from functools import wraps
from datetime import date
from flask import flash, render_template, redirect, url_for,session,request, jsonify, g
from form import SimpleProductForm, WriteForm
from kept_products import record_kept_product
from cash_book import cash_book_period
from advance_recovery import advance_recovery_period, outstanding_worker_totals
from simple_workflow import (CORE_ENTITIES, register_simple_workflow, dashboard_period, dashboard_movement_details,
                             dashboard_job_balances, report_period, report_period_selection)
from form import Outworker_form, Return_form, Login_form, Date_form_with_name, EditEntryForm
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, AnonymousUserMixin
from data_entry import add_items, add_outworker_db, add_manual_jobcard, in_move_entery
from data_Process import (get_jobcard_return_data, get_jobcard_ledger, get_current_week_range,
                          outworker_name, outworker_job_ledger)
from modes import User, Jobcard, Jobmovement, Item_data as ProductModel, Outworker
from edit_service import ENTITY_CONFIG, edit_context, save_entry, audit_logs, search_entries
from item_aliases import resolve_item_name, item_name_mapping
from master_aliases import master_name_mapping, master_name_options, resolve_master_name
from return_workspace import open_outworker_jobs
from bundle_types import BUNDLE_TYPE_CHOICES
from return_reconciliation import unassigned_returns, assign_return
from data_Process import outworker_period_account
from payroll_routes import register_payroll_routes
from validation import record_id
from database_writes import DatabaseBusy, is_database_busy
from data_entry import RequestConflict, saved_receipt
from sqlalchemy.exc import OperationalError, TimeoutError as PoolTimeout

JSON_ENDPOINTS = {"submit_jobcard", "submit_manual_jobcard", "summit_retune", "edit_search"}


def _write_json():
    data = request.get_json(silent=True)
    key = data.get("request_id") if isinstance(data, dict) else None
    if not isinstance(key, str) or not key.strip() or len(key) > 128:
        return None, (jsonify(success=False, code=405,
                              message="A valid request ID and JSON data are required. Reload the page."), 400)
    return data, None


def register_routes(app,db):
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'

    @app.errorhandler(RequestConflict)
    def request_conflict(error):
        db.session.rollback()
        if request.endpoint in JSON_ENDPOINTS:
            return jsonify(success=False, code=409, message=str(error)), 409
        return render_template('save_busy.html', message=str(error), heading='Entry needs review',
                               guidance='Review the existing saved entry first. Reload the entry form only when you intend to create a new submission.'), 409

    @app.errorhandler(DatabaseBusy)
    @app.errorhandler(PoolTimeout)
    def database_busy(error):
        db.session.rollback()
        # Flask-Login's template context processor also resolves current_user.
        # Cache a request-local fallback without changing the login cookie.
        g._login_user = AnonymousUserMixin()
        message = 'The database is busy. Your save could not be confirmed. Please retry the same entry.'
        if request.endpoint in JSON_ENDPOINTS:
            response = jsonify(success=False, code=503, retryable=True, message=message)
        else:
            # Rendering a busy page must not acquire another user-DB connection.
            response = app.make_response(render_template(
                'save_busy.html', message=message, current_user=AnonymousUserMixin()))
        response.status_code = 503
        response.headers['Retry-After'] = '2'
        return response

    @app.errorhandler(OperationalError)
    def database_operation_error(error):
        if is_database_busy(error):
            return database_busy(error)
        db.session.rollback()
        app.logger.error('Database operation failed', exc_info=error)
        g._login_user = AnonymousUserMixin()
        if request.endpoint in JSON_ENDPOINTS:
            return jsonify(success=False, code=500, message='The save failed. Please retry the same entry.'), 500
        return render_template('save_busy.html', message='The database operation failed. Return to your entry and retry.',
                               current_user=AnonymousUserMixin()), 500

    @login_manager.unauthorized_handler
    def authentication_required():
        if request.endpoint in JSON_ENDPOINTS:
            return jsonify(success=False, message="Login required.", code=401), 401
        return redirect(url_for("login", next=request.path))

    def oly_admin(func):
        @wraps(func)
        def admin_(*args, **kwargs):
            if not current_user.is_authenticated:
                return authentication_required()
            if current_user.role != 1:
                if request.endpoint in JSON_ENDPOINTS:
                    return jsonify(success=False, code=403, message="Admin access only."), 403
                flash("Administrator access is required for this page.", 'danger')
                return redirect(url_for("home"))
            return func(*args, **kwargs)

        return admin_

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        if request.endpoint in JSON_ENDPOINTS:
            return jsonify(success=False, code=500, message="The entry could not be saved. Retry with the same request ID."), 500
        g._login_user = AnonymousUserMixin()
        return render_template('error_page.html', code=500, heading='Something went wrong',
                               message='The request could not be completed. If you were saving, return to the entry and retry with the same request key.'), 500

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(405)
    def page_error(error):
        messages = {
            400: ('Check this request', 'This request is invalid or the form has expired. Review the entry and try again.'),
            403: ('Access not allowed', 'Your account does not have permission to open this page or perform this action.'),
            404: ('Page or entry not found', 'This page or record could not be found. Check its number or open the workspace.'),
            405: ('Action not available', 'This action is not available on this page. Use the buttons in the app.'),
        }
        heading, message = messages[error.code]
        # Preserve status codes and protocol headers, including Allow on a 405.
        response = error.get_response()
        if request.endpoint in JSON_ENDPOINTS:
            response.set_data(jsonify(success=False, code=error.code, message=message).get_data())
            response.content_type = 'application/json'
        else:
            response.set_data(render_template('error_page.html', code=error.code, heading=heading, message=message))
            response.content_type = 'text/html; charset=utf-8'
        return response

    register_payroll_routes(app, oly_admin)
    register_simple_workflow(app, oly_admin)

    def job_operator(func):
        @wraps(func)
        def allowed(*args, **kwargs):
            if app.config.get('SIMPLE_WORKFLOW') and current_user.role in (1, 2):
                return func(*args, **kwargs)
            return oly_admin(func)(*args, **kwargs)
        return allowed

    @login_manager.user_loader
    def load_user(user_id):
        user = (User.query.filter_by(auth_id=user_id).first()
                if isinstance(user_id, str) and len(user_id) == 64 else None)
        return user if user and user.is_active else None
    @app.route("/jobcard", methods=["GET", "POST"])
    @login_required
    @job_operator
    def job_card():
        return redirect(url_for('manual_job_card'))

    @app.route("/manual_jobcard")
    @login_required
    @job_operator
    def manual_job_card():
        job_card_data_c = {"outworker": outworker_name()}
        product_names = item_name_mapping()
        master_names = master_name_mapping()
        return render_template(
            "manual_jobcard.html", id=current_user.role, data=job_card_data_c,
            product_names=list(product_names), product_alias_map=product_names,
            master_alias_map=master_names, master_options=master_name_options(),
            bundle_type_choices=BUNDLE_TYPE_CHOICES,
        )

    @app.route("/submit-manual-jobcard", methods=["POST"])
    @login_required
    @job_operator
    def submit_manual_jobcard():
        data, error = _write_json()
        if error:
            return error
        result = add_manual_jobcard(
            data, current_user,
            data.get("request_id") if isinstance(data, dict) else None,
        )
        if isinstance(result, dict):
            if result.get("code") == 101:
                return jsonify(success=True, message="Manual job card saved", jobData=result["jobData"],
                               label_csvs=result.get('label_csvs', []), print_warning=result.get('print_warning'))
        if result == 401:
            return jsonify(success=False, code=401, message="Master name was not found."), 400
        if result == 405:
            return jsonify(success=False, code=405, message="Manual job-card data is invalid."), 400
        if result == 406:
            return jsonify(success=False, code=406, message="Item name or alias was not found. Add the product in Item Setup first."), 400
        if result == 409:
            receipt = saved_receipt(data['request_id'], 'add_manual_jobcard', current_user)
            return jsonify(success=True, duplicate=True, message="Job card already saved; original receipt restored.", **receipt)
        return jsonify(success=False, code=500, message="Manual job card could not be saved."), 500
    @app.route("/add_items", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def add_item():
        form_name = "Item setup"
        current_form = SimpleProductForm()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            token = data.pop("submission_token")
            data.update(size=0, meter=0)
            items = add_items(data,current_user,token)
            if items == 101 :
                flash(f"You have successfully added  {data['name']} .", "success")
                product = ProductModel.query.filter_by(name=resolve_item_name(data['name'])).one()
                return redirect(url_for('payroll_rates', product_id=product.id))
            elif items == 409:
                flash("Duplicate request ignored; this product was already submitted.", "warning")
                return redirect(url_for("add_item"))
            elif isinstance(items, dict) and items.get("or") is False:
                message = str(items["exception"]) if isinstance(items["exception"], ValueError) else "Could not save item. Please retry; if it still fails, contact the administrator."
                flash(message, "danger")

        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form,id=current_user.role,
            item_rows=ProductModel.query.order_by(ProductModel.name).all(),
        )
    @app.route("/add_outworver", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def add_outworker():
        form_name = "Master setup"
        current_form = Outworker_form()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            token = data.pop("submission_token")
            outworker = add_outworker_db(data,current_user,token)
            if outworker == 101 :
                flash(f"You have successfully added  {data['name']} .", "success")
                return redirect(url_for("add_outworker"))
            elif outworker == 409:
                flash("Duplicate request ignored; this outworker was already submitted.", "warning")
                return redirect(url_for("add_outworker"))
            elif isinstance(outworker, dict) and outworker.get("or") is False:
                message = str(outworker["exception"]) if isinstance(outworker["exception"], ValueError) else "Could not save master. Please retry; if it still fails, contact the administrator."
                flash(message, "danger")

        return render_template(
            "outworker_setup.html",
            form_name=form_name,
            current_form=current_form,id=current_user.role
        )
    @app.route("/retune_product", methods=["GET", "POST"])
    @login_required
    @job_operator
    def retune_product():
        current_form =  Return_form()
        ok =  request.args.get("ok",type=int)
        if ok == 101 :
            flash("Return saved successfully.", "success")
            return redirect(url_for("retune_product"))

        elif ok == 403:
            flash("The item does not match this job card.", 'danger')
            return redirect(url_for("retune_product"))

        elif ok == 405:
            flash("Return data is invalid. Check the quantities and try again.", 'danger')
            return redirect(url_for("retune_product"))
        elif ok==401:
            flash("The outworker could not be found. Select a name from the suggestions.", 'danger')
            return redirect(url_for("retune_product"))
        elif ok == 404:
            flash("The return record could not be found. Check the job card number.", 'danger')
            return redirect(url_for("retune_product"))
        if current_form.validate_on_submit():
            if current_form.jobcard_id.data and current_form.jobcard_id.data > 0:
                return redirect(url_for("job_retun", jobcard_id=current_form.jobcard_id.data))
            flash("Enter a valid job card number.", "danger")
        return render_template("return_lookup.html", current_form=current_form, id=current_user.role,
                               master_options=master_name_options())

    @app.route('/returns/outworker')
    @login_required
    @job_operator
    def outworker_returns():
        raw = request.args.get('worker_id') or request.args.get('worker', '')
        name = resolve_master_name(raw) if raw else None
        worker_id = record_id(name.split('***', 1)[0]) if name else None
        worker = db.session.get(Outworker, worker_id) if worker_id else None
        if raw and worker is None:
            flash('Select a valid outworker name, alias, or ID.', 'danger')
            return redirect(url_for('retune_product'))
        jobs = open_outworker_jobs(worker) if worker else []
        return render_template('outworker_returns.html', id=current_user.role, worker=worker,
                               jobs=jobs, master_options=master_name_options())
    @app.route("/job_retun", methods=["GET", "POST"])
    @login_required
    @job_operator
    def job_retun():
        jobcard_id = request.args.get("jobcard_id", type=int)
        if not jobcard_id or jobcard_id < 1:
            flash("Enter a job card number.", "danger")
            return redirect(url_for("retune_product"))
        data = get_jobcard_return_data(jobcard_id)
        if data is None:
            flash(f"Job card #{jobcard_id} was not found.", "danger")
            return redirect(url_for("retune_product"))
        if not data["items"] and not data["completed_items"]:
            flash(f"Job card #{jobcard_id} has no returnable items or return history.", "warning")
            return redirect(url_for("retune_product"))
        products = {row.name: row for row in ProductModel.query.all()}
        kept_options = [{'item': item, 'product': products.get(item['product_name'])} for item in data['items']]
        receipt_key = request.args.get('saved_return', '')
        receipt = saved_receipt(receipt_key, 'return_items', current_user) if receipt_key and len(receipt_key) <= 128 else {}
        saved_return = receipt.get('jobData')
        if saved_return and str(saved_return.get('jobcard_id')) != str(jobcard_id):
            saved_return = None
        return render_template("job_retun.html",data=data,id=current_user.role, kept_form=WriteForm(), kept_options=kept_options,
                               saved_return=saved_return, csv_warning=request.args.get('csv_warning') == '1',
                               kept_only=request.args.get('kept_only') == '1',
                               embedded=request.args.get('embedded') == '1')

    @app.route('/jobcard/<int:jobcard_id>/kept', methods=['POST'])
    @login_required
    @job_operator
    def jobcard_kept(jobcard_id):
        form = WriteForm()
        wants_json = request.accept_mimetypes.best == 'application/json'
        if not form.validate_on_submit():
            if wants_json:
                return jsonify(success=False, message='This form expired. Reload and review the kept pieces.'), 400
            flash('This form expired. Reload and review the kept pieces.', 'danger')
        else:
            try:
                row = record_kept_product(jobcard_id, request.form.get('product_id'), request.form.get('bundle_type'),
                    request.form.get('pieces'), request.form.get('expected_value'), request.form.get('expected_remaining'),
                    request.form.get('confirmed'), request.form.get('note'), form.submission_token.data, current_user)
                flash(f'{row.pieces} kept pieces recorded. ₹{row.amount_paise / 100:.2f} added to amount to recover (Advance #{row.advance_id}).', 'success')
                if wants_json:
                    return jsonify(success=True)
            except ValueError as error:
                if wants_json:
                    return jsonify(success=False, message=str(error)), 400
                flash(str(error), 'danger')
        return redirect(url_for('job_retun', jobcard_id=jobcard_id,
                                embedded='1' if request.form.get('embedded') == '1' else None,
                                kept_only='1' if request.form.get('kept_only') == '1' else None,
                                _anchor='kept-pieces'))
    @app.route('/edit/jobcard/open')
    @login_required
    @oly_admin
    def open_jobcard_edit():
        card_id = record_id(request.args.get('jobcard_id', ''))
        if card_id is None:
            flash('Enter a valid job card number to edit.', 'danger')
            return redirect(url_for('manual_job_card', _anchor='open-old-job'))
        if db.session.get(Jobcard, card_id) is None:
            flash(f'Job card #{card_id} was not found.', 'danger')
            return redirect(url_for('manual_job_card', _anchor='open-old-job'))
        return redirect(url_for('edit_entry', entity_type='jobcard', entity_id=card_id))

    @app.route("/jobcard/ledger")
    @login_required
    @job_operator
    def jobcard_ledger_lookup():
        error = None
        if "jobcard_id" in request.args:
            raw_id = request.args.get("jobcard_id", "").strip()
            parsed_id = record_id(raw_id)
            if parsed_id is None:
                error = "Enter a valid job card number."
            elif db.session.get(Jobcard, parsed_id) is None:
                error = f"Job card #{raw_id} was not found."
            else:
                return redirect(url_for("jobcard_ledger", jobcard_id=parsed_id))
        return render_template("jobcard_ledger_lookup.html", id=current_user.role, error=error)
    @app.route("/jobcard/<int:jobcard_id>/ledger")
    @login_required
    @job_operator
    def jobcard_ledger(jobcard_id):
        detail = get_jobcard_ledger(jobcard_id)
        if detail is None:
            return render_template('error_page.html', code=404, heading='Job card not found',
                                   message='Job card not found. Check its number and try again.'), 404
        return render_template("jobcard_ledger.html", detail=detail, id=current_user.role)
    @app.route("/summit-retune", methods=["POST"])
    @login_required
    @job_operator
    def summit_retune():
        data, error = _write_json()
        if error:
            return error

        res = in_move_entery(data,current_user,data.get("request_id") if isinstance(data, dict) else None)
        if type(res) == dict:
            if res["code"] == 101:
                latest = get_jobcard_return_data(data['jobcard_id'])
                remaining = sum(item['issued'] for item in latest['items'])
                return jsonify(success=True, message="Data saved",jobData=res,remaining=remaining)
        elif res  == 404 :
            return jsonify(success=False, message="Job card not found or return could not be saved.",code=404), 404
        elif res == 500:
            return jsonify(success=False, code=500, message="Return could not be saved. Retry with the same request ID."), 500
        elif res == 401:
            return jsonify(success=False, message="The outworker does not match this job card.",code=401), 400
        elif res == 403:
            return jsonify(success=False, message="The product does not match this job card.",code=403), 400
        elif res == 405:
            return jsonify(success=False, message="Return data is invalid.",code=405), 400
        elif res == 4033:
            return jsonify(success=False, message="Return exceeds the remaining balance on this job card. Refresh and try again.", code=4033), 409
        elif res == 4035:
            return jsonify(success=False, message="This product has future-dated job movements. Correct those dates before recording a return.", code=4035), 409
        elif res == 409:
            latest = get_jobcard_return_data(data.get('jobcard_id'))
            remaining = sum(item['issued'] for item in latest['items']) if latest else None
            return jsonify(success=True, duplicate=True, message="Duplicate return request ignored.", code=409,
                           remaining=remaining, jobData=saved_receipt(data['request_id'], 'return_items', current_user))
        else:
            return jsonify(success=False, message="The return item or type no longer matches this job card. Refresh and try again.", code=res), 400
    @app.route("/admin_dashord", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def admin_dashord():
        try:
            overview = dashboard_period(request.args)
        except (ValueError, OverflowError):
            flash('Choose valid From and To dates, with From on or before To.', 'danger')
            return redirect(url_for('admin_dashord'))
        cash = cash_book_period(overview['week_start'], overview['week_end'])
        recovery = advance_recovery_period(overview['week_start'], overview['week_end'])
        recovery['outstanding'] = sum(row.balance for row in outstanding_worker_totals())
        return render_template('simple_dashboard.html', id=current_user.role, overview=overview, cash=cash,
                               recovery=recovery)

    @app.route('/cash_book')
    @login_required
    @oly_admin
    def cash_book():
        try:
            period = report_period(**report_period_selection(request.args))
        except (ValueError, OverflowError):
            flash('Choose valid From and To dates, with From on or before To.', 'danger')
            return redirect(url_for('cash_book'))
        cash = cash_book_period(period['week_start'], period['week_end'], include_entries=True)
        return render_template('cash_book.html', id=current_user.role, period=period, cash=cash)

    @app.route('/dashboard/movements')
    @login_required
    @oly_admin
    def dashboard_movements():
        try:
            overview = dashboard_period(request.args)
            kind = request.args.get('kind', 'all')
            entries = dashboard_movement_details(overview, kind)
            view = request.args.get('view', 'workers' if kind in {'opening', 'closing'} else 'jobs')
            if view not in {'workers', 'jobs'}:
                view = 'workers'
            sort_by = request.args.get('sort', 'age_desc')
            if sort_by not in {'age_desc', 'age_asc', 'quantity_desc', 'quantity_asc', 'product'}:
                sort_by = 'age_desc'
            product_filter = request.args.get('product', '').strip()[:100]
            balances = dashboard_job_balances(overview, kind, entries, product_filter, sort_by)
        except (ValueError, OverflowError):
            flash('Choose a valid date range and movement type.', 'danger')
            return redirect(url_for('admin_dashord'))
        return render_template('dashboard_movements.html', id=current_user.role,
                               overview=overview, kind=kind, entries=entries, balances=balances,
                               view=view, sort_by=sort_by, product_filter=product_filter)

    @app.route('/outworker/jobs')
    @login_required
    @oly_admin
    def outworker_jobs():
        raw = request.args.get('worker_id') or request.args.get('worker', '')
        name = resolve_master_name(raw) if raw else None
        worker_id = record_id(name.split('***', 1)[0]) if name else None
        worker = db.session.get(Outworker, worker_id) if worker_id else None
        if raw and worker is None:
            flash('Select a valid outworker name, alias, or ID.', 'danger')
            return redirect(url_for('outworker_jobs'))
        report = None
        payment_filter = request.args.get('payment_status', 'all')
        if payment_filter not in {'all', 'paid', 'partial', 'unpaid', 'ready', 'check'}:
            payment_filter = 'all'
        if worker:
            cards = Jobcard.query.filter_by(given_to=name)
            first = cards.order_by(Jobcard.date.asc()).first()
            last = cards.order_by(Jobcard.date.desc()).first()
            report = outworker_job_ledger(name, first.date.date() if first else date.today(),
                                         last.date.date() if last else date.today())
            report['all_job_count'] = len(report['jobs'])
            if payment_filter == 'ready':
                report['jobs'] = [job for job in report['jobs']
                                  if job['payable_pieces'] > 0 and job['status'] != 'Check balance']
            elif payment_filter != 'all':
                report['jobs'] = [job for job in report['jobs'] if job['payment_status'] == payment_filter]
        return render_template('outworker_jobs.html', id=current_user.role, worker=worker,
                               report=report, master_options=master_name_options(), payment_filter=payment_filter)

    @app.route("/outworker_report", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def outworker_report():
        name_data_form = Date_form_with_name()
        range_data = get_current_week_range()
        if not name_data_form.is_submitted():
            name_data_form.date_from.data = range_data["from_date"].date()
            name_data_form.date_to.data = range_data["to_date"].date()
        report = None
        pending_returns = []
        if name_data_form.validate_on_submit():
            name = resolve_master_name(name_data_form.name.data)
            if not name:
                flash("Select an outworker by name, alias, or ID.", "danger")
            elif name_data_form.date_from.data > name_data_form.date_to.data:
                flash("The From date must be on or before the To date.", "danger")
            else:
                name_data_form.name.data = name
                if request.form.get("action") == "assign_return":
                    try:
                        assign_return(
                            int(request.form.get("movement_id", "")),
                            int(request.form.get("card_id", "")), current_user,
                        )
                        flash("Return linked to the job card. Its ledger has been updated.", "success")
                    except ValueError as error:
                        flash(str(error), "danger")
                report = outworker_job_ledger(
                    name, name_data_form.date_from.data, name_data_form.date_to.data,
                )
                report["account"] = outworker_period_account(
                    name, name_data_form.date_from.data, name_data_form.date_to.data,
                )
                pending_returns = unassigned_returns(name)
        elif name_data_form.is_submitted():
            flash("Enter an outworker and valid From and To dates.", "danger")
        return render_template(
            "outworker_job_report.html", id=current_user.role, master_options=master_name_options(),
            current_form=name_data_form, report=report,
            pending_returns=pending_returns,
            selected_worker_id=record_id(report['name'].split('***', 1)[0]) if report else None,
        )

    @app.route("/")
    @login_required
    def home():
        if current_user.role == 1:
            return redirect("/admin_dashord")
        elif current_user.role == 2:
            return redirect(url_for('manual_job_card'))
        else:
            return redirect(url_for("logout"))

    @app.route("/login", methods=['GET', 'POST'])
    def login():
        name_from = Login_form()
        wants_json = request.accept_mimetypes.best == 'application/json'

        def login_result(message, status):
            response = jsonify(success=False, message=message)
            response.headers['Cache-Control'] = 'no-store'
            return response, status

        if name_from.validate_on_submit():
            username = name_from.user_name.data.strip().lower()
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(name_from.password.data):
                if user.is_active:
                    login_user(user)
                    if wants_json:
                        response = jsonify(success=True, redirect=url_for('home'))
                        response.headers['Cache-Control'] = 'no-store'
                        return response
                    return redirect("/")
                if wants_json:
                    return login_result("This account is disabled. Contact an administrator.", 403)
                flash("This account is disabled. Contact an administrator.", "danger")
            else:
                if wants_json:
                    return login_result("Username or password is incorrect.", 401)
                flash("Username or password is incorrect.", "danger")
        elif request.method == "POST":
            if getattr(name_from, "csrf_token", None) is not None and name_from.csrf_token.errors:
                if wants_json:
                    return login_result("This login form expired. Reload the page and try again.", 400)
                flash("This login form expired. Reload the page and try again.", "warning")
            else:
                if wants_json:
                    return login_result("Enter both a username and password.", 422)
                flash("Enter both a username and password.", "warning")

        return render_template('login.html', form_name="Login",
            current_form=name_from)

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))
    @app.route("/edit")
    @login_required
    @oly_admin
    def edit_index():
        entities = {key: value for key, value in ENTITY_CONFIG.items()
                    if key in CORE_ENTITIES}
        selected_type = request.args.get('type', 'product')
        if selected_type not in entities:
            selected_type = 'product'
        return render_template(
            "edit_index.html", entities=entities, selected_type=selected_type, id=current_user.role,
        )

    @app.route("/edit/search")
    @login_required
    @oly_admin
    def edit_search():
        entity_type = request.args.get("type", "")
        result = search_entries(
            entity_type, request.args.get("q", ""),
            request.args.get("page", default=1, type=int),
        )
        if result is None:
            return jsonify(error="Unknown entry type"), 404
        return jsonify(result)

    @app.route("/edit/<entity_type>/<int:entity_id>", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def edit_entry(entity_type, entity_id):
        if entity_type == "movement":
            movement = db.session.get(Jobmovement, entity_id) if record_id(entity_id) else None
            return render_template("managed_entry.html", id=current_user.role,
                                   jobcard_id=movement.jobcard if movement else None), 403
        context = edit_context(entity_type, entity_id)
        if not context:
            flash("Entry not found.", "danger")
            return redirect(url_for("edit_index"))
        form = EditEntryForm()
        if request.method == "GET":
            form.version.data = context["version"]
        if form.validate_on_submit():
            status, detail = save_entry(
                entity_type, entity_id, request.form, form.version.data,
                form.submission_token.data, current_user.username,
            )
            if status == "saved":
                flash(f"Saved. Changed fields: {', '.join(detail) if detail else 'none'}", "success")
                return redirect(url_for("edit_entry", entity_type=entity_type, entity_id=entity_id))
            if status == "duplicate":
                flash("Duplicate save request ignored.", "warning")
                return redirect(url_for("edit_entry", entity_type=entity_type, entity_id=entity_id))
            if status == "conflict":
                flash("Someone changed this entry after you opened it. Review the latest values and save again.", "danger")
                return redirect(url_for("edit_entry", entity_type=entity_type, entity_id=entity_id))
            flash(f"Could not save: {detail}", "danger")
        if request.method == "POST":
            context["draft"] = request.form
        template = 'outworker_edit.html' if entity_type == 'outworker' else 'edit_entry.html'
        return render_template(template, form=form, entry=context, id=current_user.role)

    @app.route("/edit-logs")
    @login_required
    @oly_admin
    def edit_logs():
        entity_type = request.args.get("entity_type") or None
        entity_id = request.args.get("entity_id", type=int)
        logs = audit_logs(entity_type, entity_id)
        return render_template(
            "edit_logs.html", logs=logs, entities=ENTITY_CONFIG,
            selected_type=entity_type, selected_id=entity_id, id=current_user.role,
        )
