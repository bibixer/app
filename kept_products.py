"""Explicit stock retention, payable pieces and recoverable product value."""
from collections import defaultdict
from datetime import datetime
from types import SimpleNamespace

from modes import db, Item_data, Jobcard, JobKeptProduct, Jobmovement, Outworker, OutworkerAdvance, EditLog
from validation import record_id, MAX_PIECES


def kept_totals(*, before=None):
    query = JobKeptProduct.query
    if before is not None:
        query = query.filter(JobKeptProduct.date < before)
    names = {row.id: row.name for row in Item_data.query.all()}
    totals = defaultdict(int)
    for row in query.all():
        totals[(str(row.jobcard_id), names.get(row.product_id, row.product_name), row.bundle_type)] += row.pieces
    return totals


def kept_movement_pairs(before=None):
    """Read-only ledger projections; never write kept pieces as physical inflow."""
    query = db.session.query(JobKeptProduct, Jobcard, Item_data).join(
        Jobcard, JobKeptProduct.jobcard_id == Jobcard.id).join(Item_data, JobKeptProduct.product_id == Item_data.id)
    if before is not None:
        query = query.filter(JobKeptProduct.date < before)
    return [(SimpleNamespace(id=f'K{row.id}', date=row.date, jobcard=str(card.id),
              product_name=product.name, type_B=row.bundle_type, name_of_mater=card.given_to,
              enter_user=row.recorded_by, flow_type='KEPT', outflow=0, inflow=0, kept=row.pieces,
              bundle=None, partculer=f'Kept {row.pieces}; recovery {row.amount_paise / 100:.2f}; Advance #{row.advance_id}'), card)
            for row, card, product in query.all()]


def save_product_value(product_id, value, expected_value, token, user):
    from data_entry import claim_write
    from payroll_service import parse_money
    try:
        if user.role != 1 or not user.is_active:
            raise ValueError('Only an administrator can set product values.')
        if not claim_write(token, 'product_value', user, dict(product_id=product_id, value=value, expected=expected_value)):
            return
        product = db.session.get(Item_data, record_id(product_id)) if record_id(product_id) else None
        if not product:
            raise ValueError('Select an existing product.')
        if str(product.product_value_paise) != str(expected_value):
            raise ValueError('This product value changed. Reload and review it.')
        amount = parse_money(value)
        old = product.product_value_paise
        product.product_value_paise = amount
        db.session.add(EditLog(entity_type='product_value', entity_id=product.id, action='UPDATE',
            old_values={'value_paise': old}, new_values={'value_paise': amount},
            changed_fields=['value_paise'], username=user.username, changed_at=datetime.now()))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def record_kept_product(card_id, product_id, bundle_type, quantity, expected_value,
                        expected_remaining, confirmed, note, token, user):
    from data_entry import claim_write, record_receipt, saved_receipt
    from data_Process import get_jobcard_return_data
    from payroll_service import MAX_PAISE, worker_label
    try:
        if not user.is_authenticated or not user.is_active or user.role not in (1, 2):
            raise ValueError('Login as an administrator or operator to record kept pieces.')
        payload = dict(card_id=card_id, product_id=product_id, bundle_type=bundle_type, quantity=quantity,
                       expected_value=expected_value, expected_remaining=expected_remaining,
                       confirmed=confirmed, note=note)
        if not claim_write(token, 'kept_product', user, payload):
            receipt = saved_receipt(token, 'kept_product', user)
            return db.session.get(JobKeptProduct, receipt.get('kept_id'))
        card = db.session.get(Jobcard, record_id(card_id)) if record_id(card_id) else None
        product = db.session.get(Item_data, record_id(product_id)) if record_id(product_id) else None
        if not card or not product:
            raise ValueError('Select an existing job and product.')
        worker_id = record_id(card.given_to.split('***', 1)[0])
        worker = db.session.get(Outworker, worker_id) if worker_id else None
        if not worker or worker_label(worker) != card.given_to:
            raise ValueError('This job must belong to an outworker in Setup.')
        quantity = record_id(quantity)
        if not quantity or quantity > MAX_PIECES:
            raise ValueError('Enter a positive whole number of kept pieces.')
        if confirmed != 'yes':
            raise ValueError('Confirm the product-value recovery before saving.')
        current = get_jobcard_return_data(card.id)
        item = next((row for row in current['items'] if row['product_name'] == product.name
                     and row['colour'] == bundle_type), None)
        if not item or quantity > item['issued']:
            raise ValueError('Kept pieces cannot exceed the remaining balance for this product and type.')
        if str(item['issued']) != str(expected_remaining) or str(product.product_value_paise) != str(expected_value):
            raise ValueError('The job balance or product value changed. Reload and confirm again.')
        amount = quantity * product.product_value_paise
        if product.product_value_paise <= 0 or amount > MAX_PAISE:
            raise ValueError('Set a positive product value in Product rates; the recovery must fit the payment limit.')
        if len(str(note or '')) > 500:
            raise ValueError('Notes must be at most 500 characters.')
        now = datetime.now()
        if Jobmovement.query.filter_by(jobcard=str(card.id), product_name=product.name, type_B=bundle_type).filter(
                Jobmovement.date > now).first():
            raise ValueError('This product has future-dated job movements. Correct those dates before recording kept pieces.')
        advance = OutworkerAdvance(worker_id=worker.id, worker_name=worker_label(worker), amount_paise=amount,
            paid_at=now, method='Other', reference=f'Job #{card.id} · kept product',
            note=f'{quantity} × {product.name} ({bundle_type}) at {product.product_value_paise / 100:.2f} per piece. Product retained; no cash given.'[:500],
            recorded_by=user.username)
        db.session.add(advance)
        db.session.flush()
        row = JobKeptProduct(jobcard_id=card.id, product_id=product.id, worker_id=worker.id,
            advance_id=advance.id, product_name=product.name, bundle_type=bundle_type,
            pieces=quantity, unit_value_paise=product.product_value_paise, amount_paise=amount,
            date=now, recorded_by=user.username, note=str(note or ''))
        db.session.add(row)
        db.session.flush()
        db.session.add(EditLog(entity_type='kept_product', entity_id=row.id, action='CREATE', old_values={},
            new_values={**payload, 'advance_id': advance.id, 'amount_paise': amount},
            changed_fields=['pieces', 'advance_id'], username=user.username, changed_at=now))
        record_receipt(token, 'kept_product', user, {'kept_id': row.id, 'advance_id': advance.id})
        db.session.commit()
        return row
    except Exception:
        db.session.rollback()
        raise
