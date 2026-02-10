from modes import Cuter,Item_data,Outworker,Bundle,Jobcard,Jobmovement
from flask import flash
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
                Outworker_list.append({"id":o.id, "name":o.name,"adders":o.adders ,"full":f"{o.id}***{o.name}--{o.adders}/-"})
    return  Outworker_list

## get prodrdut id
# data domy
# { id: 125, name: "Vimal", colour: "Red", pics: 25, kg: 12.75 }

def get_product():
    product_bunle =  Bundle.query.all()
    product_list = []
    for product in product_bunle:
        if product.status.upper()  == "READY":
            product_list.append({"id":product.id,
                             "name":product.product,
                             "colour":product.color,
                             "pics":product.pieces,
                             "kg":product.kg})
    return product_list

def get_job_card_data_creation():
    return {
        "outworker":outworker_name(),
        "product":get_product(),
    }


def get_job_card_id():
    job_card = Jobcard.query.all()
    job_card_list = []
    for job_card in job_card:
        job_card_list.append({
            "id":job_card.id,"type":"jobcard",
        })
    return job_card_list

def get_retun_card_data():
    outworker_na= outworker_name()
    name_list  =[]
    for outworker in outworker_na:
        name_list.append(outworker['full'])
    return {
        "outworker": name_list,
        'fulldata':outworker_na,
    }




# error code
#404 for not find job entery
# get all data of that outworker
def get_movemet_data(master_name):
    job_data = Jobmovement.query.filter_by(name_of_mater=master_name).all()
    if job_data == []:
        return 404
    all_product_name_list = get_all_product_name(job_data)
    all_flow_type_list = get_all_flow_type(job_data)


def get_all_product_name(job_data):
    all_product_name_list = []
    for job_i in job_data:
        if job_i.product_name not in all_product_name_list:
            all_product_name_list.append(job_i.product_name)
    return all_product_name_list
def get_all_flow_type(job_data):
    all_flow_type_list = []
    for job_i in job_data:
        if job_i.flow_type not in all_flow_type_list:
            all_flow_type_list.append(job_i.flow_type)
    return all_flow_type_list

def get_product_flow(all_product_name_list,master_name,all_flow_type_list):
    product_flow = {}
    for flow in all_flow_type_list:
        for product in all_product_name_list:
            data_f_p = Jobmovement.query.filter_by(name_of_mater=master_name,product_name=product,flow_type= flow).all()
        product_flow_and[f'{product}-{flow}'] = {
            "product":product,
            "flow":flow,
            "data":data_f_p,
        }
    return product_flow

