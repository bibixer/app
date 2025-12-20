from  modes import db ,Bundle,Lump
from datetime import datetime



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
            color = lump_data['numbers_of_bundles'],
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
        print(b)
        bundle = Bundle(
            entry_datetime = datetime.now(),
            lump_id = lump_id,
            pieces = b['no_of_pics'],
            kg= b['kg_of_bundle'],
        )
        db.session.add(bundle)
        db.session.commit()

