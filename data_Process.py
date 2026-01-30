from modes import Cuter,Item_data,Outworker,Bundle

# fist for lump data
# get cuter dta
# get product data
def get_cuter_name():
    cuter_name = Cuter.query.all()
    cuter_name_list = []
    for cuter in cuter_name:
        if cuter.name != '':
            if (str(cuter.name)).upper() not in cuter_name_list:
                cuter_name_list.append(cuter.name)
    return cuter_name_list

def get_product_namm():
    product =  Item_data.query.all()
    product_list = []
    for product in product:
        if str(product.name) != '':
            if (str(product.name)).upper() not in product_list:

                product_list.append(product.name)
    return product_list

def get_serch_data():
    return {
        "product_data":get_product_namm(),
        "cuter_data":get_cuter_name(),
    }


## get outerworker name and id

def outworker_name():
    name = Outworker.query.all()
    Outworker_list = []
    for o in name:
        if o.name != '':
            if (str(o.name)).upper() not in Outworker_list:
                Outworker_list.append({"id":o.id, "name":o.name,"adders":o.adders})
    return  Outworker_list

## get prodrdut id
# data domy
# { id: 125, name: "Vimal", colour: "Red", pics: 25, kg: 12.75 }

def get_product():
    product_bunle =  Bundle.query.all()
    product_list = []
    # for product in product_bunle:
