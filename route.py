from functools import wraps
from datetime import date
from flask import flash, render_template, redirect, url_for,session,request, jsonify, g
from form import SimpleProductForm, WriteForm
from kept_products import record_kept_product
from simple_workflow import CORE_ENTITIES, register_simple_workflow, dashboard_period, dashboard_movement_details
from form import Lump_data, bundle_invadata, Item_data, Outworker_form, Cutter_form, Return_form, Login_form, Date_form, Date_form_with_name,bale_data_form,party_name,Find_and_edit,EditEntryForm
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, AnonymousUserMixin
from data_entry import add_cutter,add_items,add_outworker_db,add_jobcard,add_manual_jobcard,in_move_entery,bale_data_entry,add_party
from data_Process import get_serch_data, get_job_card_data_creation, get_jobcard_return_data, get_jobcard_ledger, \
    get_current_week_range, home_dashboard,get_cutter_report_data,outworker_name,outworker_job_ledger,product_data,find_edit_data
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


def reset_session(flow:int):
    # remove all bale lever1
    # remove all lump  vevel
    if flow== 1:
        keys_roremove =  ["bundle_data","current_bundle","bundles","sno","bale_data","current_lump","sno_lump","lump_workflow_id"]
    if flow == 2:
        keys_roremove = ["bundle_data", "current_bundle", "bundles", "sno", "lump_workflow_id"]
        if  (str(type(session['bale_data']['packing_date']))) == "<class 'datetime.datetime'>":
            session['bale_data']['packing_date'] =  session['bale_data']['packing_date'].strftime("%a, %d %b %Y")
    for key in list(session.keys()):
        if key in keys_roremove:
            session.pop(key)


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
                flash("Admin access only")
                return redirect(url_for("home"))
            return func(*args, **kwargs)

        return admin_

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        if request.endpoint in JSON_ENDPOINTS:
            return jsonify(success=False, code=500, message="The entry could not be saved. Retry with the same request ID."), 500
        return error

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
    @app.route("/bale_entery",methods=["GET", "POST"])
    @login_required
    def bale_entery():
        form_name  = " bale entery "
        data_autofill = get_serch_data()
        current_form = bale_data_form()
        if current_form.validate_on_submit():
            if current_form.cuter_name.data not in data_autofill["cuter_data"]:
                flash("select cutter name from blow","warning")
                return redirect(url_for("bale_entery"))
            canonical_product = resolve_item_name(current_form.product_name.data)
            if not canonical_product:
                flash("select product name from blow","warning")
                return redirect(url_for("bale_entery"))
            if current_form.party_name.data not in data_autofill["party_data"]:
                flash("select party name from blow","warning")
                return redirect(url_for("bale_entery"))

            ### do some date vlaidation

        ## data prosessing
            data = current_form.data
            data["product_name"] = canonical_product
            data.pop("submission_token", None)
            data.pop("csrf_token", None)
            data['packing_date'] = data['packing_date'].strftime("%a, %d %b %Y")
            reset_session(1)
            session["bale_data"] = data
            session["current_lump"] = 1
            session["sno_lump"] = 0
            return  redirect(url_for("lump_home"))

        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form,
            data=data_autofill,
            id=current_user.role
        )
    @app.route("/lumpentry", methods=["GET", "POST"])
    @login_required
    def lump_home():
        if (
                "bale_data" not in session
                or "current_lump" not in session
                or "sno_lump" not in session
        ):
            return redirect(url_for("bale_entery"))
        total = int(session["bale_data"]["number_lup"])
        current = int(session["current_lump"])
        if current > total:
            reset_session(1)
            flash("You have successfully entered the bale.", "success")
            return redirect(url_for('bale_entery'))

        form_name = f"lump entry ({current}/{total}) "
        current_form = Lump_data()
        if request.method == "GET" and session.get("inventory_save_failed"):
            for name, value in session.get("bundle_data", {}).items():
                if name in current_form._fields and name not in {"csrf_token", "submission_token", "submit"}:
                    current_form[name].data = value
            current_form.submission_token.data = session.get("lump_workflow_id")
        # data to auto fill
        data_autofill = get_serch_data()
        if not current_form.validate_on_submit():
            current_form.party_name.data = session["bale_data"]["party_name"]

            current_form.cuter_name.data = session["bale_data"]["cuter_name"]
            current_form.product_name.data =  session["bale_data"]["product_name"]
        if current_form.validate_on_submit():
            data = current_form.data.copy()
            lump_workflow_id = data.pop("submission_token", None)
            if current_form.cuter_name.data not in data_autofill["cuter_data"]:
                flash("select cutter name from blow","warning")
                return redirect(url_for("lump_home"))
            canonical_product = resolve_item_name(current_form.product_name.data)
            if not canonical_product:
                flash("select product name from blow","warning")
                return redirect(url_for("lump_home"))
            if current_form.party_name.data not in data_autofill["party_data"]:
                flash("select party name from blow","warning")
                return redirect(url_for("lump_home"))
            data.pop("csrf_token", None)
            data["product_name"] = canonical_product

            ### do some date vlaidation

            # =
            if data['numbers_of_bundles'] > 20 :
                    flash("you can not enter more then 20")
                    return redirect(url_for("lump_home"))

                # 🔄 reset any old flow
            reset_session(2)
            session.pop("inventory_save_failed", None)

                # 🚀 initialize bundle workflow
            session["bundle_data"] = data
            session["current_bundle"] = 1
            session["bundles"] = {}
            session["sno"]=0
            session["lump_workflow_id"] = lump_workflow_id
            session["current_lump"] = current + 1
            return redirect(url_for("bundle_entery"))



        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form,
            data=data_autofill,
            id=current_user.role
        )
    @app.route("/bundle_entery", methods=["GET", "POST"])
    @login_required
    def bundle_entery():

        # 🔐 Guard: block direct access / broken session
        if (
                "bundle_data" not in session
                or "current_bundle" not in session
                or "bundles" not in session
                or "sno" not in session
                or not session.get("lump_workflow_id")
        ):
            return redirect(url_for("lump_home"))

        total = int(session["bundle_data"]["numbers_of_bundles"])
        current = int(session["current_bundle"])

        # ✅ All bundles completed
        if current > total:
            all_data = {


                "main": session["bundle_data"],
                "bundles": session["bundles"],
                "bale_data" :session["bale_data"]
            }

            # print(all_data)
            result = bale_data_entry(all_data, current_user, session.get("lump_workflow_id"))
            if result not in (101, 409):
                session["current_lump"] = max(1, int(session.get("current_lump", 2)) - 1)
                session["inventory_save_failed"] = True
                flash("Inventory was not saved. Your draft is retained; review the lump and bundle details and retry.", "danger")
                return redirect(url_for("lump_home"))
            reset_session(2)
            if result == 409:
                flash("This lump was already saved. Duplicate request ignored.", "warning")
                return redirect(url_for("lump_home"))
            else:
                flash("You have successfully entered the bundle.", "success")
                return redirect(url_for("lump_home"))


        form_name = f"Bundle Entry ({current}/{total})"
        current_form = bundle_invadata()
        if not current_form.validate_on_submit():
            if session['sno'] != 0:
                current_form.no_of_so.data = session['sno'] +1
            if  session["bundle_data"]['bundle_type'] == "goodCUT 20 picset" or  session["bundle_data"]['bundle_type'] == "fent 20 picset":
                current_form.no_of_pics.data = 20


        if current_form.validate_on_submit():
            data = current_form.data.copy()
            data.pop("submission_token", None)
            data.pop("csrf_token", None)
            ### do some date vlaidation

            # =

            # ⚠️ use string keys for session safety
            session["bundles"][str(current)] = data
            session["current_bundle"] = current + 1
            session["sno"]  = current_form.no_of_so.data
            return redirect(url_for("bundle_entery"))

        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form,
            id=current_user.role
        )
    @app.route("/jobcard", methods=["GET", "POST"])
    @login_required
    @job_operator
    def job_card():
        if app.config.get('SIMPLE_WORKFLOW'):
            return redirect(url_for('manual_job_card'))
        job_card_data_c = get_job_card_data_creation()
        return render_template("jobcard.html",id=current_user.role,data = job_card_data_c)

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
        current_form = SimpleProductForm() if app.config.get('SIMPLE_WORKFLOW') else Item_data()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            token = data.pop("submission_token")
            if app.config.get('SIMPLE_WORKFLOW'):
                data.update(size=0, meter=0)
            items = add_items(data,current_user,token)
            if items == 101 :
                flash(f"You have successfully added  {data['name']} .", "success")
                if app.config.get('SIMPLE_WORKFLOW'):
                    product = ProductModel.query.filter_by(name=resolve_item_name(data['name'])).one()
                    return redirect(url_for('payroll_rates', product_id=product.id))
                return redirect(url_for("add_item"))
            elif items == 409:
                flash("Duplicate request ignored; this product was already submitted.", "warning")
                return redirect(url_for("add_item"))
            elif isinstance(items, dict) and items.get("or") is False:
                message = str(items["exception"]) if isinstance(items["exception"], ValueError) else "Could not save item. Please retry; if it still fails, contact the administrator."
                flash(message, "danger")
                return redirect(url_for("add_item"))

        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form,id=current_user.role,
            item_rows=ProductModel.query.order_by(ProductModel.name).all(),
        )
    @app.route("/add_suppy", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def add_suppy():
        form_name = "add new suppy"
        current_form = party_name()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            token = data.pop("submission_token")
            party = add_party(data, current_user,token)
            if party == 101:
                flash(f"You have successfully added  {data['name']} .", "success")
                return redirect(url_for("add_suppy"))
            elif party == 409:
                flash("Duplicate request ignored; this party was already submitted.", "warning")
                return redirect(url_for("add_suppy"))
            elif party["or"] == False:
                flash(f"call  badx {party['exception']}")
                return redirect(url_for("add_suppy"))

        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form, id=current_user.role
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
                return redirect(url_for("add_outworker"))

        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form,id=current_user.role
        )
    @app.route("/add_cutter", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def add_cuter():
        form_name = "new cutter"
        current_form = Cutter_form()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            token = data.pop("submission_token")
            add_cu = add_cutter(data,current_user,token)
            if add_cu == 101 :
                flash(f"You have successfully added  {data['name']} cutter.", "success")
                return redirect(url_for("add_cuter"))
            elif add_cu == 409:
                flash("Duplicate request ignored; this cutter was already submitted.", "warning")
                return redirect(url_for("add_cuter"))
            elif  add_cu["or"] == False :
                flash(f"call  badx{add_cu["exception"]}")

                return redirect(url_for("add_cuter"))
        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form,id=current_user.role
        )
    @app.route("/submit-jobcard",methods=["POST"])
    @login_required
    @oly_admin
    def submit_jobcard():
        data, error = _write_json()
        if error:
            return error
        ok = add_jobcard(data,current_user,data.get("request_id") if isinstance(data, dict) else None)
        # print(ok)
        if type(ok) == dict:
            if ok["code"] == 101:
                return jsonify(success=True, message="Data saved", jobData=ok["jobData"])
        elif ok ==401:
            return jsonify(success=False, code=401, message="Master name not found. Select an outworker from the list."), 400
        elif ok == 403:
            return jsonify(success=False, code=403, message="A bundle was changed or already issued. Refresh the job card."), 409
        elif ok == 405:
            return jsonify(success=False, code=405, message="Job card data is invalid."), 400
        elif ok == 409:
            receipt = saved_receipt(data['request_id'], 'add_jobcard', current_user)
            return jsonify(success=True, duplicate=True, message="Job card already saved; original receipt restored.", **receipt)
        return jsonify(success=False, code=500, message="Job card could not be saved."), 500
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
            flash("item do not macha base" )
            return redirect(url_for("retune_product"))

        elif ok == 405:
            flash("send data not right")
            return redirect(url_for("retune_product"))
        elif ok==401:
            flash("name of master not in data base")
            return redirect(url_for("retune_product"))
        elif ok == 404:
            flash("data issue")
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
        return render_template("job_retun.html",data=data,id=current_user.role, kept_form=WriteForm(), kept_options=kept_options,
                               kept_only=request.args.get('kept_only') == '1',
                               embedded=request.args.get('embedded') == '1')

    @app.route('/jobcard/<int:jobcard_id>/kept', methods=['POST'])
    @login_required
    @job_operator
    def jobcard_kept(jobcard_id):
        form = WriteForm()
        if not form.validate_on_submit():
            flash('This form expired. Reload and review the kept pieces.', 'danger')
        else:
            try:
                row = record_kept_product(jobcard_id, request.form.get('product_id'), request.form.get('bundle_type'),
                    request.form.get('pieces'), request.form.get('expected_value'), request.form.get('expected_remaining'),
                    request.form.get('confirmed'), request.form.get('note'), form.submission_token.data, current_user)
                flash(f'{row.pieces} kept pieces recorded. ₹{row.amount_paise / 100:.2f} added to amount to recover (Advance #{row.advance_id}).', 'success')
            except ValueError as error:
                flash(str(error), 'danger')
        return redirect(url_for('job_retun', jobcard_id=jobcard_id,
                                embedded='1' if request.form.get('embedded') == '1' else None,
                                kept_only='1' if request.form.get('kept_only') == '1' else None,
                                _anchor='kept-pieces'))
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
            return "Job card not found.", 404
        return render_template("jobcard_ledger.html", detail=detail, id=current_user.role)
    @app.route("/summit-retune", methods=["POST"])
    @login_required
    @job_operator
    def summit_retune():
        data, error = _write_json()
        if error:
            return error

        res = in_move_entery(data,current_user,data.get("request_id") if isinstance(data, dict) else None)
        # print(res)
        if type(res) == dict:
            if res["code"] == 101:
             # print(res)
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
        if app.config.get('SIMPLE_WORKFLOW'):
            try:
                overview = dashboard_period(request.args)
            except (ValueError, OverflowError):
                flash('Choose valid From and To dates, with From on or before To.', 'danger')
                return redirect(url_for('admin_dashord'))
            return render_template('simple_dashboard.html', id=current_user.role, overview=overview)
        range_data = get_current_week_range()
        date_from = Date_form()
        # Pre-fill form with current week range on GET
        if not date_from.is_submitted():
            date_from.date_from.data = range_data["from_date"].date()
            date_from.date_to.data = range_data["to_date"].date()
        elif not date_from.validate():
            flash("Enter a valid start and end date.", "danger")
            return redirect(url_for("admin_dashord"))
        dash_bord_data = home_dashboard(date_from)
        if dash_bord_data == "invalid_range":
            flash("⚠️ 'From Date' cannot be after 'To Date'.", "danger")
            return redirect(url_for("admin_dashord"))
        inflow_points = sorted(
            (point for point in dash_bord_data["inflow_pie"][0]["points"] if point["quantity"] > 0),
            key=lambda point: point["quantity"], reverse=True,
        )
        outflow_points = sorted(
            (point for point in dash_bord_data["outflow_pie"][0]["points"] if point["quantity"] > 0),
            key=lambda point: point["quantity"], reverse=True,
        )
        return render_template(
            "admin_dashboard.html", id=current_user.role,
            date_from=date_from, dash_bord_data=dash_bord_data,
            inflow_points=inflow_points, outflow_points=outflow_points,
            max_inflow=max((point["quantity"] for point in inflow_points), default=1),
            max_outflow=max((point["quantity"] for point in outflow_points), default=1),
        )
    @app.route('/dashboard/movements')
    @login_required
    @oly_admin
    def dashboard_movements():
        try:
            overview = dashboard_period(request.args)
            kind = request.args.get('kind', 'all')
            entries = dashboard_movement_details(overview, kind)
        except (ValueError, OverflowError):
            flash('Choose a valid date range and movement type.', 'danger')
            return redirect(url_for('admin_dashord'))
        return render_template('dashboard_movements.html', id=current_user.role,
                               overview=overview, kind=kind, entries=entries)

    @app.route("/cutter_report",methods=["GET", "POST"])
    @login_required
    @oly_admin
    def cutter_report():
        name_data_form =  Date_form_with_name()
        range_data = get_current_week_range()
        cuter_name = get_serch_data()["cuter_data"]
        cuter_name.append("all_cutter")
        if not name_data_form.is_submitted():
            name_data_form.date_from.data = range_data["from_date"].date()
            name_data_form.date_to.data = range_data["to_date"].date()
            name_data_form.name.render_kw['placeholder']= 'Enter cutter Name'
        if name_data_form.validate_on_submit():
            if name_data_form.name.data in cuter_name:
                if name_data_form.date_from.data > name_data_form.date_to.data:
                    flash("date range is wong  data from is gater then date to", "danger")
                    return  redirect(url_for("cutter_report"))


                result = get_cutter_report_data(name_data_form,current_user)
                if result == 404:
                    flash("Cutter Report user isue", "danger")

                    return redirect(url_for("cutter_report"))

                return render_template("admin.html", date_from=name_data_form, type="CUTTER_Report",
                                       name=cuter_name, backend_data=result)


            else:

                flash("Cutter name not in list", "danger")

                return redirect(url_for("cutter_report"))



        return render_template("admin.html", date_from=name_data_form, type="CUTTER_Report",name=cuter_name)

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
        outworker_name_data =  outworker_name(oly_full_name=True)
        if not name_data_form.is_submitted():
            name_data_form.date_from.data = range_data["from_date"].date()
            name_data_form.date_to.data = range_data["to_date"].date()
        report = None
        pending_returns = []
        if name_data_form.validate_on_submit():
            name = name_data_form.name.data.strip()
            if name not in outworker_name_data:
                flash("Select an outworker from the list.", "danger")
            elif name_data_form.date_from.data > name_data_form.date_to.data:
                flash("The From date must be on or before the To date.", "danger")
            else:
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
            "outworker_job_report.html", id=current_user.role,
            current_form=name_data_form, names=outworker_name_data, report=report,
            pending_returns=pending_returns,
            selected_worker_id=record_id(report['name'].split('***', 1)[0]) if report else None,
        )

    @app.route("/product_report", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def product_report():
        name_data_form = Date_form()
        range_data = get_current_week_range()
        if not name_data_form.is_submitted():
            name_data_form.date_from.data = range_data["from_date"].date()
            name_data_form.date_to.data = range_data["to_date"].date()

        report =  product_data(name_data_form.data.copy(),current_user)


        return render_template("admin.html", date_from=name_data_form, type="PRODUCT_Report",backend_data= report)


    @app.route("/")
    @login_required
    def home():
        if current_user.role == 1:
            return redirect("/admin_dashord")
        elif current_user.role == 2:
            if app.config.get('SIMPLE_WORKFLOW'):
                return redirect(url_for('manual_job_card'))
            return redirect(url_for("bale_entery"))
        else:
            return redirect(url_for("logout"))

    @app.route("/login", methods=['GET', 'POST'])
    def login():
        name_from = Login_form()
        if name_from.validate_on_submit():
            username = name_from.user_name.data.strip().lower()
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(name_from.password.data):
                if user.is_active:
                    login_user(user)
                    return redirect("/")
                flash("This account is disabled. Contact an administrator.", "danger")
            else:
                flash("Username or password is incorrect.", "danger")
        elif request.method == "POST":
            if getattr(name_from, "csrf_token", None) is not None and name_from.csrf_token.errors:
                flash("This login form expired. Reload the page and try again.", "warning")
            else:
                flash("Enter both a username and password.", "warning")

        return render_template('login.html', form_name="Login",
            current_form=name_from)

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))
    # laber print done

    ## find function
    @app.route("/find_edit",methods=["GET", "POST"])
    @login_required
    @oly_admin
    def find_edit():

        current_form = Find_and_edit()
        data_autofill = {}
        data_autofill["cuter_data"]  = get_serch_data()["cuter_data"]
        # data_autofill['cuter_data'].append("all_bundle")
        if current_form.is_submitted():
            data_sumit =  current_form.data.copy()
            data_sumit.pop('submit')
            data_sumit.pop('csrf_token')

            date_keys =  ['entry_datetime', "cut_by" ,'s_no','id']
            input_data = {}
            for k in date_keys:
                # print(data_sumit)
                if data_sumit[k] != None:
                    if data_sumit[k] != "":
                        input_data[k] =  {"data":data_sumit[k]}

            # print(input_data)
            if input_data == {}:
                flash("need some input" , "danger")
                return redirect(url_for("find_edit"))
            result = find_edit_data(current_user, input_data)
            if result == 404 :
                flash("you ae not allowed ", "danger")
                return redirect(url_for("find_edit"))
            elif result == 403 :
                flash("log in first ", "danger")
                return redirect(url_for("find_edit"))
            elif result == 405 :
                flash("no data found  ", "danger")
                return redirect(url_for("find_edit"))
            else:
                return render_template("admin.html", date_from=current_form, type="PRODUCT_find_edit",
                                       data=data_autofill,backend_data= result)






        return render_template("admin.html", date_from=current_form, type="PRODUCT_find_edit",data=data_autofill)

    @app.route("/edit")
    @login_required
    @oly_admin
    def edit_index():
        return render_template(
            "edit_index.html", entities={key: value for key, value in ENTITY_CONFIG.items()
                                         if key in CORE_ENTITIES or (not app.config.get('SIMPLE_WORKFLOW') and key != 'movement')}, id=current_user.role,
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
        return render_template("edit_entry.html", form=form, entry=context, id=current_user.role)

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
