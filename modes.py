from  flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

db =  SQLAlchemy()

class Bundle(db.Model):
    __tablename__ = "Bundle"
    id = db.Column(db.Integer, primary_key=True)
    entry_datetime = db.Column(db.DateTime, nullable=False)

    lump_id = db.Column(
        db.Integer,
        nullable=False
    )
    product = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(50), nullable=False)
    pieces = db.Column(db.Integer, nullable=False)
    kg = db.Column(db.Float, nullable=False)

    # given to master
    given_to = db.Column(db.String(50), nullable=True)
    # given by
    given_by = db.Column(db.Integer, nullable=True)
    # given_date
    given_date =  db.Column(db.DateTime,nullable=True)
    # READY → Bundle is in shop → Can send
    # GIVEN → Bundle is outside → Cannot use
    status =  db.Column(db.String(50), nullable=False,default='READY')
    # # status
    # complete = db.Column(db.Boolean, default=False)
class Lump(db.Model):
    __tablename__ = "LumpData"
    id = db.Column(db.Integer, primary_key=True)

    # Store both date + time
    entry_datetime = db.Column(db.DateTime, nullable=False)

    # entery by
    enter_user = db.Column(db.Integer, nullable=False)
    # worker
    cut_by = db.Column(db.String(50), nullable=False)

    # bundle details
    bundle_type = db.Column(db.String(20), nullable=False)   # good_cut | fant | lump | uncut
    product = db.Column(db.String(100), nullable=False)
    # meter in blundel
    meters = db.Column(db.Float, nullable=False)
    color = db.Column(db.String(100))
    number_of_bundlie = db.Column(db.Integer, nullable=False)
class Cuter(db.Model):
    __tablename__ = "CutData"
    id = db.Column(db.Integer, primary_key=True)
    name =  db.Column(db.String(50), nullable=False)

class Outworker(db.Model):
    __tablename__ = "OutworkData"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    adders = db.Column(db.String(50), nullable=False)
    number = db.Column(db.Integer, nullable=False)
class Item_data(db.Model):
    __tablename__ = "ItemData"
    id = db.Column(db.Integer, primary_key=True)
    name =  db.Column(db.String(50), nullable=False)
    meters = db.Column(db.Float, nullable=False)
    size = db.Column(db.Float(50), nullable=False)

class Jobcard(db.Model):
    __tablename__ = "JobcardData"
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    given_to = db.Column(db.Integer, nullable=False)
    # told_by = db.Column(db.String(50), nullable=False)
    # given by
    given_by = db.Column(db.Integer, nullable=False)
    product_list = db.Column(db.JSON, nullable=False)

class Jobmovement(db.Model):
    __tablename__ = "JobmovementData"
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    jobcard = db.Column(db.String(50))
    bundle = db.Column(db.String(50))
    partculer = db.Column(db.String(50), nullable=False)
    product_name = db.Column(db.String(50), nullable=False)
    name_of_mater = db.Column(db.String(50), nullable=False)
    enter_user = db.Column(db.Integer, nullable=False)
    # IN
    # OUT
    flow_type = db.Column(db.String(50), nullable=False)
    outflow = db.Column(db.Integer, default=0)
    inflow = db.Column(db.Integer, default=0)
    def to_dict(self):
        return {
            "id":self.id,
            "date":self.date,
            "jobcard":self.jobcard,
            "bundle":self.bundle,
            "partculer":self.partculer,
            "product_name":self.product_name,
            "name_of_mater":self.name_of_mater,
            "enter_user":self.enter_user,
            "flow_type":self.flow_type,
            "outflow":self.outflow,
            "inflow":self.inflow

        }

class User(UserMixin, db.Model):
    __bind_key__ = 'users'
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    role = db.Column(db.Integer, nullable=False, default=1)  # 'userT' userP userB or 'admin'
    def __init__(self,username,password,role):
        self.username =  username
        self.password =  generate_password_hash(password)
        self.role =  role
    def check_password(self,password):
        return check_password_hash(self.password,password)


