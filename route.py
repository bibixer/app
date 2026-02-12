from flask import flash, render_template, redirect, url_for,session,request, jsonify
from form import Lump_data,bundle_invadata,Item_data,Outworker_form,Cutter_form,Return_form,Login_form
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from data_entry import add_data_lump,add_cutter,add_items,add_outworker_db,add_jobcard,in_move_entery
from data_Process import get_serch_data,get_job_card_data_creation,get_retun_card_data,get_movemet_data
from modes import User
def reset_session():
    for key in list(session.keys()):
        if key != 'csrf_token':
            session.pop(key)

def register_routes(app,db):
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.route("/lumpentry", methods=["GET", "POST"])
    def lump_home():
        
        form_name = "lump entry"
        current_form = Lump_data()
        # data to auto fill
        data_autofill = get_serch_data()
        if current_form.validate_on_submit():
            data = current_form.data.copy()
            if current_form.cuter_name.data not in data_autofill["cuter_data"]:
                flash("select cutter name from blow","warning")
                return redirect(url_for("lump_home"))
            if current_form.product_name.data not in data_autofill["product_data"]:
                flash("select product name from blow","warning")
                return redirect(url_for("lump_home"))
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
    @app.route("/jobcard", methods=["GET", "POST"])
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
    @app.route("/submit-jobcard",methods=["POST"])
    def submit_jobcard():
        data = request.get_json()
        ok = add_jobcard(data)
        if ok == 101 :
            return  jsonify(success=True, message="Data saved")
        elif ok ==401:
            return jsonify(success=False, message="name of master not in data base ")
        elif ok == 403:
            return jsonify(success=False, message="product do not mach data base data base ")
        elif ok == 405:
            return jsonify(success=False, message="send data not right ")
    @app.route("/retune_product", methods=["GET", "POST"])
    def retune_product():
        form_name = "retune product"
        current_form =  Return_form()
        data_r =  get_retun_card_data()
        ok =  request.args.get("ok",type=int)
        if ok == 101 :
            flash("ok done date save")
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
                               current_form=current_form,data_r=data_r)
    @app.route("/job_retun", methods=["GET", "POST"])
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
        return render_template("job_retun.html",data=data)
    @app.route("/summit-retune", methods=["POST"])
    def summit_retune():
        data = request.get_json()
        res = in_move_entery(data)
        if res == 101 :
         return jsonify(success=True, message="Data saved")
        elif res  == 404 :
            return jsonify(success=False, message="Data not  saved iisue")
        elif res == 401:
            return jsonify(success=False, message="name of master not in data base ")
        elif res == 403:
            return jsonify(success=False, message="item do not macha base ")
        elif res == 405:
            return jsonify(success=False, message="send data not right ")

    @app.route("/")
    @login_required
    def home():
        if current_user.role == 4:
            return redirect("/admin_dashord")
        elif current_user.role == 2:
            return redirect("/lumpentry")

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