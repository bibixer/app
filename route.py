from functools import wraps
from flask import flash, render_template, redirect, url_for,session,request, jsonify
from form import Lump_data, bundle_invadata, Item_data, Outworker_form, Cutter_form, Return_form, Login_form, Date_form, Date_form_with_name,bale_data_form,party_name,Find_and_edit,EditEntryForm
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from data_entry import add_cutter,add_items,add_outworker_db,add_jobcard,add_manual_jobcard,in_move_entery,bale_data_entry,add_party
from data_Process import get_serch_data, get_job_card_data_creation, get_jobcard_return_data, get_jobcard_ledger, \
    get_current_week_range, home_dashboard,get_cutter_report_data,outworker_name,outworker_job_ledger,product_data,find_edit_data
from modes import User, Jobcard, Item_data as ProductModel
from edit_service import ENTITY_CONFIG, edit_context, save_entry, audit_logs, search_entries
from item_aliases import resolve_item_name, item_name_mapping
from master_aliases import master_name_mapping, master_name_options
from bundle_types import BUNDLE_TYPE_CHOICES
from return_reconciliation import unassigned_returns, assign_return
from data_Process import outworker_period_account
from payroll_routes import register_payroll_routes
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

    def oly_admin(func):
        @wraps(func)
        def admin_(*args, **kwargs):
            try:
                if not current_user.is_authenticated:
                    flash("Login required")
                    return redirect(url_for("login"))  # change to your login route name

                if current_user.role != 1:
                    flash("Admin access only")
                    return redirect(url_for("home"))  # change to your home route name

                return func(*args, **kwargs)

            except Exception as e:
                print("Admin decorator error:", e)
                return redirect(url_for("home"))

        return admin_

    register_payroll_routes(app, oly_admin)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
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
            reset_session(2)
            if result == 404:
                flash("you do not have rights", "success")
                return redirect(url_for("lump_home"))
            elif result == 409:
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
    @oly_admin
    def job_card():
        job_card_data_c = get_job_card_data_creation()
        return render_template("jobcard.html",id=current_user.role,data = job_card_data_c)

    @app.route("/manual_jobcard")
    @login_required
    @oly_admin
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
    @oly_admin
    def submit_manual_jobcard():
        data = request.get_json()
        result = add_manual_jobcard(
            data, current_user,
            data.get("request_id") if isinstance(data, dict) else None,
        )
        if isinstance(result, dict):
            if result.get("code") == 101:
                return jsonify(success=True, message="Manual job card saved", jobData=result["jobData"])
        if result == 401:
            return jsonify(success=False, code=401, message="Master name was not found."), 400
        if result == 405:
            return jsonify(success=False, code=405, message="Manual job-card data is invalid."), 400
        if result == 406:
            return jsonify(success=False, code=406, message="Item name or alias was not found. Add the product in Item Setup first."), 400
        if result == 409:
            return jsonify(success=True, duplicate=True, message="Duplicate request ignored; job card already saved.")
        return jsonify(success=False, code=500, message="Manual job card could not be saved."), 500
    @app.route("/add_items", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def add_item():
        form_name = "Item setup"
        current_form = Item_data()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            token = data.pop("submission_token")
            items = add_items(data,current_user,token)
            if items == 101 :
                flash(f"You have successfully added  {data['name']} .", "success")
                return redirect(url_for("add_item"))
            elif items == 409:
                flash("Duplicate request ignored; this product was already submitted.", "warning")
                return redirect(url_for("add_item"))
            elif isinstance(items, dict) and items.get("or") is False:
                message = str(items["exception"]) if isinstance(items["exception"], ValueError) else "Could not save item. Check for a duplicate name or alias."
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
                message = str(outworker["exception"]) if isinstance(outworker["exception"], ValueError) else "Could not save master. Check for a duplicate alias."
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

        data = request.get_json()
        ok = add_jobcard(data,current_user,data.get("request_id") if isinstance(data, dict) else None)
        # print(ok)
        if type(ok) == dict:
            if ok["code"] == 101:
                return jsonify(success=True, message="Data saved", jobData=ok["jobData"])
        elif ok ==401:
            return jsonify(success=False, message="Master name not found. Check spelling or turn off Caps Lock (scanner), or enter manually. ")
        elif ok == 403:
            return jsonify(success=False, message="product do not mach data base data base ")
        elif ok == 405:
            return jsonify(success=False, message="send data not right ")
        elif ok == 409:
            return jsonify(success=True, duplicate=True, message="Duplicate request ignored; job card already saved.")
    @app.route("/retune_product", methods=["GET", "POST"])
    @login_required
    @oly_admin
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
        return render_template("return_lookup.html", current_form=current_form, id=current_user.role)
    @app.route("/job_retun", methods=["GET", "POST"])
    @login_required
    @oly_admin
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
        return render_template("job_retun.html",data=data,id=current_user.role)
    @app.route("/jobcard/ledger")
    @login_required
    @oly_admin
    def jobcard_ledger_lookup():
        error = None
        if "jobcard_id" in request.args:
            raw_id = request.args.get("jobcard_id", "").strip()
            if not raw_id.isdecimal() or int(raw_id) < 1:
                error = "Enter a valid job card number."
            elif db.session.get(Jobcard, int(raw_id)) is None:
                error = f"Job card #{raw_id} was not found."
            else:
                return redirect(url_for("jobcard_ledger", jobcard_id=int(raw_id)))
        return render_template("jobcard_ledger_lookup.html", id=current_user.role, error=error)
    @app.route("/jobcard/<int:jobcard_id>/ledger")
    @login_required
    @oly_admin
    def jobcard_ledger(jobcard_id):
        detail = get_jobcard_ledger(jobcard_id)
        if detail is None:
            return "Job card not found.", 404
        return render_template("jobcard_ledger.html", detail=detail, id=current_user.role)
    @app.route("/summit-retune", methods=["POST"])
    @login_required
    @oly_admin
    def summit_retune():
        data = request.get_json()

        res = in_move_entery(data,current_user,data.get("request_id") if isinstance(data, dict) else None)
        # print(res)
        if type(res) == dict:
            if res["code"] == 101:
             # print(res)
                return jsonify(success=True, message="Data saved",jobData=res)
        elif res  == 404 :
            return jsonify(success=False, message="Data not  saved iisue",code=404)
        elif res == 401:
            return jsonify(success=False, message="name of master not in data base ",code=401)
        elif res == 403:
            return jsonify(success=False, message="item do not macha base ",code=403)
        elif res == 405:
            return jsonify(success=False, message="send data not right ",code=405)
        elif res == 4033:
            return jsonify(success=False, message="Return exceeds the remaining balance on this job card. Refresh and try again.", code=4033), 409
        elif res == 409:
            return jsonify(success=True, duplicate=True, message="Duplicate return request ignored.", code=409)
        else:
            return jsonify(success=False, message="item do not macha base ", code=res)
    @app.route("/admin_dashord", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def admin_dashord():
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
                login_user(user)
                return redirect("/")
            else:
                flash("Username or password is incorrect.", "danger")
        elif request.method == "POST":
            if name_from.csrf_token.errors:
                flash("This login form expired. Reload the page and try again.", "warning")
            else:
                flash("Enter both a username and password.", "warning")

        return render_template('user.html', form_name="Login",
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
            "edit_index.html", entities=ENTITY_CONFIG, id=current_user.role,
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
