from modes import db, Bundle, Lump, Cuter, Item_data, Outworker,Jobcard,Jobmovement
from datetime import datetime
import re

def add_data_to_database(data):
    db.session.add(data)
    db.session.commit()
    return 101
def add_data_lump(data,current_user):
    # try:
        lump_data = data['main']
        lump = Lump(
            entry_datetime = datetime.now(),
            enter_user = current_user,
            cut_by = lump_data['cuter_name'],
            bundle_type = lump_data['bundle_type'],
            product = lump_data['product_name'],
            meters = lump_data['meters'],
            color = lump_data['colors'],
            number_of_bundlie = lump_data['numbers_of_bundles']

        )
        db.session.add(lump)
        db.session.commit()
        add_bundle(data,lump.id)
    # except:
def add_bundle(data,lump_id):
    bundle_data = data['bundles']
    for key in bundle_data.keys():
        b =  data['bundles'][key]
        bundle = Bundle(
            entry_datetime = datetime.now(),
            lump_id = lump_id,
            pieces = b['no_of_pics'],
            kg= b['kg_of_bundle'],
            product = data["main"]['product_name'],
            color = data["main"]['colors'],
        )
        db.session.add(bundle)
        db.session.commit()

def error_hendle(func):
    def eror(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return {"or":False,"exception":e}
    return eror

@error_hendle
def add_cutter(data):
        cuuter = Cuter(name=data["name"].upper())
        return add_data_to_database(cuuter)

@error_hendle
def add_items(data):
    item =  Item_data(name=data["name"].upper()
    ,size = data["size"]
    ,meters = data["meter"]
    )
    return add_data_to_database(item)

@error_hendle
def add_outworker_db(data):
    outworker = Outworker(name=data["name"].upper(),
                          adders= data["address"],
                          number = data["number"]
                          )
    return add_data_to_database(outworker)

# @error_hendle
def add_jobcard(data):
    job_card = Jobcard(
    date = datetime.now(),
    given_to = data["customer"],
    given_by =  "badx",
    product_list = data['items']
    )
    db.session.add(job_card)
    db.session.commit()
    add_job_movemet_out(data,job_card.id)
    return 101

def add_job_movemet_out(data,job_id):
    for item in data['items']:
        job_movement = Jobmovement(
        date = datetime.now(),
        jobcard = job_id,
        bundle = item["item_id"],
        outflow = item["qty"],
        name_of_mater =  data["customer"],
        enter_user = 1 ,
        partculer = f'given {item["name_of_prduct"]} to '
                    f'{data["customer"] } toatal pic {item["qty"] } '
                    f'with job_id {job_id} '
        ,product_name = item["name_of_prduct"],
        flow_type = "OUT"
    )
        db.session.add(job_movement)
        db.session.commit()
        update_bundle(data)
def update_bundle(data):
    for buindle in data['items']:
        bunld = Bundle.query.filter_by(id=buindle['item_id']).first()
        bunld.status = "GIVEN"
        bunld.given_date = datetime.now()
        bunld.given_to = data["customer"]
        bunld.given_by = 0
        db.session.commit()
