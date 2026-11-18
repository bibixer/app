"""Product rates, advance balances, and immutable payments for returned job pieces."""

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError

from bundle_types import BUNDLE_TYPE_VALUES
from data_entry import claim_write
from item_aliases import normalize_name
from validation import record_id
from kept_products import kept_totals
from modes import JobKeptProduct
from modes import (db, Item_data, Outworker, Jobcard, Jobmovement, EditLog,
                   OutworkerRate, OutworkerAdvance, OutworkerPayroll, OutworkerPayrollJob,
                   OutworkerAdvanceRecovery, OutworkerAdvanceReceipt)

MAX_PAISE = 99_999_999_999
PAYMENT_METHODS = ("Cash", "Bank", "UPI", "Other")


def worker_label(worker):
    return f"{worker.id}***{worker.name}--{worker.adders}/-"


def money(paise):
    return f"{Decimal(paise) / 100:,.2f}"


def money_input(paise):
    return f"{Decimal(paise) / 100:.2f}"


def rate_text(units):
    return format(Decimal(units) / 10000, ".4f").rstrip("0").rstrip(".")


def _decimal(value, places, maximum, label):
    try:
        amount = Decimal(str(value))
        if (not amount.is_finite() or amount < 0 or amount > maximum
                or amount != amount.quantize(Decimal(1).scaleb(-places))):
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label} must be a non-negative number with up to {places} decimal places.") from None
    return amount


def parse_money(value):
    return int(_decimal(value, 2, Decimal(MAX_PAISE) / 100, "Amount") * 100)


def _claim(token, endpoint, user, payload):
    username = user.username
    if not claim_write(token, endpoint, user, payload):
        raise ValueError("This submission was already saved. Refresh to see the saved record.")
    # The claim takes SQLite's write lock before balances and rates are re-read.
    db.session.expire_all()
    return username


def _details(method, reference, note):
    if method not in PAYMENT_METHODS:
        raise ValueError("Select a payment method.")
    reference, note = str(reference or "").strip(), str(note or "").strip()
    if len(reference) > 100 or len(note) > 500:
        raise ValueError("Reference must be at most 100 characters and notes at most 500.")
    return reference, note


def rate_version(row):
    return (f"{row.id}:{row.rate_units}:{row.updated_at.isoformat()}" if row else "new")


def save_rate(product_id, bundle_type, value, expected_version, token, user, remove=False, *, commit=True):
    try:
        username = _claim(token, "outworker_rate", user, dict(product_id=product_id, bundle_type=bundle_type,
                          value=value, version=expected_version, remove=remove))
        if record_id(product_id) is None or not db.session.get(Item_data, product_id):
            raise ValueError("Select an existing product.")
        if bundle_type and bundle_type not in BUNDLE_TYPE_VALUES:
            raise ValueError("Select a listed bundle type or the base rate.")
        row = OutworkerRate.query.filter_by(product_id=product_id, bundle_type=bundle_type).first()
        if rate_version(row) != expected_version:
            raise ValueError("This rate changed. Reload the page before editing it.")
        old = {"product_id": product_id, "bundle_type": bundle_type,
               "rate": rate_text(row.rate_units) if row else None}
        if remove:
            if not row:
                raise ValueError("This rate is already unset.")
            entity_id = row.id
            db.session.delete(row)
            new_rate = None
        else:
            amount = _decimal(value, 4, Decimal("999999.9999"), "Rate")
            if amount <= 0:
                raise ValueError("Rate per piece must be greater than zero.")
            if row is None:
                row = OutworkerRate(product_id=product_id, bundle_type=bundle_type)
                db.session.add(row)
            row.rate_units = int(amount * 10000)
            row.updated_by, row.updated_at = username, datetime.now()
            db.session.flush()
            entity_id, new_rate = row.id, rate_text(row.rate_units)
        db.session.add(EditLog(
            entity_type="outworker_rate", entity_id=entity_id,
            action="DELETE" if remove else "UPDATE" if old["rate"] is not None else "CREATE",
            old_values=old, new_values={**old, "rate": new_rate}, changed_fields=["rate"],
            username=username, changed_at=datetime.now(),
        ))
        if commit:
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def save_rate_page_changes(product_id, changes, next_product_id, token, user):
    """Save dirty rate/value fields together; no partial save before switching."""
    from data_entry import claim_write
    from kept_products import save_product_value
    try:
        if user.role != 1 or not user.is_active:
            raise ValueError('Only an administrator can update rates.')
        if not isinstance(token, str) or not token.strip() or len(token) > 128:
            raise ValueError('A valid submission token is required.')
        if not isinstance(changes, list) or not 1 <= len(changes) <= len(BUNDLE_TYPE_VALUES) + 2:
            raise ValueError('Select valid changes to save.')
        if not record_id(product_id) or not db.session.get(Item_data, product_id):
            raise ValueError('Select an existing product.')
        if not record_id(next_product_id) or not db.session.get(Item_data, next_product_id):
            raise ValueError('Select an existing destination product.')
        payload = dict(product_id=product_id, next_product_id=next_product_id, changes=changes)
        if not claim_write(token, 'rate_page_changes', user, payload):
            return
        seen = set()
        for change in changes:
            if not isinstance(change, dict) or change.get('field') not in {'rate', 'product_value'}:
                raise ValueError('Invalid rate or product value change.')
            kind = change['field']
            bundle_type = change.get('bundle_type', '')
            key = (kind, bundle_type if kind == 'rate' else '')
            if key in seen:
                raise ValueError('A field was supplied more than once.')
            seen.add(key)
            child_token = hashlib.sha256(f'{token}:{kind}:{bundle_type}'.encode()).hexdigest()
            if kind == 'product_value':
                save_product_value(product_id, change.get('value'), change.get('version'),
                                   child_token, user, commit=False)
            else:
                value = str(change.get('value', '')).strip()
                save_rate(product_id, bundle_type, value, change.get('version'), child_token, user,
                          remove=value == '', commit=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def advance_balance(worker_id):
    advances = db.session.query(db.func.coalesce(db.func.sum(OutworkerAdvance.amount_paise), 0)).filter(
        OutworkerAdvance.worker_id == worker_id).scalar()
    deductions = db.session.query(db.func.coalesce(db.func.sum(OutworkerPayroll.deduction_paise), 0)).filter(
        OutworkerPayroll.worker_id == worker_id).scalar()
    receipts = db.session.query(db.func.coalesce(db.func.sum(OutworkerAdvanceReceipt.amount_paise), 0)).filter(
        OutworkerAdvanceReceipt.worker_id == worker_id).scalar()
    return int(advances) - int(deductions) - int(receipts)


def advance_entries(worker_id):
    """Outstanding amounts; historical aggregate deductions consume oldest first.

    New recoveries are permanently linked to individual advances. Older receipts
    remain untouched, with their unallocated deductions accounted for FIFO.
    """
    rows = OutworkerAdvance.query.filter_by(worker_id=worker_id).order_by(
        OutworkerAdvance.paid_at, OutworkerAdvance.id).all()
    recovered = dict(db.session.query(
        OutworkerAdvanceRecovery.advance_id, db.func.sum(OutworkerAdvanceRecovery.amount_paise)
    ).join(OutworkerPayroll, OutworkerPayroll.id == OutworkerAdvanceRecovery.payroll_id).filter(
        OutworkerPayroll.worker_id == worker_id).group_by(OutworkerAdvanceRecovery.advance_id).all())
    total_deducted = db.session.query(db.func.coalesce(db.func.sum(OutworkerPayroll.deduction_paise), 0)).filter(
        OutworkerPayroll.worker_id == worker_id).scalar()
    legacy = int(total_deducted) - sum(recovered.values())
    for advance_id, amount in db.session.query(
            OutworkerAdvanceReceipt.advance_id, db.func.sum(OutworkerAdvanceReceipt.amount_paise)).filter(
            OutworkerAdvanceReceipt.worker_id == worker_id).group_by(OutworkerAdvanceReceipt.advance_id).all():
        recovered[advance_id] = recovered.get(advance_id, 0) + int(amount)
    result = []
    for row in rows:
        left = row.amount_paise - recovered.get(row.id, 0)
        historical = min(left, legacy)
        legacy -= historical
        result.append({"id": row.id, "date": row.paid_at, "method": row.method,
                       "reference": row.reference, "amount_paise": row.amount_paise,
                       "remaining_paise": left - historical})
    return result


def receive_advance(worker_id, advance_id, amount, expected_remaining, method, reference, note, token, user):
    """Record a partial/full repayment under the same lock as payroll writes."""
    try:
        username = _claim(token, "outworker_advance_receipt", user, dict(worker_id=worker_id, advance_id=advance_id,
                          amount=amount, remaining=expected_remaining, method=method, reference=reference, note=note))
        worker = db.session.get(Outworker, worker_id) if record_id(worker_id) else None
        if not worker:
            raise ValueError("Select an existing outworker.")
        entry = next((row for row in advance_entries(worker_id) if row['id'] == record_id(advance_id)), None)
        if not entry or entry['remaining_paise'] <= 0:
            raise ValueError("Select an outstanding advance belonging to this outworker.")
        if not str(expected_remaining).isdigit() or int(expected_remaining) != entry['remaining_paise']:
            raise ValueError("This advance balance changed. Reload the account before recording money received.")
        amount = parse_money(amount)
        if amount <= 0 or amount > entry['remaining_paise']:
            raise ValueError("Money received must be greater than zero and cannot exceed this advance’s outstanding amount.")
        reference, note = _details(method, reference, note)
        receipt = OutworkerAdvanceReceipt(worker_id=worker.id, advance_id=entry['id'],
            worker_name=worker_label(worker), amount_paise=amount, received_at=datetime.now(),
            method=method, reference=reference, note=note, recorded_by=username)
        db.session.add(receipt)
        db.session.commit()
        return receipt
    except Exception:
        db.session.rollback()
        raise


def receive_selected_advances(worker_id, advance_ids, expected_snapshot, expected_total,
                              method, reference, note, token, user):
    """Confirm the advance-only popup atomically, without issuing a payroll."""
    try:
        username = _claim(token, "outworker_advance_batch_receipt", user, dict(worker_id=worker_id, advance_ids=advance_ids,
                          snapshot=expected_snapshot, total=expected_total, method=method, reference=reference, note=note))
        worker = db.session.get(Outworker, worker_id) if record_id(worker_id) else None
        if not worker:
            raise ValueError("Select an existing outworker.")
        selected = {record_id(value) for value in advance_ids}
        entries = [row for row in advance_entries(worker_id) if row['id'] in selected and row['remaining_paise'] > 0]
        if not selected or None in selected or len(entries) != len(selected):
            raise ValueError("Select outstanding advances belonging to this outworker.")
        original = {row['id']: row['remaining_paise'] for row in expected_snapshot['advances']}
        if (expected_snapshot['worker'] != worker_label(worker)
                or expected_snapshot['available'] != advance_balance(worker_id)
                or any(original.get(row['id']) != row['remaining_paise'] for row in entries)):
            raise ValueError("Advance balances changed. Reload the account and review the money received again.")
        total = sum(row['remaining_paise'] for row in entries)
        if parse_money(expected_total) != total:
            raise ValueError("The amount received does not match the selected advances. Calculate again.")
        reference, note = _details(method, reference, note)
        now = datetime.now()
        for entry in entries:
            db.session.add(OutworkerAdvanceReceipt(worker_id=worker.id, advance_id=entry['id'],
                worker_name=worker_label(worker), amount_paise=entry['remaining_paise'], received_at=now,
                method=method, reference=reference, note=note, recorded_by=username))
        db.session.commit()
        return total
    except Exception:
        db.session.rollback()
        raise


def record_advance(worker_id, amount, method, reference, note, token, user):
    try:
        username = _claim(token, "outworker_advance", user, dict(worker_id=worker_id, amount=amount,
                          method=method, reference=reference, note=note))
        worker = db.session.get(Outworker, worker_id) if record_id(worker_id) else None
        if not worker:
            raise ValueError("Select an existing outworker.")
        amount = parse_money(amount)
        if amount <= 0:
            raise ValueError("Advance must be greater than zero.")
        reference, note = _details(method, reference, note)
        advance = OutworkerAdvance(
            worker_id=worker.id, worker_name=worker_label(worker), amount_paise=amount,
            paid_at=datetime.now(), method=method, reference=reference, note=note,
            recorded_by=username,
        )
        db.session.add(advance)
        db.session.commit()
        return advance
    except Exception:
        db.session.rollback()
        raise


def payable_job_quotes(worker):
    """Quote only returned pieces that have not appeared on an issued payroll."""
    cards = Jobcard.query.filter_by(given_to=worker_label(worker)).order_by(Jobcard.id).all()
    if not cards:
        return []
    paid = defaultdict(list)
    for payment in OutworkerPayrollJob.query.filter(
            OutworkerPayrollJob.jobcard_id.in_([card.id for card in cards])).all():
        paid[payment.jobcard_id].append(payment)
    by_card = defaultdict(list)
    for row in Jobmovement.query.filter(Jobmovement.jobcard.in_([str(card.id) for card in cards])).all():
        by_card[row.jobcard].append(row)
    # Resolve full saved product names only; aliases are input conveniences.
    items = {normalize_name(item.name): item for item in Item_data.query.all()}
    rates = {(row.product_id, row.bundle_type): row for row in OutworkerRate.query.all()}
    quotes = []
    kept = kept_totals()
    for card in cards:
        groups = defaultdict(lambda: {"given": 0, "returned": 0})
        invalid = False
        for row in by_card[str(card.id)]:
            if (row.name_of_mater != card.given_to or row.flow_type not in ("OUT", "IN")
                    or (row.outflow or 0) < 0 or (row.inflow or 0) < 0
                    or (row.flow_type == "OUT" and (row.inflow or 0))
                    or (row.flow_type == "IN" and (row.outflow or 0))):
                invalid = True
                break
            group = groups[(row.product_name, row.type_B)]
            group["given"] += (row.outflow or 0) if row.flow_type == "OUT" else 0
            group["returned"] += (row.inflow or 0) if row.flow_type == "IN" else 0
        groups = {key: group for key, group in groups.items() if group["given"] or group["returned"]}
        if invalid or not groups or any(
            group["given"] <= 0 or group["returned"] > group["given"] for group in groups.values()
        ):
            continue
        paid_groups = defaultdict(int)
        for payment in paid[card.id]:
            if not isinstance(payment.lines, list) or not payment.lines:
                invalid = True
                break
            payment_pieces = 0
            for line in payment.lines:
                if not isinstance(line, dict):
                    invalid = True
                    break
                item = items.get(normalize_name(line.get("product", "")))
                product_id = line.get("product_id") or (item.id if item else None)
                key = (product_id or normalize_name(line.get("product", "")), line.get("type"))
                quantity = line.get("pieces")
                if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
                    invalid = True
                    break
                paid_groups[key] += quantity
                payment_pieces += quantity
            if payment_pieces != payment.pieces:
                invalid = True
                break
        current_keys = {(items[normalize_name(name)].id if normalize_name(name) in items else normalize_name(name), kind)
                        for name, kind in groups}
        if invalid or any(key not in current_keys for key in paid_groups):
            continue
        lines, errors = [], []
        for (name, type_name), group in sorted(groups.items()):
            group['kept'] = kept[(str(card.id), name, type_name)]
            item = items.get(normalize_name(name))
            paid_quantity = paid_groups[(item.id if item else normalize_name(name), type_name)]
            if group['returned'] + group['kept'] > group['given'] or paid_quantity > group["returned"] + group['kept']:
                invalid = True
                break
            quantity = group["returned"] + group['kept'] - paid_quantity
            if quantity == 0:
                continue
            override = rates.get((item.id, type_name)) if item else None
            rate = override or (rates.get((item.id, "")) if item else None)
            if not item:
                errors.append(f"{name}: product is not in Item Setup.")
            elif not rate:
                errors.append(f"Set a base or {type_name} rate for {name}.")
            paise = int((Decimal(quantity) * rate.rate_units / 100).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP)) if rate else None
            lines.append({
                "product_id": item.id if item else None, "product": name, "type": type_name,
                "pieces": quantity, "given": group["given"], "returned": group["returned"],
                "kept": group['kept'],
                "already_paid": paid_quantity,
                "rate": rate_text(rate.rate_units) if rate else None,
                "rate_source": "Type override" if override else "Base rate",
                "amount_paise": paise,
            })
        if invalid or not lines:
            continue
        gross = sum(line["amount_paise"] or 0 for line in lines)
        if gross > MAX_PAISE:
            errors.append("Job amount exceeds the supported payment limit.")
        quotes.append({"id": card.id, "date": card.date, "lines": lines,
                       "given": sum(group["given"] for group in groups.values()),
                       "returned": sum(group["returned"] for group in groups.values()),
                       "kept": sum(group.get('kept', 0) for group in groups.values()),
                       "already_paid": sum(paid_groups.values()),
                       "pending_return": sum(group["given"] - group["returned"] - group.get('kept', 0) for group in groups.values()),
                       "pieces": sum(line["pieces"] for line in lines),
                       "gross_paise": gross, "errors": errors})
    return quotes


# Compatibility for existing callers; eligibility now includes partially returned jobs.
completed_job_quotes = payable_job_quotes


def payroll_preview(worker_id, job_ids, deduction, *, advance_ids=None):
    worker = db.session.get(Outworker, worker_id) if record_id(worker_id) else None
    if not worker:
        raise ValueError("Select an existing outworker.")
    try:
        ids = sorted({record_id(value) for value in job_ids})
        if any(value is None for value in ids):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Select valid job cards.") from None
    if not ids:
        raise ValueError("Select at least one job with returned, unpaid pieces.")
    quotes = {quote["id"]: quote for quote in payable_job_quotes(worker)}
    if any(card_id not in quotes for card_id in ids):
        raise ValueError("A selected job has no returned unpaid pieces, has an invalid balance, or belongs to another outworker.")
    jobs = [quotes[card_id] for card_id in ids]
    errors = [error for job in jobs for error in job["errors"]]
    if errors:
        raise ValueError(" ".join(errors))
    gross = sum(job["gross_paise"] for job in jobs)
    if gross > MAX_PAISE:
        raise ValueError("Payroll total exceeds the supported payment limit.")
    available = advance_balance(worker_id)
    entries = [entry for entry in advance_entries(worker_id) if entry["remaining_paise"] > 0]
    selected = None
    if advance_ids is not None:
        try:
            selected = {record_id(value) for value in advance_ids}
            if None in selected or not selected.issubset({entry["id"] for entry in entries}):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("Select available advances belonging to this outworker. Refresh the account.") from None
        entries = [entry for entry in entries if entry["id"] in selected]
        deduction = min(gross, sum(entry["remaining_paise"] for entry in entries))
        deduction = money_input(deduction)
    # Selection-based recovery: never deduct more than this payroll can cover.
    deduction = min(available, gross) if deduction == "available" else parse_money(deduction)
    if deduction > available or deduction > gross:
        raise ValueError("Advance deduction cannot exceed the available advance or gross payroll.")
    recoveries = []
    to_recover = deduction
    for entry in entries:
        amount = min(to_recover, entry["remaining_paise"])
        if amount:
            recoveries.append({"advance_id": entry["id"], "amount_paise": amount})
            to_recover -= amount
    # Check quantities, rates, worker and advance balance again at final save.
    version_data = {"worker": worker_label(worker), "available": available,
                    "jobs": [{"id": job["id"], "lines": job["lines"], "given": job["given"],
                              "returned": job["returned"], "already_paid": job["already_paid"]} for job in jobs],
                    "deduction": deduction}
    if selected is not None:
        version_data["advances"] = [{"id": entry["id"], "remaining": entry["remaining_paise"]} for entry in entries]
    version = hashlib.sha256(json.dumps(version_data, sort_keys=True).encode()).hexdigest()
    return {"worker": worker, "worker_name": worker_label(worker), "jobs": jobs,
            "gross_paise": gross, "deduction_paise": deduction, "net_paise": gross - deduction,
            "available_paise": available, "remaining_advance_paise": available - deduction,
            "pieces": sum(job["pieces"] for job in jobs), "version": version,
            "advance_recoveries": recoveries}


def browser_payroll_snapshot(worker, jobs, advances, available):
    """Signed page-load quote; dates are display-only and not needed for validation."""
    return {"worker": worker_label(worker), "available": available,
            "jobs": [{key: job[key] for key in (
                "id", "given", "returned", "kept", "already_paid", "pending_return", "pieces",
                "gross_paise", "lines", "errors")} for job in jobs],
            "advances": [{"id": row["id"], "remaining_paise": row["remaining_paise"]} for row in advances]}


def issue_payroll(worker_id, job_ids, deduction, expected_version, method, reference, note, token, user, *, advance_ids=None, expected_snapshot=None):
    try:
        username = _claim(token, "outworker_payroll", user, dict(worker_id=worker_id, job_ids=job_ids,
                          deduction=deduction, version=expected_version, method=method, reference=reference,
                          note=note, advance_ids=advance_ids, snapshot=expected_snapshot))
        preview = payroll_preview(worker_id, job_ids, deduction, advance_ids=advance_ids)
        valid = preview["version"] == expected_version
        if expected_snapshot is not None:
            current = browser_payroll_snapshot(preview["worker"], preview["jobs"],
                                              advance_entries(worker_id), preview["available_paise"])
            ids = {job["id"] for job in preview["jobs"]}
            selected = {record_id(value) for value in (advance_ids or [])}
            original = {**expected_snapshot,
                        "jobs": [job for job in expected_snapshot["jobs"] if job["id"] in ids],
                        "advances": [row for row in expected_snapshot["advances"] if row["id"] in selected]}
            current["advances"] = [row for row in current["advances"] if row["id"] in selected]
            valid = current == original and parse_money(deduction) == preview["deduction_paise"]
        if not valid:
            raise ValueError("Rates, job quantities or advances changed. Calculate the payroll again before paying.")
        reference, note = _details(method, reference, note)
        payroll = OutworkerPayroll(
            worker_id=worker_id, worker_name=preview["worker_name"],
            gross_paise=preview["gross_paise"], deduction_paise=preview["deduction_paise"],
            net_paise=preview["net_paise"], paid_at=datetime.now(), method=method,
            reference=reference, note=note, recorded_by=username,
        )
        db.session.add(payroll)
        db.session.flush()
        for recovery in preview["advance_recoveries"]:
            db.session.add(OutworkerAdvanceRecovery(payroll_id=payroll.id, **recovery))
        for job in preview["jobs"]:
            db.session.add(OutworkerPayrollJob(
                payroll_id=payroll.id, jobcard_id=job["id"], pieces=job["pieces"],
                amount_paise=job["gross_paise"], lines=job["lines"],
            ))
        db.session.commit()
        return payroll
    except IntegrityError:
        db.session.rollback()
        raise ValueError("This payroll conflicts with a saved payment. Refresh the account.") from None
    except Exception:
        db.session.rollback()
        raise


def payment_account(worker_id):
    advances = OutworkerAdvance.query.filter_by(worker_id=worker_id).all()
    payrolls = OutworkerPayroll.query.filter_by(worker_id=worker_id).all()
    receipts = OutworkerAdvanceReceipt.query.filter_by(worker_id=worker_id).all()
    kept_advances = {row.advance_id for row in JobKeptProduct.query.filter_by(worker_id=worker_id).all()}
    events = [{"date": row.paid_at, "kind": "Advance", "id": row.id,
               "advance_paise": row.amount_paise, "deduction_paise": 0,
               "gross_paise": 0, "net_paise": 0 if row.id in kept_advances else row.amount_paise,
               "method": row.method, "reference": row.reference, "note": row.note,
               "product_kept": row.id in kept_advances,
               "recorded_by": row.recorded_by} for row in advances]
    events.extend({"date": row.paid_at, "kind": "Payroll", "id": row.id,
                   "advance_paise": 0, "deduction_paise": row.deduction_paise,
                   "gross_paise": row.gross_paise, "net_paise": row.net_paise,
                   "method": row.method, "reference": row.reference, "note": row.note,
                   "recorded_by": row.recorded_by} for row in payrolls)
    events.extend({"date": row.received_at, "kind": "Recovery", "id": row.id,
                   "advance_id": row.advance_id, "advance_paise": 0, "deduction_paise": 0,
                   "received_paise": row.amount_paise, "gross_paise": 0, "net_paise": row.amount_paise,
                   "method": row.method, "reference": row.reference, "note": row.note,
                   "recorded_by": row.recorded_by} for row in receipts)
    events.sort(key=lambda event: (event["date"], event["kind"], event["id"]))
    balance = 0
    for event in events:
        balance += event["advance_paise"] - event["deduction_paise"] - event.get("received_paise", 0)
        event["balance_paise"] = balance
    return {"events": events, "advance_paise": balance,
            "gross_paise": sum(row.gross_paise for row in payrolls),
            "deduction_paise": sum(row.deduction_paise for row in payrolls),
            "direct_recovery_paise": sum(row.amount_paise for row in receipts),
            "net_paise": sum(row.net_paise for row in payrolls)}
