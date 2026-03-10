from functools import wraps

from flask import flash, render_template, redirect, url_for,session,request, jsonify
from form import Lump_data, bundle_invadata, Item_data, Outworker_form, Cutter_form, Return_form, Login_form, Date_form, Date_form_with_name,bale_data_form,party_name
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from data_entry import add_cutter,add_items,add_outworker_db,add_jobcard,in_move_entery,bale_data_entry,add_party
from data_Process import get_serch_data, get_job_card_data_creation, get_retun_card_data, get_movemet_data, \
    get_current_week_range, home_dashboard,get_cutter_report_data,outworker_name,master_report_card,product_data
from modes import User
def reset_session(flow:int):
    # remove all bale lever1
    # remove all lump  vevel
    if flow== 1:
        keys_roremove =  ["bundle_data","current_bundle","bundles","sno","bale_data","current_lump","sno_lump"]
    if flow == 2:
        keys_roremove = ["bundle_data", "current_bundle", "bundles", "sno"]
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
            if current_form.product_name.data not in data_autofill["product_data"]:
                flash("select product name from blow","warning")
                return redirect(url_for("bale_entery"))
            if current_form.party_name.data not in data_autofill["party_data"]:
                flash("select party name from blow","warning")
                return redirect(url_for("bale_entery"))

            ### do some date vlaidation

        ## data prosessing
            data =  current_form.data
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
            if current_form.cuter_name.data not in data_autofill["cuter_data"]:
                flash("select cutter name from blow","warning")
                return redirect(url_for("lump_home"))
            if current_form.product_name.data not in data_autofill["product_data"]:
                flash("select product name from blow","warning")
                return redirect(url_for("lump_home"))
            if current_form.party_name.data not in data_autofill["party_data"]:
                flash("select party name from blow","warning")
                return redirect(url_for("lump_home"))
            data.pop("csrf_token", None)

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
            bale_data_entry(all_data, current_user)
            reset_session(2)
            flash("You have successfully entered the bundle.", "success")
            return redirect(url_for("lump_home"))


        form_name = f"Bundle Entry ({current}/{total})"
        current_form = bundle_invadata()
        if not current_form.validate_on_submit():
            if session['sno'] != 0:
                current_form.no_of_so.data = session['sno'] +1


        if current_form.validate_on_submit():
            data = current_form.data.copy()
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
    @app.route("/add_items", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def add_item():
        form_name = "add new produdcts"
        current_form = Item_data()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            items = add_items(data,current_user)
            if items == 101 :
                flash(f"You have successfully added  {data['name']} .", "success")
                return redirect(url_for("add_item"))
            elif  items["or"] == False :
                flash(f"call  badx {items['exception']}")
                return redirect(url_for("add_item"))

        return render_template(
            "user.html",
            form_name=form_name,
            current_form=current_form,id=current_user.role
        )
    @app.route("/add_suppy", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def add_suppy():
        form_name = "add new suppy"
        current_form = party_name()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            party = add_party(data, current_user)
            if party == 101:
                flash(f"You have successfully added  {data['name']} .", "success")
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
        form_name = "new outworver"
        current_form = Outworker_form()

        if current_form.validate_on_submit():
            data = current_form.data.copy()
            outworker = add_outworker_db(data,current_user)
            if outworker == 101 :
                flash(f"You have successfully added  {data['name']} .", "success")
                return redirect(url_for("add_outworker"))
            elif outworker['or'] == False :
                flash(f"call  badx{outworker['exception']}")
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
            add_cu = add_cutter(data,current_user)
            if add_cu == 101 :
                flash(f"You have successfully added  {data['name']} cutter.", "success")
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
        ok = add_jobcard(data,current_user)
        # print(ok)
        if ok["code"] == 101 :
            return  jsonify(success=True, message="Data saved",jobData=ok["jobData"])
        elif ok ==401:
            return jsonify(success=False, message="name of master not in data base ")
        elif ok == 403:
            return jsonify(success=False, message="product do not mach data base data base ")
        elif ok == 405:
            return jsonify(success=False, message="send data not right ")
    @app.route("/retune_product", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def retune_product():
        form_name = "retune product"
        current_form =  Return_form()
        data_r =  get_retun_card_data()
        ok =  request.args.get("ok",type=int)
        if ok == 101 :
            flash("ok done Data saved ")
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
            if str(current_form.name.data) in data_r["outworker"] :
                return redirect(url_for("job_retun",name_master=current_form.name.data))

            else:
                flash("Select for the blow ")
                return redirect(url_for("retune_product"))

        return render_template("user.html",
                               form_name=form_name,
                               current_form=current_form,data_r=data_r,id=current_user.role)
    @app.route("/job_retun", methods=["GET", "POST"])
    @login_required
    @oly_admin
    def job_retun():
        name_of_master =  request.args.get("name_master",type=str)
        if not name_of_master:
            flash("need_master_name")
            return redirect(url_for("retune_product"))
        data = get_movemet_data(name_of_master)
        if data == 404:
            flash(f"{name_of_master} not exist in job movement")
            return redirect(url_for("retune_product"))
        if data['items'] == []:
            flash("no product given ")
            return redirect(url_for("retune_product"))
        return render_template("job_retun.html",data=data,id=current_user.role)
    @app.route("/summit-retune", methods=["POST"])
    @login_required
    @oly_admin
    def summit_retune():
        data = request.get_json()
        res = in_move_entery(data,current_user)
        if res["code"] == 101 :
         # print(res)
         return jsonify(success=True, message="Data saved",jobData=res)
        elif res  == 404 :
            return jsonify(success=False, message="Data not  saved iisue")
        elif res == 401:
            return jsonify(success=False, message="name of master not in data base ")
        elif res == 403:
            return jsonify(success=False, message="item do not macha base ")
        elif res == 405:
            return jsonify(success=False, message="send data not right ")
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
        dash_bord_data = home_dashboard(date_from)
        if dash_bord_data == "invalid_range":
            flash("⚠️ 'From Date' cannot be after 'To Date'.", "danger")
            return redirect(url_for("admin_dashord"))
        return render_template("admin.html",date_from=date_from,type="DASHBORD", outflow_data=dash_bord_data["outflow_pie"],inflow_data=dash_bord_data["inflow_pie"],dash_bord_data=dash_bord_data)
    @app.route("/cutter_report",methods=["GET", "POST"])
    @login_required
    # @oly_admin
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
    # @oly_admin
    def outworker_report():
        name_data_form = Date_form_with_name()
        range_data = get_current_week_range()
        outworker_name_data =  outworker_name(oly_full_name=True)
        if not name_data_form.is_submitted():
            name_data_form.date_from.data = range_data["from_date"].date()
            name_data_form.date_to.data = range_data["to_date"].date()
            name_data_form.name.render_kw = {
                'placeholder': 'Enter outworker Name',"id":"name_f"
            }
        if name_data_form.validate_on_submit():
            data = name_data_form.data.copy()
            if data["name"] not in outworker_name_data:
                flash("ented name not in list", "danger")
                return redirect(url_for("outworker_report"))
            if data["date_from"] >  data['date_to']:
                flash("date range is wong  data from is gater then date to", "danger")
                return redirect(url_for("outworker_report"))

            report =  master_report_card(data,current_user)
            if report == 404:
                flash("user not allowed", "danger")

                return redirect(url_for("outworker_report"))
            elif report == 402:
                flash("ented name not in databases", "danger")
                return redirect(url_for("outworker_report"))
            elif report == 403:
                flash("no flow for the name", "danger")
                return redirect(url_for("outworker_report"))
            return render_template("admin.html", date_from=name_data_form, type="OUTWOKER_Report",
                                   name=outworker_name_data,backend_data=report)

        return render_template("admin.html", date_from=name_data_form, type="OUTWOKER_Report", name=outworker_name_data)

    @app.route("/product_report", methods=["GET", "POST"])
    @login_required
    # @oly_admin
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
            user = User.query.filter_by(username=name_from.user_name.data).first()
            if user and user.check_password(name_from.password.data):
                login_user(user)
                return redirect("/")
            else:
                flash("Invalid credentials")

        return render_template('user.html', form_name="Login",
            current_form=name_from)

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))
    # laber print done