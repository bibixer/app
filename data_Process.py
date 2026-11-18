from modes import Cuter,Item_data,Outworker,Bundle,Jobcard,Jobmovement,ReturnBreakdown,Lump,Party,OutworkerPayrollJob
from item_aliases import item_name_suggestions
from datetime import datetime,timedelta,time
from collections import defaultdict
from modes import db
from validation import record_id
from piece_totals import piece_sum
from modes import JobKeptProduct
from kept_products import kept_totals, kept_movement_pairs



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
    return item_name_suggestions()

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

def get_jobcard_return_data(jobcard_id):
    """Given and returned quantities for one card, excluding unlinked legacy returns."""
    card = db.session.get(Jobcard, jobcard_id) if record_id(jobcard_id) else None
    if card is None:
        return None
    movements = Jobmovement.query.filter_by(jobcard=str(card.id)).order_by(Jobmovement.id).all()
    return_ids = [movement.id for movement in movements if movement.flow_type == "IN"]
    breakdowns = {
        row.movement_id: row
        for row in ReturnBreakdown.query.filter(ReturnBreakdown.movement_id.in_(return_ids)).all()
    } if return_ids else {}
    return _build_jobcard_return_data(card, movements, breakdowns)


def _build_jobcard_return_data(card, movements, breakdowns):
    """Share one card's given patterns and return history with reports and entry."""

    def product_key(name, type_name):
        return (str(name).strip().casefold(), str(type_name).strip().casefold())

    given_patterns = defaultdict(dict)
    pattern_totals = defaultdict(int)
    for row in card.product_list if isinstance(card.product_list, list) else []:
        if not isinstance(row, dict):
            continue
        quantity = row.get("qty")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            continue
        pieces = row.get("pieces_per_bundle", quantity)
        count = row.get("bundle_count", 1)
        if (isinstance(pieces, bool) or isinstance(count, bool)
                or not isinstance(pieces, int) or not isinstance(count, int)
                or pieces <= 0 or count <= 0 or pieces * count != quantity):
            continue
        key = product_key(row.get("name_of_prduct", ""), row.get("type", ""))
        given_patterns[key][pieces] = given_patterns[key].get(pieces, 0) + count
        pattern_totals[key] += quantity

    groups = {}
    for movement in movements:
        if movement.name_of_mater != card.given_to:
            continue
        key = (movement.product_name, movement.type_B)
        group = groups.setdefault(key, {"issued_total": 0, "returned_total": 0, "history": []})
        if movement.flow_type == "OUT":
            group["issued_total"] += movement.outflow or 0
        elif movement.flow_type == "IN":
            group["returned_total"] += movement.inflow or 0
            breakdown = breakdowns.get(movement.id)
            group["history"].append({
                "date": movement.date.strftime("%d-%m-%Y"),
                "time": movement.date.strftime("%H:%M"),
                "returned": movement.inflow or 0,
                "entry_method": breakdown.entry_method if breakdown else "legacy",
                "calculation_rows": breakdown.calculation_rows if breakdown else [],
                "entered_by": movement.enter_user,
            })
    items = []
    completed_items = []
    kept = kept_totals()
    for (name, type_name), group in groups.items():
        kept_quantity = kept[(str(card.id), name, type_name)]
        balance = group["issued_total"] - group["returned_total"] - kept_quantity
        key = product_key(name, type_name)
        pattern_rows = ([{"pieces": pieces, "count": count} for pieces, count in given_patterns[key].items()]
                        if pattern_totals[key] == group["issued_total"] else [])
        given = {
            "total": group["issued_total"],
            "date": card.date.strftime("%d-%m-%Y"),
            "time": card.date.strftime("%H:%M"),
            "entered_by": card.given_by,
            "calculation_rows": pattern_rows,
        }
        if balance > 0:
            items.append({
                "item_id": len(items) + 1,
                "name": name.replace(" ", "_"),
                "product_name": name,
                "colour": type_name,
                "issued": balance,
                "kept": kept_quantity,
                "given": given,
                "history": group["history"],
            })
        elif group["issued_total"] > 0 and (group["history"] or kept_quantity):
            completed_items.append({
                "name": name.replace(" ", "_"),
                "product_name": name,
                "colour": type_name,
                "kept": kept_quantity,
                "given": given,
                "history": group["history"],
            })
    return {
        "jobcard_id": card.id,
        "name": card.given_to,
        "date": card.date.strftime("%d %b, %Y"),
        "items": items,
        "completed_items": completed_items,
        "kept_entries": [{'id': row.id, 'product': db.session.get(Item_data, row.product_id).name, 'type': row.bundle_type,
                          'pieces': row.pieces, 'unit_value_paise': row.unit_value_paise,
                          'amount_paise': row.amount_paise, 'advance_id': row.advance_id,
                          'date': row.date.strftime('%d-%m-%Y %H:%M'), 'recorded_by': row.recorded_by,
                          'date_iso': row.date.isoformat(),
                          'note': row.note}
                         for row in JobKeptProduct.query.filter_by(jobcard_id=card.id).order_by(JobKeptProduct.date).all()],
    }


def outworker_job_ledger(name, date_from, date_to, jobcard_id=None):
    """Job cards created in the range, with all returns linked to those cards."""
    card_query = Jobcard.query.filter(
        Jobcard.given_to == name,
        Jobcard.date.between(datetime.combine(date_from, time.min), datetime.combine(date_to, time.max)),
    )
    if jobcard_id is not None:
        card_query = card_query.filter(Jobcard.id == jobcard_id)
    cards = card_query.order_by(Jobcard.date.desc(), Jobcard.id.desc()).all()
    summary = {"jobs": 0, "given": 0, "returned": 0, "kept": 0, "remaining": 0, "open_jobs": 0, "completed_jobs": 0}
    if not cards:
        return {"name": name, "date_from": date_from, "date_to": date_to, "summary": summary, "jobs": []}

    card_ids = {str(card.id) for card in cards}
    paid_jobs = defaultdict(list)
    for row in OutworkerPayrollJob.query.filter(
            OutworkerPayrollJob.jobcard_id.in_([card.id for card in cards])).order_by(OutworkerPayrollJob.id).all():
        paid_jobs[row.jobcard_id].append({"payroll_id": row.payroll_id, "pieces": row.pieces,
                                         "amount_paise": row.amount_paise})
    movements = (Jobmovement.query.filter(Jobmovement.jobcard.in_(card_ids))
                 .order_by(Jobmovement.date, Jobmovement.id).all())
    movement_ids = [movement.id for movement in movements if movement.flow_type == "IN"]
    breakdowns = {
        row.movement_id: row
        for row in ReturnBreakdown.query.filter(ReturnBreakdown.movement_id.in_(movement_ids)).all()
    } if movement_ids else {}
    movements_by_card = defaultdict(list)
    for movement in movements:
        if movement.name_of_mater == name:
            movements_by_card[movement.jobcard].append(movement)

    jobs = []
    for card in cards:
        card_movements = movements_by_card[str(card.id)]
        card_data = _build_jobcard_return_data(card, card_movements, breakdowns)
        products = []
        for item in card_data["items"] + card_data["completed_items"]:
            given = item["given"]["total"]
            returned = sum(entry["returned"] for entry in item["history"])
            products.append({
                "name": item.get("product_name", item["name"]), "type": item["colour"],
                "given": given, "returned": returned, "kept": item.get('kept', 0),
                "remaining": given - returned - item.get('kept', 0),
                "given_patterns": item["given"]["calculation_rows"],
                "returns": item["history"],
            })
        products.sort(key=lambda item: (item["name"].casefold(), item["type"].casefold()))
        given_total = sum(item["given"] for item in products)
        returned_total = sum(item["returned"] for item in products)
        kept_total = sum(item['kept'] for item in products)
        remaining_total = given_total - returned_total - kept_total

        running_balance = 0
        product_balances = defaultdict(int)
        ledger = []
        source_rows = card.product_list if isinstance(card.product_list, list) else []
        used_source_rows = set()
        for movement in card_movements:
            if movement.flow_type not in ("OUT", "IN"):
                continue
            given_qty = (movement.outflow or 0) if movement.flow_type == "OUT" else 0
            returned_qty = (movement.inflow or 0) if movement.flow_type == "IN" else 0
            running_balance += given_qty - returned_qty
            product_key = (movement.product_name, movement.type_B)
            product_balances[product_key] += given_qty - returned_qty
            breakdown = breakdowns.get(movement.id)
            calculation_rows = breakdown.calculation_rows if breakdown else []
            if movement.flow_type == "OUT":
                matching_rows = []
                for index, source in enumerate(source_rows):
                    if index in used_source_rows or not isinstance(source, dict):
                        continue
                    source_name = str(source.get("name_of_prduct", "")).strip().casefold()
                    movement_name = movement.product_name.strip().casefold()
                    if (source_name != movement_name or source.get("type") != movement.type_B
                            or source.get("qty") != given_qty):
                        continue
                    source_id = str(source.get("item_id") or "")
                    exact_reference = (source_id == str(movement.bundle) if movement.bundle
                                       else bool(source_id) and movement.partculer.endswith(source_id))
                    if exact_reference:
                        matching_rows = [(index, source)]
                        break
                    if not source_id:
                        matching_rows.append((index, source))
                if len(matching_rows) == 1:
                    index, source = matching_rows[0]
                    pieces = source.get("pieces_per_bundle", given_qty)
                    count = source.get("bundle_count", 1)
                    if (isinstance(pieces, int) and not isinstance(pieces, bool)
                            and isinstance(count, int) and not isinstance(count, bool)
                            and pieces > 0 and count > 0 and pieces * count == given_qty):
                        calculation_rows = [{"pieces": pieces, "count": count}]
                        used_source_rows.add(index)
                elif movement.bundle and given_qty > 0:
                    calculation_rows = [{"pieces": given_qty, "count": 1}]
            ledger.append({
                "id": movement.id, "date": movement.date, "product": movement.product_name,
                "flow_type": movement.flow_type,
                "type": movement.type_B, "given": given_qty, "returned": returned_qty,
                "balance": running_balance, "product_balance": product_balances[product_key],
                "bundle": movement.bundle if movement.flow_type == "OUT" else None,
                "method": breakdown.entry_method if breakdown else "legacy" if movement.flow_type == "IN" else "given",
                "calculation_rows": calculation_rows,
                "entered_by": movement.enter_user,
            })

        for entry in card_data['kept_entries']:
            ledger.append({'id': f'K{entry["id"]}', 'date': datetime.fromisoformat(entry['date_iso']),
                'product': entry['product'], 'type': entry['type'], 'flow_type': 'KEPT', 'given': 0, 'returned': 0,
                'kept': entry['pieces'], 'amount_paise': entry['amount_paise'], 'advance_id': entry['advance_id'],
                'entered_by': entry['recorded_by'], 'bundle': None, 'method': 'kept', 'calculation_rows': []})
        ledger.sort(key=lambda entry: (entry['date'], entry['flow_type'] == 'KEPT', int(str(entry['id']).lstrip('K'))))
        running_balance = 0
        product_balances = defaultdict(int)
        for entry in ledger:
            delta = entry['given'] - entry['returned'] - entry.get('kept', 0)
            running_balance += delta
            product_key = (entry['product'], entry['type'])
            product_balances[product_key] += delta
            entry.update(balance=running_balance, product_balance=product_balances[product_key])
        status = ("Check balance" if any(item['remaining'] < 0 for item in products)
                  else "Open" if any(item['remaining'] > 0 for item in products)
                  else "Complete" if given_total else "No movements")
        payments = paid_jobs[card.id]
        paid_pieces = sum(payment['pieces'] for payment in payments)
        jobs.append({
            "id": card.id, "date": card.date, "given_by": card.given_by,
            "payroll_id": payments[-1]['payroll_id'] if payments else None,
            "payrolls": payments, "paid_pieces": paid_pieces,
            "payment_status": ('check' if paid_pieces > given_total else
                               'paid' if given_total > 0 and paid_pieces == given_total else
                               'partial' if paid_pieces > 0 else 'unpaid'),
            "payable_pieces": max(0, returned_total + kept_total - paid_pieces),
            "unpaid_pieces": max(0, given_total - paid_pieces),
            "last_activity": ledger[-1]['date'] if ledger else card.date,
            "given": given_total, "returned": returned_total, "kept": kept_total, "remaining": remaining_total,
            "kept_entries": card_data['kept_entries'],
            "status": status, "products": products, "ledger": ledger,
        })
        summary["jobs"] += 1
        summary["given"] += given_total
        summary["returned"] += returned_total
        summary['kept'] += kept_total
        summary["remaining"] += remaining_total
        summary["open_jobs"] += status == "Open"
        summary["completed_jobs"] += status == "Complete"
    return {"name": name, "date_from": date_from, "date_to": date_to, "summary": summary, "jobs": jobs}


def outworker_period_account(name, date_from, date_to):
    """Piece account by movement dates, including balances from older jobs."""
    start = datetime.combine(date_from, time.min)
    end = datetime.combine(date_to, time.max)
    cards = {str(card.id): card for card in Jobcard.query.filter(
        Jobcard.given_to == name, Jobcard.date <= end,
    ).all()}
    rows = (Jobmovement.query.filter(
        Jobmovement.jobcard.in_(list(cards)), Jobmovement.name_of_mater == name,
        Jobmovement.date <= end, Jobmovement.flow_type.in_(["OUT", "IN"]),
    ).order_by(Jobmovement.date, Jobmovement.id).all()) if cards else []
    rows += [row for row, card in kept_movement_pairs() if row.jobcard in cards and row.date <= end]
    rows.sort(key=lambda row: (row.date, row.flow_type == 'KEPT', int(str(row.id).lstrip('K'))))
    totals = {"opening": 0, "given": 0, "returned": 0, "closing": 0,
              "incomplete_jobs": 0, "pieces_left": 0, 'kept': 0}
    products = {}
    jobs = {}
    for row in rows:
        key = (row.product_name, row.type_B)
        product = products.setdefault(key, {
            "name": row.product_name, "type": row.type_B,
            "opening": 0, "given": 0, "returned": 0, "closing": 0, 'kept': 0,
            "pieces_left": 0, "incomplete_jobs": 0, "jobs": [],
        })
        given = (row.outflow or 0) if row.flow_type == "OUT" else 0
        returned = (row.inflow or 0) if row.flow_type == "IN" else 0
        kept = getattr(row, 'kept', 0)
        if row.date < start:
            product["opening"] += given - returned - kept
        else:
            product["given"] += given
            product["returned"] += returned
            product['kept'] += kept
        product["closing"] += given - returned - kept
        job = jobs.setdefault(row.jobcard, {
            "id": cards[row.jobcard].id, "date": cards[row.jobcard].date,
            "given": 0, "returned": 0, "remaining": 0, "pieces_left": 0,
            "products": {},
        })
        job["given"] += given
        job["returned"] += returned
        job['kept'] = job.get('kept', 0) + kept
        job["remaining"] += given - returned - kept
        detail = job["products"].setdefault(key, {
            "name": product["name"], "type": row.type_B,
            "given": 0, "returned": 0, "remaining": 0,
        })
        detail["given"] += given
        detail["returned"] += returned
        detail['kept'] = detail.get('kept', 0) + kept
        detail["remaining"] += given - returned - kept

    outstanding = []
    for job in jobs.values():
        for key, detail in job["products"].items():
            if detail["remaining"] > 0:
                job["pieces_left"] += detail["remaining"]
                products[key]["pieces_left"] += detail["remaining"]
                products[key]["incomplete_jobs"] += 1
            products[key]["jobs"].append({
                "id": job["id"], "date": job["date"], **detail,
            })
        job["products"] = sorted(job["products"].values(), key=lambda item: (item["name"], item["type"]))
        if job["pieces_left"] > 0:
            outstanding.append(job)
            totals["pieces_left"] += job["pieces_left"]
    totals["incomplete_jobs"] = len(outstanding)
    for product in products.values():
        for field in ("opening", "given", "returned", "closing", 'kept'):
            totals[field] += product[field]
    return {
        "totals": totals,
        "products": sorted(products.values(), key=lambda item: (item["name"], item["type"])),
        "outstanding_jobs": sorted(outstanding, key=lambda job: (job["date"], job["id"])),
    }


def get_jobcard_ledger(jobcard_id):
    """Full linked movement history for one job card, independent of report dates."""
    card = db.session.get(Jobcard, jobcard_id) if record_id(jobcard_id) else None
    if card is None:
        return None
    report = outworker_job_ledger(card.given_to, card.date.date(), card.date.date(), jobcard_id=card.id)
    return {"outworker": card.given_to, "job": report["jobs"][0]} if report["jobs"] else None


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
