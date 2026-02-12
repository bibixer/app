from modes import db, Bundle, Lump, Cuter, Item_data, Outworker,Jobcard,Jobmovement
from datetime import datetime
from data_Process import outworker_name,get_movemet_data
# import re

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

def check_name_master(data):
    all_data = outworker_name(oly_full_name=True)
    if data["customer"] in all_data:
        return True
    else:
        return False

# 101 ok 401 name 403 falt on itetem


def check_product(data):
    item_ids = [item["item_id"] for item in data["items"]]

    bundles = Bundle.query.filter(Bundle.id.in_(item_ids)).all()
    bundle_map = {b.id: b for b in bundles}

    for item in data["items"]:
        bundle = bundle_map.get(item["item_id"])
        if not bundle:
            return False

        if bundle.product != item["name_of_product"]:
            return False

        if bundle.pieces != int(item["qty"]):
            return False

        if abs(bundle.kg - float(item["kg"])) > 0.0001:
            return False

        if bundle.status != "READY":
            return False

    return True


def validate_payload_structure(data):
    if not isinstance(data, dict):
        return False

    # customer check
    if "customer" not in data or not isinstance(data["customer"], str) or not data["customer"].strip():
        return False
    # items check
    if "items" not in data or not isinstance(data["items"], list) or len(data["items"]) == 0:
        return False

    for item in data["items"]:
        if not isinstance(item, dict):
            return False

        required_fields = ["item_id", "name_of_prduct", "qty", "kg"]
        for field in required_fields:
            if field not in item:
                return False

        if not isinstance(item["item_id"], str):
            return False,

        if not isinstance(item["name_of_prduct"], str):
            return False,

        if not isinstance(item["qty"], (int, float)):
            return False,

        if not isinstance(item["kg"], (int, float)):
            return False

    return True






def add_jobcard(data):
    if not validate_payload_structure(data):
        return 405
    if not check_name_master(data["customer"]):
        return 401
    if not check_product(data):
        return 403
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

def check_return_item(data):
    db_data = get_movemet_data(data["name"])

    if db_data == 404:
        return False

    # Map by item_id
    db_items = {
        int(item["item_id"]): item
        for item in db_data["items"]
    }

    for item in data["items"]:
        item_id = int(item["item_id"])
        returned_qty = int(item["returned"])
        token_name = item["name_of_product"]

        # 1️⃣ Check ID exists
        if item_id not in db_items:
            return False

        db_item = db_items[item_id]

        # 2️⃣ Check name matches for same ID
        if db_item["name"] != token_name:
            return False

        # 3️⃣ Check quantity rule
        if returned_qty > db_item["issued"]:
            return False

    return True,
def in_move_entery(data):
    # if validate_return_structure_(data):
    #     return 405

    try:
        data_r = {"customer": data['name']

                  }
        if not check_name_master(data_r):
            print(data['name'])
            return 401
        if not check_return_item(data):
            return 403
        for item in data['items']:
            job_movement = Jobmovement(
                date=datetime.now(),
                partculer = f"taken {item["name_of_product"]} from {data['name']} by {"badx"}",
                product_name = item["name_of_product"],
                name_of_mater = data['name'],
                enter_user = 1,
                flow_type = "IN",
                inflow =item["returned"],
            )

            db.session.add(job_movement)
            db.session.commit()
        return 101
    except:
        return 404


