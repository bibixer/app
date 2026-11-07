from modes import db, Bundle, Lump, Cuter, Item_data, Outworker, OutworkerAlias,Jobcard,Jobmovement,ReturnBreakdown,Bale_date,Party,RequestDedup
import logging
from flask import current_app
from datetime import datetime
import hashlib
from functools import wraps
from sqlalchemy.exc import IntegrityError
from item_aliases import normalize_name, parse_aliases, validate_names, resolve_item_name, item_name_mapping
from validation import positive_integer, finite_number, record_id, MAX_DATABASE_INTEGER
from modes import ItemAlias
from master_aliases import validate_master_aliases, resolve_master_name
from bundle_types import BUNDLE_TYPE_VALUES
from data_Process import outworker_name,get_jobcard_return_data
from data_print_format import outworker_qr_print,buldel_qr_print,job_cade_print

def add_data_to_database(data):
    db.session.add(data)
    db.session.commit()
    return 101


def claim_write(request_key, endpoint, current_user):
    """Atomically claim a browser submission before changing business data."""
    if not isinstance(request_key, str) or not request_key.strip() or len(request_key) > 128:
        return False
    stable_key = hashlib.sha256(
        f"{current_user.username}:{endpoint}:{request_key}".encode("utf-8")
    ).hexdigest()
    try:
        db.session.add(RequestDedup(
            request_key=stable_key,
            endpoint=endpoint,
            username=current_user.username,
            created_at=datetime.now(),
        ))
        db.session.flush()
        db.session.expire_all()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def transactional_write(func):
    """A failed write must release both its data changes and its request claim."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            db.session.rollback()
            raise
    return wrapped


def _inventory_payload(data):
    if not isinstance(data, dict) or any(not isinstance(data.get(key), dict) for key in ("bale_data", "main", "bundles")):
        raise ValueError("Invalid inventory payload.")
    bale, main = dict(data["bale_data"]), dict(data["main"])
    bundles = data["bundles"]
    if (not positive_integer(main.get("numbers_of_bundles"), 20)
            or len(bundles) != main["numbers_of_bundles"]
            or main.get("bundle_type") not in BUNDLE_TYPE_VALUES
            or not finite_number(main.get("meters")) or main["meters"] <= 0
            or not finite_number(main.get("meters_add_remove"), minimum=-MAX_DATABASE_INTEGER)
            or main["meters"] + main["meters_add_remove"] <= 0):
        raise ValueError("Invalid lump quantities or bundle type.")
    if any(not positive_integer(bale.get(field)) for field in ("lot_number", "lot_count", "bale_number")):
        raise ValueError("Lot and bale numbers must be positive integers.")
    for bundle in bundles.values():
        if (not isinstance(bundle, dict) or not positive_integer(bundle.get("no_of_pics"))
                or not positive_integer(bundle.get("no_of_so")) or not finite_number(bundle.get("kg_of_bundle"))):
            raise ValueError("Invalid bundle quantity or weight.")
    product = resolve_item_name(main.get("product_name"))
    if (not product or resolve_item_name(bale.get("product_name")) != product
            or main.get("cuter_name") != bale.get("cuter_name")
            or not Cuter.query.filter_by(name=bale.get("cuter_name")).first()
            or not Party.query.filter_by(name=bale.get("party_name")).first()):
        raise ValueError("Select the product, cutter and supplier from Setup.")
    bale["product_name"] = main["product_name"] = product
    bale["packing_date"] = datetime.strptime(bale["packing_date"], "%a, %d %b %Y")
    return {"bale_data": bale, "main": main, "bundles": bundles}


@transactional_write
def bale_data_entry(data,current_user,request_key):
    # if current_user.is_authenticated:
    #     if current_user.role != 1:
    #         return 404
    if not  current_user.is_authenticated:
        return 404
    if not claim_write(request_key, "lump_workflow", current_user):
        return 409
    try:
        data = _inventory_payload(data)
    except (ValueError, TypeError, KeyError):
        db.session.rollback()
        return 405


    bale_data = dict(data['bale_data'])
    # check for cuuter date =
    old_date =  Bale_date.query.filter_by(
        part_name=bale_data['party_name'],
        lot_number=bale_data['lot_number'],
        lot_count=bale_data['lot_count'],
        bale_number= bale_data['bale_number'],
        enter_user =  current_user.username,
         cut_by = bale_data['cuter_name'],
        product = bale_data['product_name'],
        bale_date= bale_data['packing_date']

    ).first()
    if old_date == None:
        bale = Bale_date(
            part_name=bale_data['party_name'],
            lot_number=bale_data['lot_number'],
            lot_count=bale_data['lot_count'],
            bale_number= bale_data['bale_number'],
            enter_user =  current_user.username,
             cut_by = bale_data['cuter_name'],
            product = bale_data['product_name'],
            bale_date= bale_data['packing_date'],



        )
        db.session.add(bale)
        db.session.flush()
        id_b =  bale.id
    elif old_date !=  None:
        id_b = old_date.id

    data_to_print = add_data_lump(data,current_user,id_b)
    db.session.commit()
    try:
        buldel_qr_print(data_to_print)
    except Exception:
        logging.exception("Lump saved, but bundle label printing failed")
    return 101


def add_data_lump(data,current_user,bale_id):
    # try:
        lump_data = data['main']
        lump = Lump(
            entry_datetime = datetime.now(),
            enter_user = current_user.username,
            cut_by = lump_data['cuter_name'],
            bundle_type = lump_data['bundle_type'],
            product = lump_data['product_name'],
            meters = lump_data['meters'],
            color = lump_data['colors'],
            number_of_bundlie = lump_data['numbers_of_bundles'],
            bale_id= bale_id,
            meters_add_remove=lump_data['meters_add_remove']


        )
        db.session.add(lump)
        db.session.flush()
        all_bun_data = add_bundle(data,lump.id,lump_data['bundle_type'],lump_data['cuter_name'])
        return (all_bun_data)
def add_bundle(data,lump_id,type,cuter):
    fulldata_list = []
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
            type_B=type,
            s_no= b['no_of_so']
        )
        db.session.add(bundle)
        db.session.flush()
        fulldata_list.append(bundle.to_dict(cuter=cuter,no_of_so=b['no_of_so']))
    return fulldata_list
def error_hendle(func):
    @wraps(func)
    def eror(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            db.session.rollback()
            return {"or":False,"exception":e}
    return eror
@error_hendle
def add_cutter(data,current_user,request_key):
        if not claim_write(request_key, "add_cutter", current_user):
            return 409
        name = normalize_name(data["name"])
        if not name or len(name) > 50:
            raise ValueError("Cutter name must be between 1 and 50 characters.")
        cuuter = Cuter(name=name,
                       enter_user=current_user.username)
        return add_data_to_database(cuuter)

@error_hendle
def add_party(data,current_user,request_key):
       if not claim_write(request_key, "add_party", current_user):
           return 409
       name = normalize_name(data["name"])
       if not name or len(name) > 50 or any(normalize_name(row.name) == name for row in Party.query.all()):
           raise ValueError("Enter a unique supplier name of at most 50 characters.")
       paty = Party(name=name,
                       enter_user=current_user.username)
       return add_data_to_database(paty)

@error_hendle
def add_items(data,current_user,request_key):
    if not claim_write(request_key, "add_item", current_user):
        return 409
    name = normalize_name(data["name"])
    aliases = parse_aliases(data.get("aliases"))
    validate_names(name, aliases)
    if not finite_number(data.get("size")) or not finite_number(data.get("meter")):
        raise ValueError("Product size and meters must be finite, non-negative numbers.")
    item =  Item_data(name=name
    ,size = data["size"]
    ,meters = data["meter"],
    enter_user=current_user.username
    )
    db.session.add(item)
    db.session.flush()
    db.session.add_all(ItemAlias(item_id=item.id, alias=alias) for alias in aliases)
    return add_data_to_database(item)
@error_hendle
def add_outworker_db(data,current_user,request_key):
    if not claim_write(request_key, "add_outworker", current_user):
        return 409
    name = normalize_name(data["name"])
    aliases = parse_aliases(data.get("aliases"))
    validate_master_aliases(name, aliases)
    address = str(data.get("address") or "").strip()
    if not address or len(address) > 50 or not positive_integer(data.get("number")):
        raise ValueError("Enter an address of at most 50 characters and a positive contact number.")
    if any(normalize_name(row.name) == name and normalize_name(row.adders) == normalize_name(address)
           and row.number == data["number"] for row in Outworker.query.all()):
        raise ValueError("This outworker with the same address and contact number already exists.")
    outworker = Outworker(name=name,
                          adders=address,
                          number = data["number"],
                          enter_user=current_user.username
                          )
    db.session.add(outworker)
    db.session.flush()
    db.session.add_all(OutworkerAlias(worker_id=outworker.id, alias=alias) for alias in aliases)
    OUT=add_data_to_database(outworker)
    if OUT == 101 and not current_app.config.get('SIMPLE_WORKFLOW'):
        try:
            if outworker_qr_print(outworker) != 101:
                logging.error("Outworker %s saved, but QR printing did not succeed", outworker.id)
        except Exception:
            logging.exception("Outworker %s saved, but QR printing failed", outworker.id)
        return 101
    return OUT
# @error_hendle
def check_name_master(data):
    all_data = outworker_name(oly_full_name=True)
    # print(all_data)
    # print(str(data))
    if str(data) in all_data:
        return True
    else:
        return False
# 101 ok 401 name 403 falt on itetem
def check_product(data):
    item_ids = [record_id(item["item_id"]) for item in data["items"]]
    if any(item_id is None for item_id in item_ids):
        return False
    if len(item_ids) != len(set(item_ids)):
        return False

    bundles = Bundle.query.filter(Bundle.id.in_(item_ids)).all()

    bundle_map = {b.id: b for b in bundles}
    for item in data["items"]:

        bundle = bundle_map.get(record_id(item["item_id"]))

        if not bundle:
            return False

        if bundle.product != item["name_of_prduct"]:
            return False

        if bundle.pieces != int(item["qty"]):
            return False

        if abs(bundle.kg - float(item["kg"])) > 0.0001:
            return False
        if (bundle.type_B != (item["type"])):
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
    if not isinstance(data.get("items"), list) or not 1 <= len(data["items"]) <= 1000:
        return False

    for item in data["items"]:
        if not isinstance(item, dict):
            return False

        required_fields = ["item_id", "name_of_prduct", "qty", "kg","type"]
        for field in required_fields:
            if field not in item:
                return False

        if not isinstance(item["item_id"], str) or record_id(item["item_id"]) is None:
            return False
        if not isinstance(item["type"], str) or item["type"] not in BUNDLE_TYPE_VALUES:
            return False

        if not isinstance(item["name_of_prduct"], str) or not item["name_of_prduct"].strip():
            return False

        if not positive_integer(item["qty"]):
            return False

        if not finite_number(item["kg"]):
            return False

    return True
@transactional_write
def add_jobcard(data,current_user,request_key):
    if not validate_payload_structure(data):
        return 405
    if not claim_write(request_key, "add_jobcard", current_user):
        return 409
    if not check_name_master(data["customer"]):
        db.session.rollback()
        return 401
    if not check_product(data):
        db.session.rollback()
        return 403
    return _persist_jobcard(data, current_user)


def _persist_jobcard(data, current_user):
    job_card = Jobcard(
    date = datetime.now(),
    given_to = data["customer"],
    given_by =  current_user.username,
    product_list = data['items']
    )
    db.session.add(job_card)
    db.session.flush()
    add_job_movemet_out(data,job_card.id,current_user)
    db.session.commit()
    data_p = {
        "code":101,
        "jobData":{
            "jobId": job_card.id,
            "party": job_card.given_to,
            "toal_p": ".",
            "date": datetime.now().strftime("%d-%m-%Y"),
            "items":job_card.product_list,
            "username": current_user.username
        }
    }
    try:
        job_cade_print(data_p)
    except Exception:
        logging.exception("Job card %s saved, but CSV printing failed", job_card.id)

    return  data_p


def validate_manual_jobcard(data):
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("customer"), str) or not data["customer"].strip():
        return False
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows or len(rows) > 100:
        return False
    for row in rows:
        if not isinstance(row, dict):
            return False
        if not isinstance(row.get("product"), str) or not row["product"].strip():
            return False
        if not isinstance(row.get("type"), str) or row["type"] not in BUNDLE_TYPE_VALUES:
            return False
        pieces = row.get("pieces")
        count = row.get("count")
        if not positive_integer(pieces):
            return False
        if not positive_integer(count, maximum=500) or pieces * count > MAX_DATABASE_INTEGER:
            return False
    return sum(row["pieces"] * row["count"] for row in rows) <= MAX_DATABASE_INTEGER


@transactional_write
def add_manual_jobcard(data, current_user, request_key):
    """Create a job card directly from manual patterns, without inventory bundles."""
    if not validate_manual_jobcard(data):
        return 405
    if not claim_write(request_key, "add_manual_jobcard", current_user):
        return 409
    product_map = item_name_mapping()
    product_names = [product_map.get(normalize_name(row["product"])) for row in data["rows"]]
    if any(name is None for name in product_names):
        db.session.rollback()
        return 406
    master_name = resolve_master_name(data["customer"])
    if not master_name:
        db.session.rollback()
        return 401

    job_card = Jobcard(
        date=datetime.now(), given_to=master_name,
        given_by=current_user.username, product_list=[],
    )
    db.session.add(job_card)
    db.session.flush()
    items = [{
        "item_id": f"MANUAL-{job_card.id}-{index}",
        "name_of_prduct": product_names[index - 1],
        "type": row["type"].strip(),
        "pieces_per_bundle": row["pieces"],
        "bundle_count": row["count"],
        "qty": row["pieces"] * row["count"],
        "kg": 0,
        "source": "MANUAL",
    } for index, row in enumerate(data["rows"], start=1)]

    job_card.product_list = items
    for item in items:
        db.session.add(Jobmovement(
            date=datetime.now(), jobcard=str(job_card.id), bundle=None,
            outflow=item["qty"], name_of_mater=job_card.given_to,
            enter_user=current_user.username,
            partculer=f'Manual job card {job_card.id}, line {item["item_id"]}'[:50],
            product_name=item["name_of_prduct"], flow_type="OUT",
            type_B=item["type"],
        ))
    db.session.commit()
    result = {
        "code": 101,
        "jobData": {
            "jobId": job_card.id, "party": job_card.given_to,
            "toal_p": ".", "date": job_card.date.strftime("%d-%m-%Y"),
            "items": items, "username": current_user.username,
        },
    }
    if not current_app.config.get('SIMPLE_WORKFLOW'):
        try:
            job_cade_print(result)
        except Exception:
            logging.exception("Manual job card %s saved, but CSV printing failed", job_card.id)
    return result
def add_job_movemet_out(data,job_id,current_user):
    for item in data['items']:
        job_movement = Jobmovement(
        date = datetime.now(),
        jobcard = job_id,
        bundle = item["item_id"],
        outflow = item["qty"],
        name_of_mater =  data["customer"],
        enter_user = current_user.username,
        partculer = f'given {item["name_of_prduct"]} to '
                    f'{data["customer"] } toatal pic {item["qty"] } '
                    f'with job_id {job_id} '
        ,product_name = item["name_of_prduct"],
        flow_type = "OUT",
        type_B = item["type"]
        )
        db.session.add(job_movement)
    update_bundle(data,current_user)
def update_bundle(data,current_user):
    for buindle in data['items']:
        bunld = Bundle.query.filter_by(id=buindle['item_id']).first()
        bunld.status = "GIVEN"
        bunld.given_date = datetime.now()
        bunld.given_to = data["customer"]
        bunld.given_by = str(current_user.username)
def check_return_item(data):
    if not isinstance(data, dict) or not positive_integer(data.get("jobcard_id")):
        return 405
    if not isinstance(data.get("items"), list) or not data["items"]:
        return 405
    db_data = get_jobcard_return_data(data["jobcard_id"])
    if db_data is None:
        return 404
    if data.get("name") != db_data["name"]:
        return 401
    db_items = {item["item_id"]: item for item in db_data["items"]}


    seen_ids = set()
    for item in data["items"]:
        try:
            item_id = record_id(item["item_id"])
            returned_qty = item["returned"]
            token_name = item["name_of_product"]
            type_B = item['type']
        except (KeyError, TypeError, ValueError):
            return 405
        if item_id is None or item_id in seen_ids or not positive_integer(returned_qty):
            return 405
        seen_ids.add(item_id)
        # print(item)


        # 1️⃣ Check ID exists
        if item_id not in db_items:
            return 4031

        db_item = db_items[item_id]

        # 2️⃣ Check name matches for same ID
        # print(token_name.lstrip())
        # print(db_item["name"].lstrip())
        if db_item["name"] != token_name:
            return 4032

        # 3️⃣ Check quantity rule
        if returned_qty > db_item["issued"]:
            return 4033
        if type_B != db_item["colour"]:
            return 4034

        method = item.get("entry_method", "direct")
        rows = item.get("calculation_rows", [])
        if method not in ("direct", "calculator") or not isinstance(rows, list) or len(rows) > 100:
            return 405
        if method == "direct" and rows:
            return 405
        if method == "calculator":
            if not rows:
                return 405
            calculated_total = 0
            for row in rows:
                if not isinstance(row, dict):
                    return 405
                pieces, count = row.get("pieces"), row.get("count")
                if not positive_integer(pieces) or not positive_integer(count) or pieces * count > MAX_DATABASE_INTEGER:
                    return 405
                calculated_total += pieces * count
            if calculated_total != returned_qty:
                return 405


    return True
def in_move_entery(data,current_user,request_key):
    # if validate_return_structure_(data):
    #     return 405

    try:
        if not claim_write(request_key, "return_items", current_user):
            return 409
        check_i = check_return_item(data)
        if check_i is not True:
            db.session.rollback()
            return check_i
        canonical_items = {item["item_id"]: item["product_name"]
                           for item in get_jobcard_return_data(data["jobcard_id"])["items"]}
        result_items = []
        for item in data['items']:
            rows = item.get("calculation_rows", [])
            method = item.get("entry_method", "direct")
            note = ", ".join(f'{row["pieces"]}X{row["count"]}' for row in rows) if method == "calculator" else ""
            product_name = canonical_items[record_id(item["item_id"])]
            result_items.append({**item, "note": note, "name_of_product": product_name})
            job_movement = Jobmovement(
                date=datetime.now(),
                jobcard=str(data["jobcard_id"]),
                partculer=f"Return card {data['jobcard_id']} {note}"[:50],
                product_name = product_name,
                name_of_mater = data['name'],
                enter_user = current_user.username,
                flow_type = "IN",
                type_B = item["type"],
                inflow =item["returned"],
            )

            db.session.add(job_movement)
            db.session.flush()
            db.session.add(ReturnBreakdown(
                movement_id=job_movement.id,
                entry_method=method,
                calculation_rows=rows,
            ))
        db.session.commit()
        return {
        "code": 101,
        "jobData": {
            "jobcard_id": data["jobcard_id"],
            "party": data['name'],
            "date": datetime.now().strftime("%d-%m-%Y"),
            "items": result_items,
            "username":current_user.username
        }
    }

    except Exception:
        db.session.rollback()
        logging.exception("Return save failed")
        return 500
