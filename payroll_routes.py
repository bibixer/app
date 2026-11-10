"""Admin screens for piece rates, advances and returned-piece payroll."""

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from bundle_types import BUNDLE_TYPE_CHOICES
from form import WriteForm
from validation import record_id
from master_aliases import master_name_mapping, master_name_options, resolve_master_name
from modes import (db, Outworker, Item_data, Jobcard, OutworkerRate, OutworkerPayroll,
                   OutworkerPayrollJob, OutworkerAdvanceRecovery)
from payroll_service import (PAYMENT_METHODS, worker_label, money, money_input, rate_text, rate_version,
                             save_rate, record_advance, payable_job_quotes,
                             payroll_preview, issue_payroll, payment_account, advance_entries,
                             browser_payroll_snapshot, receive_advance, receive_selected_advances)


def register_payroll_routes(app, admin_required):
    app.jinja_env.filters["money"] = money
    app.jinja_env.filters["money_input"] = money_input

    def read_review_snapshot():
        try:
            return URLSafeTimedSerializer(app.secret_key, salt="payroll-browser-review").loads(
                request.form.get("client_snapshot", ""), max_age=7200)
        except (BadSignature, SignatureExpired):
            raise ValueError("This payroll review expired or is invalid. Reload the account and calculate again.") from None

    @app.route("/payroll/rates", methods=["GET", "POST"])
    @login_required
    @admin_required
    def payroll_rates():
        form = WriteForm()
        products = Item_data.query.order_by(Item_data.name).all()
        product_id = request.values.get("product_id", type=int)
        product = (db.session.get(Item_data, product_id) if record_id(product_id) else None) if product_id else (products[0] if products else None)
        if request.method == "POST":
            if not form.validate_on_submit():
                flash("This form expired. Reload the page and try again.", "danger")
            else:
                try:
                    save_rate(product_id, request.form.get("bundle_type", ""), request.form.get("rate", ""),
                              request.form.get("version"), form.submission_token.data, current_user,
                              remove=request.form.get("action") == "remove")
                    flash("Rate updated. Saved payroll keeps its original rates.", "success")
                    return redirect(url_for("payroll_rates", product_id=product_id))
                except ValueError as error:
                    flash(str(error), "danger")
        configured = {row.bundle_type: row for row in OutworkerRate.query.filter_by(product_id=product.id).all()} if product else {}
        rate_rows = [{"type": value, "label": label, "configured": configured.get(value),
                      "version": rate_version(configured.get(value)),
                      "value": rate_text(configured[value].rate_units) if value in configured else ""}
                     for value, label in (("", "Base rate · all types"), *BUNDLE_TYPE_CHOICES)]
        return render_template("payroll_rates.html", id=current_user.role, form=form,
                               products=products, product=product, rate_rows=rate_rows)

    @app.route("/payroll", methods=["GET", "POST"])
    @login_required
    @admin_required
    def outworker_payroll():
        form = WriteForm()
        workers = Outworker.query.order_by(Outworker.name).all()
        worker_id = request.values.get("worker_id", type=int)
        # Match manual job entry on lookup only. Payment POSTs keep their explicit ID.
        worker_input = request.args.get("worker_name", "").strip() if request.method == "GET" else ""
        if request.method == "GET" and "worker_name" in request.args:
            resolved = resolve_master_name(worker_input)
            worker_id = record_id(resolved.split("***", 1)[0]) if resolved else None
            if not resolved:
                flash("Select an existing outworker by name, alias or ID.", "danger")
        worker = db.session.get(Outworker, worker_id) if record_id(worker_id) else None
        preview = None
        selected_ids = request.form.getlist("job_ids") if request.method == "POST" else request.args.getlist("job_id")
        deduction = request.form.get("deduction", "0.00")
        # The unchecked fallback precedes the checkbox in the submitted form.
        deduction_mode = request.form.getlist("deduction_mode")[-1] if "deduction_mode" in request.form else "none"
        selected_advances = request.form.getlist("advance_ids") if request.form.get("advance_selection") == "1" else None
        if request.method == "POST":
            if not form.validate_on_submit():
                flash("This form expired. Reload the page and try again.", "danger")
            elif worker is None:
                flash("Select an existing outworker.", "danger")
            else:
                try:
                    action = request.form.get("action")
                    if action == "advance":
                        record_advance(worker.id, request.form.get("amount"), request.form.get("method"),
                                       request.form.get("reference"), request.form.get("note"),
                                       form.submission_token.data, current_user)
                        flash("Advance payment recorded in the outworker account.", "success")
                        return redirect(url_for("outworker_payroll", worker_id=worker.id))
                    elif action == "recover_advance":
                        choice = request.form.get("advance_choice", "").split(":")
                        if len(choice) != 2:
                            raise ValueError("Select an outstanding advance to recover.")
                        receipt = receive_advance(worker.id, choice[0], request.form.get("amount"), choice[1],
                            request.form.get("method"), request.form.get("reference"), request.form.get("note"),
                            form.submission_token.data, current_user)
                        flash(f"Money received recorded as Recovery #{receipt.id}. The amount to recover has been reduced.", "success")
                        return redirect(url_for("outworker_payroll", worker_id=worker.id, _anchor="payment-ledger"))
                    elif action == "recover_selected_advances":
                        if selected_ids:
                            raise ValueError("Direct recovery cannot include jobs. Calculate the payroll instead.")
                        total = receive_selected_advances(worker.id, request.form.getlist("advance_ids"),
                            read_review_snapshot(), deduction, request.form.get("method"),
                            request.form.get("reference"), request.form.get("note"),
                            form.submission_token.data, current_user)
                        flash(f"Received ₹{money(total)} back from the outworker. Selected advances have been reduced; no payroll was issued.", "success")
                        return redirect(url_for("outworker_payroll", worker_id=worker.id, _anchor="payment-ledger"))
                    elif action == "preview":
                        if "deduction_mode" in request.form:
                            if deduction_mode not in ("none", "available"):
                                raise ValueError("Choose whether to deduct the available advance or carry it forward.")
                            deduction = "available" if deduction_mode == "available" else "0"
                        preview = payroll_preview(worker.id, selected_ids, deduction, advance_ids=selected_advances)
                    elif action == "pay":
                        snapshot = None
                        if request.form.get("client_snapshot"):
                            snapshot = read_review_snapshot()
                            if selected_advances is None:
                                raise ValueError("Select advances and calculate the payroll again.")
                        payroll = issue_payroll(worker.id, selected_ids, deduction, request.form.get("version"),
                                                request.form.get("method"), request.form.get("reference"),
                                                request.form.get("note"), form.submission_token.data, current_user,
                                                advance_ids=selected_advances, expected_snapshot=snapshot)
                        flash("Payment recorded and payroll issued.", "success")
                        return redirect(url_for("payroll_receipt", payroll_id=payroll.id))
                    else:
                        raise ValueError("Choose an advance or payroll action.")
                except ValueError as error:
                    flash(str(error), "danger")
        jobs = payable_job_quotes(worker) if worker else []
        advances = advance_entries(worker.id) if worker else []
        account = payment_account(worker.id) if worker else None
        client_data = browser_payroll_snapshot(worker, jobs, advances, account['advance_paise']) if worker else None
        client_snapshot = URLSafeTimedSerializer(app.secret_key, salt="payroll-browser-review").dumps(client_data) if worker else ""
        return render_template(
            "outworker_payroll.html", id=current_user.role, form=form, workers=workers, worker=worker,
            worker_name=worker_label(worker) if worker else "", selected_ids=selected_ids,
            jobs=jobs, preview=preview, deduction=deduction,
            account=account, payment_methods=PAYMENT_METHODS,
            master_options=master_name_options(), master_alias_map=master_name_mapping(),
            worker_input=worker_input,
            deduction_mode=deduction_mode,
            advances=advances, client_data=client_data, client_snapshot=client_snapshot,
            selected_advances=selected_advances or [],
        )

    @app.route("/payroll/job/<int:jobcard_id>")
    @login_required
    @admin_required
    def payroll_for_job(jobcard_id):
        card = db.session.get(Jobcard, jobcard_id) if record_id(jobcard_id) else None
        if card is not None:
            try:
                worker_id = record_id(card.given_to.split("***", 1)[0])
                worker = db.session.get(Outworker, worker_id) if worker_id else None
            except ValueError:
                worker = None
            if worker and worker_label(worker) == card.given_to:
                return redirect(url_for("outworker_payroll", worker_id=worker.id, job_id=card.id))
        flash("The job card must be linked to an outworker in Setup before payroll can be calculated.", "danger")
        return redirect(url_for("outworker_payroll"))

    @app.route("/payroll/<int:payroll_id>")
    @login_required
    def payroll_receipt(payroll_id):
        if current_user.role != 1:
            abort(403)
        payroll = db.session.get(OutworkerPayroll, payroll_id) if record_id(payroll_id) else None
        if payroll is None:
            abort(404)
        jobs = OutworkerPayrollJob.query.filter_by(payroll_id=payroll.id).order_by(OutworkerPayrollJob.jobcard_id).all()
        recoveries = OutworkerAdvanceRecovery.query.filter_by(payroll_id=payroll.id).order_by(
            OutworkerAdvanceRecovery.advance_id).all()
        return render_template("payroll_receipt.html", id=current_user.role, payroll=payroll, jobs=jobs,
                               recoveries=recoveries)
