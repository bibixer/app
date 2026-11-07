"""Open job cards for one outworker; return writes still use the existing job endpoint."""

from sqlalchemy import func
from master_aliases import master_full_name
from modes import db, Jobcard, Jobmovement
from validation import record_id


def open_outworker_jobs(worker):
    name = master_full_name(worker)
    groups = db.session.query(Jobmovement.jobcard,
                              func.coalesce(func.sum(Jobmovement.outflow), 0),
                              func.coalesce(func.sum(Jobmovement.inflow), 0)).filter(
        Jobmovement.name_of_mater == name,
    ).group_by(Jobmovement.jobcard, Jobmovement.product_name, Jobmovement.type_B).all()
    pending = {}
    for raw_id, given, returned in groups:
        card_id = record_id(raw_id)
        if card_id and given > returned:
            pending[card_id] = pending.get(card_id, 0) + given - returned
    cards = Jobcard.query.filter(Jobcard.given_to == name, Jobcard.id.in_(pending)).order_by(Jobcard.date, Jobcard.id).all() if pending else []
    return [{'card': card, 'pending': pending[card.id]} for card in cards]
