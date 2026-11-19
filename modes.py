from  flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime
import secrets

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
    contact_number = db.Column(db.String(10), nullable=True)
    enter_user = db.Column(db.String(50), nullable=False)

    @property
    def mobile(self):
        return self.contact_number if self.contact_number is not None else str(self.number)

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
    product_value_paise = db.Column(db.BigInteger, nullable=False, default=0, server_default='0')
    __table_args__ = (db.CheckConstraint('product_value_paise >= 0 AND product_value_paise <= 99999999999'),)

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

class ReturnBreakdown(db.Model):
    """Exact input used for one saved job-card return movement."""
    __tablename__ = "ReturnBreakdown"
    id = db.Column(db.Integer, primary_key=True)
    movement_id = db.Column(db.Integer, db.ForeignKey("JobmovementData.id"), nullable=False, unique=True, index=True)
    entry_method = db.Column(db.String(20), nullable=False)
    calculation_rows = db.Column(db.JSON, nullable=False, default=list)

class User(UserMixin, db.Model):
    __bind_key__ = 'users'
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    role = db.Column(db.Integer, nullable=False, default=2)  # 'userT' userP userB or 'admin'
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    auth_id = db.Column(db.String(64), nullable=False, unique=True,
                        default=lambda: secrets.token_hex(32))
    def get_id(self):
        return self.auth_id
    def revoke_sessions(self):
        self.auth_id = secrets.token_hex(32)
    def __init__(self,username,password,role):
        self.username =  username
        self.password =  generate_password_hash(password)
        self.role =  role
    def check_password(self,password):
        return check_password_hash(self.password,password)

class UserAccessLog(db.Model):
    __bind_key__ = 'users'
    __tablename__ = 'user_access_log'
    id = db.Column(db.Integer, primary_key=True)
    request_key = db.Column(db.String(64), nullable=False, unique=True)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    actor = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(30), nullable=False)
    old_role = db.Column(db.Integer)
    new_role = db.Column(db.Integer, nullable=False)
    payload_hash = db.Column(db.String(64))


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
    payload_hash = db.Column(db.String(64))
    receipt = db.Column(db.JSON)


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


class OutworkerRate(db.Model):
    __tablename__ = "outworker_rate"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("ItemData.id"), nullable=False)
    bundle_type = db.Column(db.String(50), nullable=False, default="")
    rate_units = db.Column(db.BigInteger, nullable=False)  # 1 rupee = 10,000 units
    updated_by = db.Column(db.String(100), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)
    __table_args__ = (
        db.UniqueConstraint("product_id", "bundle_type"),
        db.CheckConstraint("rate_units > 0"),
    )


class OutworkerAdvance(db.Model):
    __tablename__ = "outworker_advance"
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("OutworkData.id"), nullable=False, index=True)
    worker_name = db.Column(db.String(100), nullable=False)
    amount_paise = db.Column(db.BigInteger, nullable=False)
    paid_at = db.Column(db.DateTime, nullable=False)
    method = db.Column(db.String(20), nullable=False)
    reference = db.Column(db.String(100), nullable=False, default="")
    note = db.Column(db.String(500), nullable=False, default="")
    recorded_by = db.Column(db.String(100), nullable=False)
    __table_args__ = (db.CheckConstraint("amount_paise > 0"),)


class JobKeptProduct(db.Model):
    """Stock retained by an outworker, not a physical return or cash advance."""
    __tablename__ = 'job_kept_product'
    id = db.Column(db.Integer, primary_key=True)
    jobcard_id = db.Column(db.Integer, db.ForeignKey('JobcardData.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('ItemData.id'), nullable=False, index=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('OutworkData.id'), nullable=False, index=True)
    advance_id = db.Column(db.Integer, db.ForeignKey('outworker_advance.id'), nullable=False, unique=True)
    product_name = db.Column(db.String(50), nullable=False)
    bundle_type = db.Column(db.String(50), nullable=False)
    pieces = db.Column(db.Integer, nullable=False)
    unit_value_paise = db.Column(db.BigInteger, nullable=False)
    amount_paise = db.Column(db.BigInteger, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    recorded_by = db.Column(db.String(100), nullable=False)
    note = db.Column(db.String(500), nullable=False, default='')
    __table_args__ = (
        db.CheckConstraint('pieces > 0 AND pieces <= 1000000000'),
        db.CheckConstraint('unit_value_paise > 0 AND amount_paise > 0 AND amount_paise <= 99999999999'),
        db.CheckConstraint('amount_paise = pieces * unit_value_paise'),
    )


class OutworkerPayroll(db.Model):
    __tablename__ = "outworker_payroll"
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("OutworkData.id"), nullable=False, index=True)
    worker_name = db.Column(db.String(100), nullable=False)
    gross_paise = db.Column(db.BigInteger, nullable=False)
    deduction_paise = db.Column(db.BigInteger, nullable=False)
    net_paise = db.Column(db.BigInteger, nullable=False)
    paid_at = db.Column(db.DateTime, nullable=False)
    method = db.Column(db.String(20), nullable=False)
    reference = db.Column(db.String(100), nullable=False, default="")
    note = db.Column(db.String(500), nullable=False, default="")
    recorded_by = db.Column(db.String(100), nullable=False)
    receipt_archive = db.Column(db.JSON, nullable=True)
    __table_args__ = (
        db.CheckConstraint("gross_paise >= 0 AND deduction_paise >= 0 AND net_paise >= 0"),
        db.CheckConstraint("gross_paise = deduction_paise + net_paise"),
    )


class OutworkerAdvanceReceipt(db.Model):
    """Money actually received back, independent of a payroll deduction."""
    __tablename__ = "outworker_advance_receipt"
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("OutworkData.id"), nullable=False, index=True)
    advance_id = db.Column(db.Integer, db.ForeignKey("outworker_advance.id"), nullable=False, index=True)
    worker_name = db.Column(db.String(100), nullable=False)
    amount_paise = db.Column(db.BigInteger, nullable=False)
    received_at = db.Column(db.DateTime, nullable=False)
    method = db.Column(db.String(20), nullable=False)
    reference = db.Column(db.String(100), nullable=False, default="")
    note = db.Column(db.String(500), nullable=False, default="")
    recorded_by = db.Column(db.String(100), nullable=False)
    __table_args__ = (db.CheckConstraint("amount_paise > 0"),)


class OutworkerAdvanceRecovery(db.Model):
    __tablename__ = "outworker_advance_recovery"
    id = db.Column(db.Integer, primary_key=True)
    payroll_id = db.Column(db.Integer, db.ForeignKey("outworker_payroll.id"), nullable=False, index=True)
    advance_id = db.Column(db.Integer, db.ForeignKey("outworker_advance.id"), nullable=False, index=True)
    amount_paise = db.Column(db.BigInteger, nullable=False)
    __table_args__ = (db.UniqueConstraint('payroll_id', 'advance_id'),
                      db.CheckConstraint('amount_paise > 0'))


class OutworkerPayrollJob(db.Model):
    __tablename__ = "outworker_payroll_job"
    id = db.Column(db.Integer, primary_key=True)
    payroll_id = db.Column(db.Integer, db.ForeignKey("outworker_payroll.id"), nullable=False, index=True)
    jobcard_id = db.Column(db.Integer, db.ForeignKey("JobcardData.id"), nullable=False, index=True)
    pieces = db.Column(db.Integer, nullable=False)
    amount_paise = db.Column(db.BigInteger, nullable=False)
    lines = db.Column(db.JSON, nullable=False)
    __table_args__ = (db.UniqueConstraint('payroll_id', 'jobcard_id'),)



