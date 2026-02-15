from modes import Cuter,Item_data,Outworker,Bundle,Jobcard,Jobmovement
from datetime import datetime,timedelta,time
from collections import defaultdict
from sqlalchemy import func
from modes import db

# fist for lump data
# get cuter dta
# get product data

# demodata_{'main':
# {'bundle_type': 'lump', 'colors': 'red', 'cuter_name': 'MANOJ', 'meters': 125.0, 'numbers_of_bundles': 2, 'product_name': 'GOLD 2MTR', 'submit': True},
# 'bundles': {'1': {'kg_of_bundle': 25.0, 'no_of_pics': 1, 'no_of_so': 25, 'submit': True}, '2': {'kg_of_bundle': 1.0, 'no_of_pics': 25, 'no_of_so': 26, 'submit': True}}
# }

def bulk_data_lump(data):
    main = data
    bundles = {}
    for i in range(1,main['numbers_of_bundles']+1):
        bundles[i] = {'kg_of_bundle':0.001 ,'no_of_pics': 20, 'no_of_so': 10505 }
    return {'main':main, 'bundles':bundles}

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

def outworker_name(**kwargs):
    oly_full_name = kwargs.get("oly_full_name")
    name = Outworker.query.all()
    Outworker_list = []
    for o in name:
        if o.name != '':
            if (str(o.name)).upper() not in Outworker_list:
                if oly_full_name:
                    Outworker_list.append(f"{o.id}***{o.name}--{o.adders}/-")
                else:
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
                            "type":product.type_B,
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
    # 1️⃣ Fetch all data in ONE query
    job_data = (
        Jobmovement.query
        .filter_by(name_of_mater=master_name)
        .order_by(
            Jobmovement.product_name,
            Jobmovement.type_B
        )
        .all()
    )

    if not job_data:
        return 404

    # 2️⃣ Build product → IN/OUT structure
    product_flow = defaultdict(
        lambda: defaultdict(lambda: {"IN": [], "OUT": []})
    )

    for job in job_data:
        product_flow[job.product_name][job.type_B][job.flow_type].append(
            job.to_dict()
        )

    # 3️⃣ Format final job-card output
    result = {
        "name": master_name,
        "date": datetime.now().strftime("%d %b, %Y"),
        "items": []
    }

    item_id = 0
    for product, types in product_flow.items():
        for type_b, flows in types.items():

            total_in = sum(i.get("inflow", 0) for i in flows["IN"])
            total_out = sum(i.get("outflow", 0) for i in flows["OUT"])

            balance = total_out - total_in

            if balance != 0:
                item_id += 1
                result["items"].append({
                    "item_id": item_id,
                    "name": product,
                    "colour": type_b,
                    "issued": balance,
                    "history": []
                })
    return result


def get_current_week_range():
    today = datetime.now()

    weekday = today.weekday()  # Monday=0, Tuesday=1, Wednesday=2, ...

    if weekday == 2:  # Today is Wednesday
        from_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
        to_date = from_date + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
    else:
        days_since_wednesday = (weekday - 2) % 7
        from_date = (today - timedelta(days=days_since_wednesday)).replace(hour=0, minute=0, second=0, microsecond=0)
        to_date = from_date + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
    data = {"from_date":from_date, "to_date":
        to_date}
    return data


def home_dashboard(date):
    # Bundle stats (READY + GIVEN in one go)

    start_datetime = datetime.combine(date.date_from.data, time.min)
    end_datetime = datetime.combine(date.date_to.data, time.max)
    if start_datetime  > end_datetime:
        return "invalid_range"

    bundle_query = db.session.query(
        Bundle.status,
        func.count(Bundle.id),
        func.coalesce(func.sum(Bundle.pieces), 0)
    ).filter(
        Bundle.status.in_(["READY", "GIVEN"]),
    ).group_by(Bundle.status).all()

    bundle_stats = {}

    for status, count, total in bundle_query:
        bundle_stats[status] = (count, total)

    count_ready, total_ready = bundle_stats.get("READY", (0, 0))
    count_given, total_given = bundle_stats.get("GIVEN", (0, 0))

    # Movement totals
    movement_totals = db.session.query(
        func.coalesce(func.sum(Jobmovement.inflow), 0),
        func.coalesce(func.sum(Jobmovement.outflow), 0)
    ).filter(
        Jobmovement.date.between(start_datetime, end_datetime)
    ).first()

    total_inflow, total_outflow = movement_totals

    # Per-product aggregation
    product_flows = db.session.query(
        Jobmovement.product_name,
        func.coalesce(func.sum(Jobmovement.inflow), 0),
        func.coalesce(func.sum(Jobmovement.outflow), 0)
    ).filter(
        Jobmovement.date.between(start_datetime, end_datetime)
    ).group_by(Jobmovement.product_name).all()

    inflow_pie = []
    outflow_pie = []

    for product, inflow_sum, outflow_sum in product_flows:
        inflow_pie.append({
            "item_name": product,
            "quantity": inflow_sum
        })
        outflow_pie.append({
            "item_name": product,
            "quantity": outflow_sum
        })

    return {
        "redy": f"{count_ready}:{total_ready}",
        "given": f"{count_given}:{total_given}",
        "inflow_total": total_inflow,
        "outflow_total": total_outflow,
        "inflow_pie": [{"name": "item", "points": inflow_pie}],
        "outflow_pie": [{"name": "item", "points": outflow_pie}],
    }
