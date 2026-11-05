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
    type_B = db.Column(db.String(50), nullable=False)
    # given to master
    given_to = db.Column(db.String(50), nullable=True)
    # given by
    given_by = db.Column(db.String(50), nullable=True)
    # given_date
    given_date =  db.Column(db.DateTime,nullable=True)
    # READY → Bundle is in shop → Can send
    # GIVEN → Bundle is outside → Cannot use
    status =  db.Column(db.String(50), nullable=False,default='READY')
    # # status
    s_no = db.Column(db.Integer, nullable=False,default=10505)
    # complete = db.Column(db.Boolean, default=False)
    def to_dict(self,cuter,no_of_so):
        return {
            "id":self.id,
            "entry_datetime":self.entry_datetime,
            "lump_id":self.lump_id,
            "product":self.product,
            "color":self.color,
            "pieces":self.pieces,
            "kg":self.kg,
            'type_B':self.type_B,
            'no_of_so':no_of_so,
            "OR_code":f"{self.id}--{self.product}--{self.color}--{self.pieces}",
            "cutter":cuter
        }

    def to_dict_2(self,cutter):
        return {
            "id":self.id,
            "entry_datetime":self.entry_datetime,
            "lump_id":self.lump_id,
            "product":self.product,
            "pieces":self.pieces,
            "kg":self.kg,
            'type_B':self.type_B,
            'given_to': self.given_to,
          'given_by' : self.given_by,
          'given_date': self.given_date,
        'status' : self.status,
            "cutter": cutter


        }
class Lump(db.Model):
    __tablename__ = "LumpData"
    id = db.Column(db.Integer, primary_key=True)
    # Store both date + time
    entry_datetime = db.Column(db.DateTime, nullable=False)
    bale_id = db.Column(db.Integer, nullable=False,default=0)
    # entery by
    enter_user = db.Column(db.String(50), nullable=False)
    # worker
    cut_by = db.Column(db.String(50), nullable=False)

    # bundle details
    bundle_type = db.Column(db.String(20), nullable=False)   # good_cut | fant | lump | uncut
    product = db.Column(db.String(100), nullable=False)
    # meter in blundel
    meters = db.Column(db.Float, nullable=False)
    meters_add_remove = db.Column(db.Float, nullable=False)
    color = db.Column(db.String(100))
    number_of_bundlie = db.Column(db.Integer, nullable=False)
class Cuter(db.Model):
    __tablename__ = "CutData"
    id = db.Column(db.Integer, primary_key=True)
    name =  db.Column(db.String(50), nullable=False,unique=True)
    enter_user = db.Column(db.String(50), nullable=False)

class Outworker(db.Model):
    __tablename__ = "OutworkData"
    id = db.Column(db.Integer, primary_key=True,unique=True)
    name = db.Column(db.String(50), nullable=False)
    adders = db.Column(db.String(50), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    enter_user = db.Column(db.String(50), nullable=False)

class OutworkerAlias(db.Model):
    __tablename__ = "OutworkerAlias"
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("OutworkData.id"), nullable=False, index=True)
    alias = db.Column(db.String(50), nullable=False, unique=True)
    worker = db.relationship("Outworker", backref=db.backref("alias_rows", lazy=True))

class Item_data(db.Model):
    __tablename__ = "ItemData"
    id = db.Column(db.Integer, primary_key=True)
    name =  db.Column(db.String(50), nullable=False,unique=True)
    meters = db.Column(db.Float, nullable=False)
    size = db.Column(db.Float(50), nullable=False)
    enter_user = db.Column(db.String(50), nullable=False)

class ItemAlias(db.Model):
    __tablename__ = "ItemAlias"
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("ItemData.id"), nullable=False, index=True)
    alias = db.Column(db.String(50), nullable=False, unique=True)
    item = db.relationship("Item_data", backref=db.backref("alias_rows", lazy=True))

class Jobcard(db.Model):
    __tablename__ = "JobcardData"
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    given_to = db.Column(db.String(100), nullable=False)
    # told_by = db.Column(db.String(50), nullable=False)
    # given by
    given_by = db.Column(db.String(50), nullable=False)
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
    enter_user = db.Column(db.String(50), nullable=False)
    type_B=db.Column(db.String(50), nullable=False)
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
    role = db.Column(db.Integer, nullable=False, default=2)  # 'userT' userP userB or 'admin'
    def __init__(self,username,password,role):
        self.username =  username
        self.password =  generate_password_hash(password)
        self.role =  role
    def check_password(self,password):
        return check_password_hash(self.password,password)

class Bale_date(db.Model):
    __tablename__ = "BaleDate"
    id = db.Column(db.Integer, primary_key=True)
    part_name = db.Column(db.String(50), nullable=False)
    lot_number = db.Column(db.Integer, nullable=False)
    lot_count =db.Column(db.Integer, nullable=False)
    bale_number = db.Column(db.Integer, nullable=False)
    bale_date = db.Column(db.DateTime, nullable=False)
    enter_user = db.Column(db.String(50), nullable=False)
    # worker
    cut_by = db.Column(db.String(50), nullable=False)
    product = db.Column(db.String(50), nullable=False)
    # lump_ids = db.Column(db.JSON, nullable=False)

class Party(db.Model):
    __tablename__ = "party"
    id = db.Column(db.Integer, primary_key=True)
    name =  db.Column(db.String(50), nullable=False,unique=True)
    enter_user = db.Column(db.String(50), nullable=False)


class RequestDedup(db.Model):
    """One row per client write request.

    The unique key is the database-level guard against two workers accepting the
    same browser submission at the same time.
    """
    __tablename__ = "request_dedup"
    id = db.Column(db.Integer, primary_key=True)
    request_key = db.Column(db.String(128), nullable=False, unique=True, index=True)
    endpoint = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)


class EditLog(db.Model):
    """Append-only audit history for every edit made from the admin UI."""
    __tablename__ = "edit_log"
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(50), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    action = db.Column(db.String(30), nullable=False, default="UPDATE")
    old_values = db.Column(db.JSON, nullable=False)
    new_values = db.Column(db.JSON, nullable=False)
    changed_fields = db.Column(db.JSON, nullable=False)
    username = db.Column(db.String(100), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False)



