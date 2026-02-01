from flask import flash, render_template, redirect, url_for,session
from form import Lump_data,bundle_invadata,Item_data,Outworker_form,Cutter_form

from data_entry import add_data_lump,add_cutter,add_items,add_outworker_db
from data_Process import get_serch_data,get_job_card_data_creation

def reset_session():
    for key in list(session.keys()):
        if key != 'csrf_token':
            session.pop(key)

def register_routes(app):

    @app.route("/lumpentry", methods=["GET", "POST"])
    def lump_home():
        
        form_name = "lump entry"
        current_form = Lump_data()
        # data to auto fill
        data_autofill = get_serch_data()
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
        print(data_autofill)
        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form,
            data=data_autofill
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
    @app.route("/", methods=["GET", "POST"])
    def job_card():
        job_card_data_c = get_job_card_data_creation()
        return render_template("jobcard.html",data = job_card_data_c)
    @app.route("/add_items", methods=["GET", "POST"])
    def add_item():
        form_name = "add new produdcts"
        current_form = Item_data()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            items = add_items(data)
            if items == 101 :
                flash(f"You have successfully added  {data['name']} .", "success")
                return redirect(url_for("add_item"))
            elif  items["or"] == False :
                flash(f"call  badx {items['exception']}")
                return redirect(url_for("add_item"))

        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form
        )

    @app.route("/add_outworver", methods=["GET", "POST"])
    def add_outworker():
        form_name = "new outworver"
        current_form = Outworker_form()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            outworker = add_outworker_db(data)
            if outworker == 101 :
                flash(f"You have successfully added  {data['name']} .", "success")
                return redirect(url_for("add_outworker"))
            elif outworker['or'] == False :
                flash(f"call  badx{outworker['exception']}")
                return redirect(url_for("add_outworker"))

        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form
        )

    @app.route("/add_cutter", methods=["GET", "POST"])
    def add_cuter():
        form_name = "new cutter"
        current_form = Cutter_form()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            add_cu = add_cutter(data)
            if add_cu == 101 :
                flash(f"You have successfully added  {data['name']} cutter.", "success")
                return redirect(url_for("add_cuter"))
            elif  add_cu["or"] == False :
                flash(f"call  badx{add_cu["exception"]}")

                return redirect(url_for("add_cuter"))
        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form
        )
    @app.route("/job_retun", methods=["GET", "POST"])
    def job_retun():
        return render_template("job_retun.html")