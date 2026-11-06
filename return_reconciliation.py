"""Assign historical return movements to a verified job card."""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import or_, func

from data_entry import claim_write
from modes import db, Jobcard, Jobmovement, EditLog


def _unassigned():
    return or_(Jobmovement.jobcard.is_(None), func.trim(Jobmovement.jobcard) == "")


def matching_jobs(movement):
    """Only offer cards issued before this return with enough product balance."""
    if movement.flow_type != "IN" or (movement.inflow or 0) <= 0:
        return []
    cards = Jobcard.query.filter(
        Jobcard.given_to == movement.name_of_mater,
        Jobcard.date <= movement.date,
    ).order_by(Jobcard.date, Jobcard.id).all()
    if not cards:
        return []
    rows = Jobmovement.query.filter(
        Jobmovement.jobcard.in_([str(card.id) for card in cards]),
        Jobmovement.name_of_mater == movement.name_of_mater,
        Jobmovement.product_name == movement.product_name,
        Jobmovement.type_B == movement.type_B,
    ).all()
    balances = defaultdict(int)
    issued_before_return = defaultdict(int)
    for row in rows:
        if row.flow_type == "OUT":
            balances[row.jobcard] += row.outflow or 0
            if row.date <= movement.date:
                issued_before_return[row.jobcard] += row.outflow or 0
        elif row.flow_type == "IN":
            balances[row.jobcard] -= row.inflow or 0
    return [{"id": card.id, "date": card.date, "remaining": balances[str(card.id)]}
            for card in cards
            if balances[str(card.id)] >= movement.inflow
            and issued_before_return[str(card.id)] >= movement.inflow]


def unassigned_returns(worker):
    rows = Jobmovement.query.filter(
        Jobmovement.name_of_mater == worker,
        Jobmovement.flow_type == "IN", _unassigned(),
    ).order_by(Jobmovement.date, Jobmovement.id).all()
    return [{"movement": row, "jobs": matching_jobs(row)} for row in rows]


def assign_return(movement_id, card_id, user):
    """Claim first so concurrent assignments cannot consume the same balance."""
    try:
        if not claim_write(f"legacy-return-{movement_id}", "assign_return", user):
            raise ValueError("This return was already submitted. Refresh the ledger.")
        movement = db.session.get(Jobmovement, movement_id, populate_existing=True)
        if movement is None or movement.flow_type != "IN":
            raise ValueError("Return entry was not found.")
        if movement.jobcard and movement.jobcard.strip():
            raise ValueError("This return already belongs to a job card.")
        if card_id not in {card["id"] for card in matching_jobs(movement)}:
            raise ValueError("Select a matching job with enough remaining pieces, issued before this return.")
        old = movement.jobcard
        movement.jobcard = str(card_id)
        db.session.add(EditLog(
            entity_type="movement", entity_id=movement.id, action="UPDATE",
            old_values={"jobcard": old}, new_values={"jobcard": str(card_id)},
            changed_fields=["jobcard"], username=user.username,
            changed_at=datetime.now(),
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
