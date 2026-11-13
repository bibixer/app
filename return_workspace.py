"""Open job cards for one outworker; return writes still use the existing job endpoint."""

from sqlalchemy import func
from master_aliases import master_full_name
from modes import db, Jobcard, Jobmovement
from validation import record_id
from kept_products import kept_totals
from piece_totals import piece_sum


def open_outworker_jobs(worker):
    name = master_full_name(worker)
    groups = db.session.query(Jobmovement.jobcard, Jobmovement.product_name, Jobmovement.type_B,
                              func.coalesce(piece_sum(Jobmovement.outflow), 0),
                              func.coalesce(piece_sum(Jobmovement.inflow), 0)).filter(
        Jobmovement.name_of_mater == name,
    ).group_by(Jobmovement.jobcard, Jobmovement.product_name, Jobmovement.type_B).all()
    pending = {}
    kept = kept_totals()
    for raw_id, product, kind, given, returned in groups:
        card_id = record_id(raw_id)
        balance = given - returned - kept[(str(card_id), product, kind)]
        if card_id and balance > 0:
            pending[card_id] = pending.get(card_id, 0) + balance
    cards = Jobcard.query.filter(Jobcard.given_to == name, Jobcard.id.in_(pending)).order_by(Jobcard.date, Jobcard.id).all() if pending else []
    return [{'card': card, 'pending': pending[card.id]} for card in cards]
