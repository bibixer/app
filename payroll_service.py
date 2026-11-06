"""Product rates, advance balances, and immutable completed-job payment records."""

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError

from bundle_types import BUNDLE_TYPE_VALUES
from data_entry import claim_write
from item_aliases import normalize_name
from modes import (db, Item_data, Outworker, Jobcard, Jobmovement, EditLog,
                   OutworkerRate, OutworkerAdvance, OutworkerPayroll, OutworkerPayrollJob)

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


def _claim(token, endpoint, user):
    username = user.username
    if not claim_write(token, endpoint, user):
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


def save_rate(product_id, bundle_type, value, expected_version, token, user, remove=False):
    try:
        username = _claim(token, "outworker_rate", user)
        if not db.session.get(Item_data, product_id):
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
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def advance_balance(worker_id):
    advances = db.session.query(db.func.coalesce(db.func.sum(OutworkerAdvance.amount_paise), 0)).filter(
        OutworkerAdvance.worker_id == worker_id).scalar()
    deductions = db.session.query(db.func.coalesce(db.func.sum(OutworkerPayroll.deduction_paise), 0)).filter(
        OutworkerPayroll.worker_id == worker_id).scalar()
    return int(advances) - int(deductions)


def record_advance(worker_id, amount, method, reference, note, token, user):
    try:
        username = _claim(token, "outworker_advance", user)
        worker = db.session.get(Outworker, worker_id)
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


def completed_job_quotes(worker):
    """Require every product/type to balance, rather than only the job total."""
    cards = Jobcard.query.filter_by(given_to=worker_label(worker)).order_by(Jobcard.id).all()
    if not cards:
        return []
    paid = {row.jobcard_id: row.payroll_id for row in OutworkerPayrollJob.query.filter(
        OutworkerPayrollJob.jobcard_id.in_([card.id for card in cards])).all()}
    by_card = defaultdict(list)
    for row in Jobmovement.query.filter(Jobmovement.jobcard.in_([str(card.id) for card in cards])).all():
        by_card[row.jobcard].append(row)
    # Resolve full saved product names only; aliases are input conveniences.
    items = {normalize_name(item.name): item for item in Item_data.query.all()}
    rates = {(row.product_id, row.bundle_type): row for row in OutworkerRate.query.all()}
    quotes = []
    for card in cards:
        if card.id in paid:
            continue
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
        if invalid or not groups or any(
            group["given"] <= 0 or group["given"] != group["returned"] for group in groups.values()
        ):
            continue
        lines, errors = [], []
        for (name, type_name), group in sorted(groups.items()):
            item = items.get(normalize_name(name))
            override = rates.get((item.id, type_name)) if item else None
            rate = override or (rates.get((item.id, "")) if item else None)
            if not item:
                errors.append(f"{name}: product is not in Item Setup.")
            elif not rate:
                errors.append(f"Set a base or {type_name} rate for {name}.")
            quantity = group["given"]
            paise = int((Decimal(quantity) * rate.rate_units / 100).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP)) if rate else None
            lines.append({
                "product_id": item.id if item else None, "product": name, "type": type_name,
                "pieces": quantity, "rate": rate_text(rate.rate_units) if rate else None,
                "rate_source": "Type override" if override else "Base rate",
                "amount_paise": paise,
            })
        gross = sum(line["amount_paise"] or 0 for line in lines)
        if gross > MAX_PAISE:
            errors.append("Job amount exceeds the supported payment limit.")
        quotes.append({"id": card.id, "date": card.date, "lines": lines,
                       "pieces": sum(line["pieces"] for line in lines),
                       "gross_paise": gross, "errors": errors})
    return quotes


def payroll_preview(worker_id, job_ids, deduction):
    worker = db.session.get(Outworker, worker_id)
    if not worker:
        raise ValueError("Select an existing outworker.")
    try:
        ids = sorted({int(value) for value in job_ids})
    except (TypeError, ValueError):
        raise ValueError("Select valid job cards.") from None
    if not ids:
        raise ValueError("Select at least one completed job.")
    quotes = {quote["id"]: quote for quote in completed_job_quotes(worker)}
    if any(card_id not in quotes for card_id in ids):
        raise ValueError("A selected job is incomplete, already paid, or belongs to another outworker.")
    jobs = [quotes[card_id] for card_id in ids]
    errors = [error for job in jobs for error in job["errors"]]
    if errors:
        raise ValueError(" ".join(errors))
    gross = sum(job["gross_paise"] for job in jobs)
    if gross > MAX_PAISE:
        raise ValueError("Payroll total exceeds the supported payment limit.")
    available = advance_balance(worker_id)
    deduction = parse_money(deduction)
    if deduction > available or deduction > gross:
        raise ValueError("Advance deduction cannot exceed the available advance or gross payroll.")
    # Check quantities, rates, worker and advance balance again at final save.
    version_data = {"worker": worker_label(worker), "available": available,
                    "jobs": [{"id": job["id"], "lines": job["lines"]} for job in jobs],
                    "deduction": deduction}
    version = hashlib.sha256(json.dumps(version_data, sort_keys=True).encode()).hexdigest()
    return {"worker": worker, "worker_name": worker_label(worker), "jobs": jobs,
            "gross_paise": gross, "deduction_paise": deduction, "net_paise": gross - deduction,
            "available_paise": available, "remaining_advance_paise": available - deduction,
            "pieces": sum(job["pieces"] for job in jobs), "version": version}


def issue_payroll(worker_id, job_ids, deduction, expected_version, method, reference, note, token, user):
    try:
        username = _claim(token, "outworker_payroll", user)
        preview = payroll_preview(worker_id, job_ids, deduction)
        if preview["version"] != expected_version:
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
        for job in preview["jobs"]:
            db.session.add(OutworkerPayrollJob(
                payroll_id=payroll.id, jobcard_id=job["id"], pieces=job["pieces"],
                amount_paise=job["gross_paise"], lines=job["lines"],
            ))
        db.session.commit()
        return payroll
    except IntegrityError:
        db.session.rollback()
        raise ValueError("A selected job has already been paid. Refresh the account.") from None
    except Exception:
        db.session.rollback()
        raise


def payment_account(worker_id):
    advances = OutworkerAdvance.query.filter_by(worker_id=worker_id).all()
    payrolls = OutworkerPayroll.query.filter_by(worker_id=worker_id).all()
    events = [{"date": row.paid_at, "kind": "Advance", "id": row.id,
               "advance_paise": row.amount_paise, "deduction_paise": 0,
               "gross_paise": 0, "net_paise": row.amount_paise,
               "method": row.method, "reference": row.reference, "note": row.note,
               "recorded_by": row.recorded_by} for row in advances]
    events.extend({"date": row.paid_at, "kind": "Payroll", "id": row.id,
                   "advance_paise": 0, "deduction_paise": row.deduction_paise,
                   "gross_paise": row.gross_paise, "net_paise": row.net_paise,
                   "method": row.method, "reference": row.reference, "note": row.note,
                   "recorded_by": row.recorded_by} for row in payrolls)
    events.sort(key=lambda event: (event["date"], event["kind"], event["id"]))
    balance = 0
    for event in events:
        balance += event["advance_paise"] - event["deduction_paise"]
        event["balance_paise"] = balance
    return {"events": events, "advance_paise": balance,
            "gross_paise": sum(row.gross_paise for row in payrolls),
            "deduction_paise": sum(row.deduction_paise for row in payrolls),
            "net_paise": sum(row.net_paise for row in payrolls)}
