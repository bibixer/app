from flask import flash, render_template, redirect, url_for,request,session
from form import Lump_data,bundle_invadata
from data_entry import add_data_lump

def reset_session():
    for key in list(session.keys()):
        if key != 'csrf_token':
            session.pop(key)

def register_routes(app):

    @app.route("/", methods=["GET", "POST"])
    def lump_home():
        
        form_name = "lump entry"
        current_form = Lump_data()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            data.pop("csrf_token", None)
            if data['numbers_of_bundles'] > 6:
                flash("you can not enter more then 6")
                return redirect(url_for("lump_home"))

            # 🔄 reset any old flow
            reset_session()

            # 🚀 initialize bundle workflow
            session["bundle_data"] = data
            session["current_bundle"] = 1
            session["bundles"] = {}

            return redirect(url_for("bundle_entery"))

        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form
        )

    @app.route("/bundle_entery", methods=["GET", "POST"])
    def bundle_entery():

        # 🔐 Guard: block direct access / broken session
        if (
                "bundle_data" not in session
                or "current_bundle" not in session
                or "bundles" not in session
        ):
            return redirect(url_for("lump_home"))

        total = int(session["bundle_data"]["numbers_of_bundles"])
        current = int(session["current_bundle"])

        # ✅ All bundles completed
        if current > total:
            print('ok')
            all_data = {
                "main": session["bundle_data"],
                "bundles": session["bundles"]
            }
            add_data_lump(all_data,1)

            reset_session()
            flash("You have successfully entered the bundle.", "success")
            return redirect(url_for("lump_home"))

        form_name = f"Bundle Entry ({current}/{total})"
        current_form = bundle_invadata()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            data.pop("csrf_token", None)

            # ⚠️ use string keys for session safety
            session["bundles"][str(current)] = data
            session["current_bundle"] = current + 1

            return redirect(url_for("bundle_entery"))

        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form
        )
