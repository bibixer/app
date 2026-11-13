"""Relationship and quantity rules used by the edit center."""

from collections import defaultdict
from sqlalchemy import cast, String

from bundle_types import BUNDLE_TYPE_VALUES
from item_aliases import resolve_item_name
from master_aliases import resolve_master_name
from modes import db, Bundle, Jobcard, Jobmovement, Lump, OutworkerPayrollJob
from validation import record_id


def _parent_bundles(entity_type, obj):
    if entity_type == "lump":
        return Bundle.query.filter_by(lump_id=obj.id).all()
    return Bundle.query.join(Lump, Bundle.lump_id == Lump.id).filter(Lump.bale_id == obj.id).all()


def validate_update(entity_type, obj, updates, old):
    if entity_type == "lump" and updates["meters"] + updates["meters_add_remove"] <= 0:
        raise ValueError("The lump must have a positive total meter quantity.")
    if entity_type in {"bale", "lump"} and any(
        name in updates and updates[name] != old.get(name) for name in ("product", "bundle_type", "color")
    ):
        bundles = _parent_bundles(entity_type, obj)
        paid = Jobmovement.query.filter(
            Jobmovement.bundle.in_([str(bundle.id) for bundle in bundles]),
            Jobmovement.jobcard.in_(db.session.query(cast(OutworkerPayrollJob.jobcard_id, String))),
        ).first() if bundles else None
        if paid:
            raise ValueError("This entry contains a bundle linked to an issued payroll.")
    type_field = {"bundle": "type_B", "movement": "type_B", "lump": "bundle_type"}.get(entity_type)
    if type_field and updates[type_field] not in BUNDLE_TYPE_VALUES:
        raise ValueError("Select a bundle type defined in the app.")
    if entity_type == "jobcard":
        worker = resolve_master_name(updates["given_to"])
        if worker is None:
            raise ValueError("Select an outworker from Setup.")
        updates["given_to"] = worker
    if entity_type == "bundle":
        if updates["pieces"] <= 0 or not db.session.get(Lump, updates.get("lump_id", obj.lump_id)):
            raise ValueError("A bundle needs a valid lump and a positive piece count.")
        movements = Jobmovement.query.filter_by(bundle=str(obj.id), flow_type="OUT").all()
        if movements:
            if updates["status"] != "GIVEN":
                raise ValueError("An issued bundle cannot be made READY and issued again.")
            if any(row.name_of_mater != updates["given_to"] for row in movements):
                raise ValueError("Transfer the outworker by editing the job card, so returns stay linked.")
        elif updates["status"] != "READY" or updates["given_to"]:
            raise ValueError("Use a job card to assign a ready bundle to an outworker.")
    if entity_type == "movement":
        if updates["flow_type"] == "OUT":
            if updates["outflow"] <= 0 or updates["inflow"]:
                raise ValueError("A given entry needs positive outflow and zero inflow.")
            if old["jobcard"] and updates["jobcard"] != old["jobcard"]:
                raise ValueError("An issued movement's job card reference cannot be changed.")
            if updates["bundle"] != old["bundle"]:
                raise ValueError("An issued movement's bundle reference cannot be changed.")
        elif updates["inflow"] <= 0 or updates["outflow"]:
            raise ValueError("A return entry needs positive inflow and zero outflow.")
        if updates["jobcard"]:
            card_id = record_id(updates["jobcard"])
            card = db.session.get(Jobcard, card_id) if card_id else None
            if card is None:
                raise ValueError("The referenced job card does not exist.")
            updates["jobcard"] = str(card.id)
            if updates["name_of_mater"] != card.given_to:
                raise ValueError("The movement's outworker must match its job card.")
        elif updates["flow_type"] == "OUT":
            raise ValueError("Every given entry must have a job card number.")
    field = {"bundle": "product", "lump": "product", "movement": "product_name"}.get(entity_type)
    if field:
        name = resolve_item_name(updates[field])
        if name is None:
            raise ValueError("Select a product from Item Setup.")
        updates[field] = name


def validate_affected_jobs(entity_type, obj, old):
    if entity_type == "jobcard":
        ids = {obj.id}
    elif entity_type == "movement":
        ids = {record_id(value) for value in (old["jobcard"], obj.jobcard)} - {None}
    elif entity_type == "bundle":
        ids = {record_id(row.jobcard) for row in Jobmovement.query.filter_by(bundle=str(obj.id)).all()} - {None}
    elif entity_type in {"lump", "bale"}:
        bundle_ids = [str(bundle.id) for bundle in _parent_bundles(entity_type, obj)]
        ids = {record_id(row.jobcard) for row in Jobmovement.query.filter(Jobmovement.bundle.in_(bundle_ids)).all()} - {None}
    else:
        return
    for card_id in ids:
        from modes import JobKeptProduct
        if JobKeptProduct.query.filter_by(jobcard_id=card_id).first():
            raise ValueError('This stock entry belongs to a job with kept-product recoveries and cannot be corrected independently.')
        card = db.session.get(Jobcard, card_id)
        if card is None:
            raise ValueError("A linked job card is missing.")
        balances = defaultdict(int)
        for row in Jobmovement.query.filter_by(jobcard=str(card_id)).all():
            if row.name_of_mater != card.given_to:
                raise ValueError("All movements must belong to the job card's outworker.")
            key = (row.product_name, row.type_B)
            balances[key] += (row.outflow or 0) if row.flow_type == "OUT" else -(row.inflow or 0)
        if any(balance < 0 for balance in balances.values()):
            raise ValueError("This edit would make returns exceed the pieces given on a job card.")
