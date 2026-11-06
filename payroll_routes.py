"""Admin screens for piece rates, advances and completed-job payroll."""

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from bundle_types import BUNDLE_TYPE_CHOICES
from form import WriteForm
from modes import db, Outworker, Item_data, Jobcard, OutworkerRate, OutworkerPayroll, OutworkerPayrollJob
from payroll_service import (PAYMENT_METHODS, worker_label, money, money_input, rate_text, rate_version,
                             save_rate, record_advance, completed_job_quotes,
                             payroll_preview, issue_payroll, payment_account)


def register_payroll_routes(app, admin_required):
    app.jinja_env.filters["money"] = money
    app.jinja_env.filters["money_input"] = money_input

    @app.route("/payroll/rates", methods=["GET", "POST"])
    @login_required
    @admin_required
    def payroll_rates():
        form = WriteForm()
        products = Item_data.query.order_by(Item_data.name).all()
        product_id = request.values.get("product_id", type=int)
        product = db.session.get(Item_data, product_id) if product_id else (products[0] if products else None)
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
        worker = db.session.get(Outworker, worker_id) if worker_id else None
        preview = None
        selected_ids = request.form.getlist("job_ids") if request.method == "POST" else request.args.getlist("job_id")
        deduction = request.form.get("deduction", "0.00")
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
                    elif action == "preview":
                        preview = payroll_preview(worker.id, selected_ids, deduction)
                    elif action == "pay":
                        payroll = issue_payroll(worker.id, selected_ids, deduction, request.form.get("version"),
                                                request.form.get("method"), request.form.get("reference"),
                                                request.form.get("note"), form.submission_token.data, current_user)
                        flash("Payment recorded and payroll issued.", "success")
                        return redirect(url_for("payroll_receipt", payroll_id=payroll.id))
                    else:
                        raise ValueError("Choose an advance or payroll action.")
                except ValueError as error:
                    flash(str(error), "danger")
        return render_template(
            "outworker_payroll.html", id=current_user.role, form=form, workers=workers, worker=worker,
            worker_name=worker_label(worker) if worker else "", selected_ids=selected_ids,
            jobs=completed_job_quotes(worker) if worker else [], preview=preview, deduction=deduction,
            account=payment_account(worker.id) if worker else None, payment_methods=PAYMENT_METHODS,
        )

    @app.route("/payroll/job/<int:jobcard_id>")
    @login_required
    @admin_required
    def payroll_for_job(jobcard_id):
        card = db.session.get(Jobcard, jobcard_id)
        if card is not None:
            paid = OutworkerPayrollJob.query.filter_by(jobcard_id=card.id).first()
            if paid:
                return redirect(url_for("payroll_receipt", payroll_id=paid.payroll_id))
            try:
                worker = db.session.get(Outworker, int(card.given_to.split("***", 1)[0]))
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
        payroll = db.session.get(OutworkerPayroll, payroll_id)
        if payroll is None:
            abort(404)
        jobs = OutworkerPayrollJob.query.filter_by(payroll_id=payroll.id).order_by(OutworkerPayrollJob.jobcard_id).all()
        return render_template("payroll_receipt.html", id=current_user.role, payroll=payroll, jobs=jobs)
