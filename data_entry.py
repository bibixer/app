from modes import db, Bundle, Lump, Cuter, Item_data, Outworker
from datetime import datetime



def add_data_to_database(data):
    db.session.add(data)
    db.session.commit()
    return 101
def add_data_lump(data,current_user):
    # try:
        lump_data = data['main']
        print(data)
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


