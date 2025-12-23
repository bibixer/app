from  flask_sqlalchemy import SQLAlchemy

db =  SQLAlchemy()

class Bundle(db.Model):
    __tablename__ = "Bundle"
    id = db.Column(db.Integer, primary_key=True)
    entry_datetime = db.Column(db.DateTime, nullable=False)

    lump_id = db.Column(
        db.Integer,
        nullable=False
    )

    pieces = db.Column(db.Integer, nullable=False)
    kg = db.Column(db.Float, nullable=False)

    # given to master
    given_to = db.Column(db.String(50), nullable=True)
    # given by
    given_by = db.Column(db.Integer, nullable=True)
    # given_date
    given_date =  db.Column(db.DateTime,nullable=True)
    # return list (date + pieces returned + entery by)
    return_list = db.Column(db.JSON, default=list)

    # status
    complete = db.Column(db.Boolean, default=False)
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

