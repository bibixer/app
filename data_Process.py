# from sqlalchemy.sql.functions import current_user

from modes import Cuter,Item_data,Outworker,Bundle,Jobcard,Jobmovement,Lump,Party,Bale_date
from datetime import datetime,timedelta,time
from collections import defaultdict
from sqlalchemy import func
from modes import db



def get_cuter_name():
    cuter_name = Cuter.query.all()
    cuter_name_list = []
    for cuter in cuter_name:
        if cuter.name != '':
            if (str(cuter.name)).upper() not in cuter_name_list:
                cuter_name_list.append(cuter.name)
    return cuter_name_list

def get_party_name():
    cuter_name = Party.query.all()
    party_name_list = []
    for party in cuter_name:
        if party.name != '':
            if (str(party.name)).upper() not in party_name_list:
                party_name_list.append(party.name)
    return party_name_list

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
        "party_data":get_party_name()
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
# { id: 125, name: "Vimal", colour: "Red", pics: 25, kg: 12.75 ,avg cloth used   }

#  total avage cloth used =  total used / total pics

def age_clothused(product):
    all_date =  Bundle.query.filter_by(lump_id=product.lump_id).all()
    lump_data =  Lump.query.get(product.lump_id)
    total_pic  =  0
    for pro in all_date:
        total_pic += pro.pieces
    # print(f"for  {product.lump_id}  ")
    # print(lump_data.meters)
    add = lump_data.meters_add_remove
    if add == "":
        print(add)
        add= 0.0
    # print(type(float(add)))
    # print(total_pic)
    # print((float(lump_data.meters) + float(add)) / int(total_pic))
    return {"avg_cloth":((float(lump_data.meters) + float(add)) / int(total_pic)),'cutter_name':lump_data.cut_by}

def get_product():
    product_bunle =  Bundle.query.all()
    product_list = []
    avg_cloth = {}
    for product in product_bunle:
        if product.status.upper()  == "READY":
            if product.lump_id not in  avg_cloth.keys():
                avg_cloth[product.lump_id] = age_clothused(product)
            product_list.append({"id":product.id,
                             "name":product.product,
                             "colour":product.color,
                             "pics":product.pieces,
                            "type":product.type_B,
                             "kg":product.kg,
                             "avg_cloth":avg_cloth[product.lump_id]["avg_cloth"],
                             "cutter_name":avg_cloth[product.lump_id]['cutter_name'],
                             "so_no":product.s_no,
                             "cutting_date":product.entry_datetime.strftime("%Y-%m-%d")
                                 }

                              )
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

# {
#           name: "Manoj",
#           date_from: new Date(2025, 3, 4),
#           date_to: new Date(2025, 3, 26),
#           tres: [
#             {
#               name_of_product: "vinal",
#               pics: 20,
#               type: "good cut",
#               date: new Date(2025, 3, 5),
#               id: 1,
#             },
#             {
#               name_of_product: "vinal",
#               pics: 20,
#               type: "good cut",
#               date: new Date(2025, 3, 6),
#               id: 3,
#             },
#             {
#               name_of_product: "vinal2",
#               pics: 40,
#               type: "good cut",
#               date: new Date(2025, 3, 7),
#               id: 4,
#             },
#             {
#               name_of_product: "vinal",
#               pics: 30,
#               type: "Lump",
#               date: new Date(2025, 3, 8),
#               id: 5,
#             },
#             {
#               name_of_product: "vinal2",
#               pics: 25,
#               type: "Fent",
#               date: new Date(2025, 3, 9),
#               id: 6,
#             },
#             {
#               name_of_product: "ram",
#               pics: 35,
#               type: "Lump",
#               date: new Date(2025, 3, 10),
#               id: 7,
#             },
#             {
#               name_of_product: "ram",
#               pics: 15,
#               type: "Fent",
#               date: new Date(2025, 3, 11),
#               id: 8,
#             },
#             {
#               name_of_product: "shyam",
#               pics: 40,
#               type: "Lump",
#               date: new Date(2025, 3, 12),
#               id: 9,
#             },
#             {
#               name_of_product: "shyam",
#               pics: 20,
#               type: "Fent",
#               date: new Date(2025, 3, 13),
#               id: 10,
#             },
#             {
#               name_of_product: "vinal",
#               pics: 20,
#               type: "good cut",
#               date: new Date(2025, 3, 14),
#               id: 11,
#             },
#             {
#               name_of_product: "vinal",
#               pics: 20,
#               type: "good cut",
#               date: new Date(2025, 3, 15),
#               id: 12,
#             },
#             {
#               name_of_product: "vinal",
#               pics: 20,
#               type: "good cut",
#               date: new Date(2025, 3, 16),
#               id: 13,
#             },
#           ],
#         };

def get_cutter_report_data(data,current_user):
    if current_user.is_authenticated:
        if current_user.role != 1:
            return 404
    if not  current_user.is_authenticated:
        return 404
    if data.name.data == "all_cutter":
        all_date = Lump.query.filter(
            Lump.entry_datetime.between(
                datetime.combine(data.date_from.data, time.min),  # 00:00:00 of start date
                datetime.combine(data.date_to.data, time.max)  # 23:59:59.999999 of end date
            )
        ).all()
    elif data.name.data != "all_cutter":
        all_date = Lump.query.filter_by(cut_by=data.name.data).filter(
            Lump.entry_datetime.between(
                datetime.combine(data.date_from.data, time.min),  # 00:00:00 of start date
                datetime.combine(data.date_to.data, time.max)  # 23:59:59.999999 of end date
            )
        ).all()


    all_bundle = []
    for i in all_date:
      all_b = (Bundle.query.filter(Bundle.lump_id == i.id).all())
      for b in all_b:
          # all_bundle.append(b.to_dict_2())
          cutter =  Lump.query.get(b.lump_id).cut_by
          data_b= b.to_dict_2(cutter)
          # need to add
          # supplier: "Ram Tex",
          #               lot_number: "410X3",
          #               bale_number: 2,
          #               packing_date: "2026-02-22",
          #               meter: 148,
          lump = Lump.query.get(b.lump_id)
          data_b['meter'] = lump.meters
          if  lump.bale_id:
              bale =  Bale_date.query.get(lump.bale_id)
              data_b["supplier"]  = bale.part_name
              data_b["lot_number"] =  f"{bale.lot_number}X{bale.lot_count}"
              data_b['packing_date'] = str(bale.bale_date)
              data_b["bale_number"]  = bale.bale_number
          elif not  lump.bale_id:

              data_b["supplier"] = "UNKNOWN"
              data_b["lot_number"] = "UNKNOWN"
              data_b['packing_date'] = "UNKNOWN"

          all_bundle.append(data_b)



    return {
        'name': data.name.data,
        'date_from': data.date_from.data.strftime("%Y-%m-%d"),
        'date_to':data.date_to.data.strftime("%Y-%m-%d"),
        'tres': all_bundle,

    }



# cuuter repot_wokrk
# {
#         name: "Ramesh (Supervisor)",
#         date_from: "2026-03-01",
#         date_to: "2026-03-07",
#         old_bal_data: [
#           { product: "Vimal", type: "Premium", pieces: 30 },
#           { product: "Vimal", type: "Standard", pieces: 15 },
#           { product: "Basmati Rice", type: "Premium", pieces: 100 },
#           { product: "Basmati Rice", type: "Standard", pieces: 50 },
#           { product: "Organic Wheat", type: "Premium", pieces: 75 },
#         ],
#         tres: [
#           // VIMAL - Premium: 3 in, 5 out | Standard: 2 in, 4 out
#
#           {
#             id: 109,
#             entry_datetime: "2026-03-02T14:00:00",
#             product: "Organic Wheat",
#             type_B: "Standard",
#             pieces: 60,
#             kg: 1500,
#             flow: "out",
#           },
#           {
#             id: 110,
#             entry_datetime: "2026-03-03T15:30:00",
#             product: "Organic Wheat",
#             type_B: "Premium",
#             pieces: 20,
#             kg: 500,
#             flow: "in",
#           },
#         ],
#       };


# 402 outwower name not found
# 403 for flow not found

def master_report_card(data:dict,current_user):
    if current_user.is_authenticated:
        if current_user.role != 1:
            return 404
    if not current_user.is_authenticated:
        return 404
    product_flow_data = []
    old_data =[]
    # chek name if in database  or not

    all_name =  outworker_name(oly_full_name=True)
    if data["name"]not in all_name:
        return 402

    # check for flow
    is_flow = Jobmovement.query.filter_by(name_of_mater=data['name']).first()

    if not is_flow:
        return 403
    # # get old date

    old_flow =  (
        Jobmovement.query.filter_by(name_of_mater=data['name']).filter(
            Jobmovement.date<  datetime.combine(data["date_from"], time.min)  # 00:00:00 of start date
        ).order_by(
            Jobmovement.product_name,
            Jobmovement.type_B
        ).all()
    )
    product_flow_old = defaultdict(
        lambda: defaultdict(lambda: {"IN": [], "OUT": []})
    )

    for job in old_flow:
        product_flow_old[job.product_name][job.type_B][job.flow_type].append(
            job.to_dict()
        )
    so = 0
    for product, types in product_flow_old.items():
        for type_b, flows in types.items():

            total_in = sum(i.get("inflow", 0) for i in flows["IN"])
            total_out = sum(i.get("outflow", 0) for i in flows["OUT"])

            balance = total_out - total_in

            if balance != 0:
                so +=1
                old_data.append({
                    "so":so,
                    "product": product,
                    "type": type_b,
                    "pieces": -(balance),

                })

    # get date of that range

    # {
    #             id: 110,
    #             entry_datetime: "2026-03-03T15:30:00",
    #             product: "Organic Wheat",
    #             type_B: "Premium",
    #             pieces: 20,
    #             kg: 500,
    #             flow: "in",
    #           }
    rag_date  =  (
        Jobmovement.query.filter_by(name_of_mater=data['name']).filter(
            Jobmovement.date.between(

                    datetime.combine(data['date_from'], time.min),  # 00:00:00 of start date
                    datetime.combine(data['date_to'], time.max)  # 23:59:59.999999 of end date
                )
            )  # 00:00:00 of start date
        ).order_by(
            Jobmovement.product_name,
            Jobmovement.type_B
        ).all()

    if rag_date !=[]:
         for date_range_data in rag_date:
           if date_range_data.flow_type == "OUT":
               buundle = Bundle.query.get(date_range_data.bundle)
               lump =  Lump.query.get(buundle.lump_id)
               product_flow_data.append({
                       'id': date_range_data.id,
                       "entry_datetime": date_range_data.date,
                       "product": date_range_data.product_name,
                       "type_B": date_range_data.type_B,
                       "pieces": date_range_data.outflow,
                       "kg": buundle.kg,
                       "flow": "out",
                       "color": buundle.color,
                       "cut_by":lump.cut_by,
                       "labe_made_by":lump.enter_user,
                       "bindle_id":date_range_data.bundle,
                       "give_by":date_range_data.enter_user,
               })

           if date_range_data.flow_type == "IN":
               product_flow_data.append({

                       'id': date_range_data.id,
                       "entry_datetime": date_range_data.date,
                       "product": date_range_data.product_name,
                       "type_B": date_range_data.type_B,
                       "pieces": date_range_data.inflow,
                       "kg": 0.01,
                       "flow": "in",
                       "give_taken":date_range_data.enter_user,
               })

    return {
        'name': data["name"],
        'date_from': data["date_from"],
        'date_to': data['date_to'],
        'old_bal_data': old_data,
        'tres': product_flow_data,

    }

# reddy

def get_movemet_data_2(master_name,date_from):
    # 1️⃣ Fetch all data in ONE query
    job_data = (Jobmovement.query
                .filter_by(name_of_mater=master_name)
                .filter(Jobmovement.date < datetime.combine(date_from, time.min))
                .order_by(Jobmovement.product_name, Jobmovement.type_B)
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

                })
    return result


#  { id: 101, product: "Panel", type_B: "sliced", pieces: 5, kg: 12.5, status: "completed", given_to: null, entry_datetime: new Date("2025-03-02"), flow: "ready" }
def product_data (data:dict,current_user):
    if current_user.is_authenticated:
        if current_user.role != 1:
            return 404
    if not current_user.is_authenticated:
        return 404
    product_bunle = Bundle.query.all()
    product_list = []
    avg_cloth = {}
    for product in product_bunle:
        if product.status.upper() == "READY":
            if product.lump_id not in avg_cloth.keys():
                avg_cloth[product.lump_id] = age_clothused(product)
            product_list.append({"id": product.id,
                                 "product": product.product,
                                 "colour": product.color,
                                 "pieces": product.pieces,
                                 "type_B": product.type_B,
                                 "kg": product.kg,
                                 "given_to":None,
                                 "flow": "ready",
                                 "entry_datetime":product.entry_datetime.strftime("%Y-%m-%d"),
                                 "avg_cloth": avg_cloth[product.lump_id]["avg_cloth"]})
    # { id: 201, product: "Panel", type_B: "sliced", pieces: 4, kg: 8.0, status: "completed", given_to: "Mohan", entry_datetime: new Date("2025-03-08"), flow: "outflow" }
    outflow = Jobmovement.query.filter_by(flow_type="OUT").filter(
    Jobmovement.date.between(
        datetime.combine(data['date_from'], time.min),  # 00:00:00 of start date
        datetime.combine(data['date_to'], time.max)     # 23:59:59 of end date
    )
    ).order_by(Jobmovement.product_name, Jobmovement.type_B).all()
    for out  in outflow:
        buble  =  Bundle.query.get(out.bundle)
        data_F = {
            'id': out.id,
            "product": out.product_name,
            "type_B":out.type_B,
            "pieces": out.outflow ,
            'kg':buble.kg,
            "status": "completed",
            "given_to": out.name_of_mater ,
            "entry_datetime" :out.date.strftime("%Y-%m-%d"),
            "flow": "outflow"


        }

        product_list.append(data_F)
    inflow = Jobmovement.query.filter_by(flow_type="IN").filter(
    Jobmovement.date.between(
        datetime.combine(data['date_from'], time.min),  # 00:00:00 of start date
        datetime.combine(data['date_to'], time.max)     # 23:59:59 of end date
    )
    ).order_by(Jobmovement.product_name, Jobmovement.type_B).all()
    for inf  in inflow :
        data_F = {
            'id': inf .id,
            "product": inf.product_name,
            "type_B":inf.type_B,
            "pieces": inf.inflow,
            'kg':0.0,
            "status": "completed",
            "given_to": inf.name_of_mater ,
            "entry_datetime" :inf.date.strftime("%Y-%m-%d"),
            "flow": "inflow"


        }

        product_list.append(data_F)
    all_out_name =  outworker_name(oly_full_name=True)
    all_dat =  {}
    for all in all_out_name:
        data_o = get_movemet_data_2(all,date_from=data['date_from'])

        if data_o != 404:
            total = 0
            for dat in data_o['items']:
                total += dat['issued']
            all_dat[data_o['name']] = - total

    return {"proddcut": product_list,"ouwoker": all_dat}



# data needy by edit find
#     const baseData = [
#         // Bundle/Lump data with given_by and given_to (from the provided record)
#         {
#             id: 1935, level: 'lump', lump_id: 887, bale_number: 7902, bale_id: 2,
#             cutter: 'RAJENDRA', entry_datetime: 'Wed, 18 Mar 2026 18:18:31 GMT',
#             given_by: 'chandan', given_date: 'Thu, 19 Mar 2026 11:15:15 GMT',
#             given_to: '38***VIDYA--38/-', kg: 4.61, lot_number: '9090X1',
#             meter: 47.0, packing_date: '2026-03-18', pieces: 20,
#             product: 'MAHAMAYA 2MTR', status: 'GIVEN', supplier: 'UNKNOW',
#             type_B: 'lump', so_number: 202,
#             // Lump specific fields
#             cut_by: 'RAJENDRA', bundle_type: 'good_cut', meters: 47.0,
#             meters_add_remove: 1.5, color: 'RED', number_of_bundlie: 2
#         },
#         // Bundles under this lump
#         {
#             id: 4001, level: 'bundle', bundle_id: 8001, lump_id: 887,
#             product: 'MAHAMAYA 2MTR', color: 'RED', pieces: 12, kg: 2.76,
#             type_B: 'bundle', no_of_so: 202, status: 'GIVEN',
#             entry_datetime: '2026-03-18 18:30:00',
#             given_by: 'chandan', given_date: 'Thu, 19 Mar 2026 11:15:15 GMT',
#             given_to: '38***VIDYA--38/-'
#         },
#         {
#             id: 4002, level: 'bundle', bundle_id: 8002, lump_id: 887,
#             product: 'MAHAMAYA 2MTR', color: 'BLUE', pieces: 8, kg: 1.85,
#             type_B: 'bundle', no_of_so: 202, status: 'READY',
#             entry_datetime: '2026-03-18 19:00:00',
#             given_by: null, given_date: null, given_to: null
#         },


