"""Admin corrections start at a job card; movements are maintained automatically."""

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from bundle_types import BUNDLE_TYPE_CHOICES, BUNDLE_TYPE_VALUES
from item_aliases import item_name_mapping, normalize_name
from master_aliases import resolve_master_name
from modes import (db, User, Jobcard, Jobmovement, Bundle, ReturnBreakdown,
                   EditLog, RequestDedup, OutworkerPayrollJob)
from validation import MAX_DATABASE_INTEGER, record_id


def _snapshot(row):
    return {column.name: (getattr(row, column.name).isoformat() if isinstance(getattr(row, column.name), datetime)
                          else getattr(row, column.name)) for column in row.__table__.columns}


def _state(card):
    movements = Jobmovement.query.filter_by(jobcard=str(card.id)).order_by(Jobmovement.id).all()
    bundles = {row.bundle: db.session.get(Bundle, int(row.bundle)) for row in movements
               if row.flow_type == "OUT" and row.bundle and row.bundle.isascii() and row.bundle.isdecimal()}
    breakdowns = {row.movement_id: row for row in ReturnBreakdown.query.filter(
        ReturnBreakdown.movement_id.in_([row.id for row in movements])).all()}
    state = {"card": _snapshot(card), "movements": [_snapshot(row) for row in movements],
             "bundles": [_snapshot(row) for row in bundles.values() if row],
             "breakdowns": [_snapshot(row) for row in breakdowns.values()],
             "paid": bool(OutworkerPayrollJob.query.filter_by(jobcard_id=card.id).first())}
    return movements, bundles, breakdowns, state


def _version(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _source(card, movement):
    sources = card.product_list if isinstance(card.product_list, list) else []
    for item in sources:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("item_id", ""))
        if source_id and (source_id == movement.bundle or movement.partculer.endswith(source_id)):
            return dict(item)
    return {"item_id": movement.bundle or f"MANUAL-{card.id}-{movement.id}",
            "pieces_per_bundle": movement.outflow, "bundle_count": 1,
            "source": "SCANNED" if movement.bundle else "MANUAL"}


def jobcard_edit_context(card_id):
    card = db.session.get(Jobcard, card_id) if record_id(card_id) else None
    if card is None:
        return None
    movements, bundles, _, state = _state(card)
    given, returns = [], []
    for row in movements:
        details = {"id": row.id, "product": row.product_name, "type": row.type_B,
                   "quantity": row.outflow if row.flow_type == "OUT" else row.inflow,
                   "date": row.date.isoformat(timespec="seconds"), "entered_by": row.enter_user}
        if row.flow_type == "OUT":
            source = _source(card, row)
            bundle = bundles.get(row.bundle)
            details.update(pieces=source.get("pieces_per_bundle", row.outflow),
                           count=source.get("bundle_count", 1), bundle=row.bundle,
                           kg=bundle.kg if bundle else 0, color=bundle.color if bundle else "")
            given.append(details)
        elif row.flow_type == "IN":
            returns.append(details)
    return {"title": "Job card", "entity_type": "jobcard", "entity_id": card.id,
            "fields": [{"name": name, "kind": kind,
                        "value": card.date.isoformat(timespec="seconds") if name == "date" else state["card"][name]}
                       for name, kind in (("date", "datetime"), ("given_to", "text"), ("given_by", "text"))],
            "version": _version(state), "given": given, "returns": returns, "paid": state["paid"],
            "products": sorted(set(item_name_mapping().values())), "types": BUNDLE_TYPE_CHOICES}


def _quantity(value, allow_zero=False):
    text = str(value)
    if not text.isascii() or not text.isdecimal() or len(text) > 19:
        raise ValueError("Piece counts must be whole numbers.")
    number = int(text)
    if number > MAX_DATABASE_INTEGER or number < (0 if allow_zero else 1):
        raise ValueError("Enter a valid piece count.")
    return number


def _date(value, current=None):
    if current is not None and str(value) == current.isoformat(timespec="seconds"):
        return current
    try:
        result = datetime.fromisoformat(str(value))
        if result.tzinfo is not None:
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise ValueError("Enter a valid local date and time.") from None


def _audit(entity, row, old, username):
    new = _snapshot(row)
    changed = [name for name in old if old[name] != new[name]]
    if changed:
        db.session.add(EditLog(entity_type=entity, entity_id=row.id, action="JOB_CARD_EDIT",
                               old_values=old, new_values=new, changed_fields=changed,
                               username=username, changed_at=datetime.now()))


def save_jobcard_edit(card_id, data, expected_version, token, username):
    if record_id(card_id) is None:
        return "not_found", None
    if not isinstance(token, str) or not token.strip() or len(token) > 128:
        return "invalid", "Reload the form to obtain a valid submission token."
    user = User.query.filter_by(username=username).first()
    if user is None or user.role != 1:
        return "invalid", "Only an administrator can correct a job card."
    try:
        key = hashlib.sha256(f"{username}:jobcard-edit:{card_id}:{token}".encode()).hexdigest()
        db.session.add(RequestDedup(request_key=key, endpoint="jobcard_edit", username=username, created_at=datetime.now()))
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return "duplicate", None
    try:
        db.session.expire_all()
        card = db.session.get(Jobcard, card_id)
        if card is None:
            db.session.rollback()
            return "not_found", None
        movements, bundles, breakdowns, before = _state(card)
        if _version(before) != expected_version:
            db.session.rollback()
            return "conflict", None
        if before["paid"]:
            raise ValueError("This job belongs to an issued payroll. Its paid data is locked.")
        worker = resolve_master_name(data.get("given_to"))
        giver = str(data.get("given_by") or "").strip()
        if not worker or not giver or len(giver) > 50:
            raise ValueError("Choose an existing outworker and enter who gave the job.")
        card.date, card.given_to, card.given_by = _date(data.get("date"), card.date), worker, giver
        edit_lines = data.get("edit_lines") == "1"
        reason = data.get("edit_reason", "")
        if edit_lines and (not isinstance(reason, str) or not reason.strip() or len(reason) > 500):
            raise ValueError("Enter a correction reason of at most 500 characters.")
        products = item_name_mapping()
        sources, balances = [], defaultdict(int)
        for row in movements:
            old = _snapshot(row)
            row.name_of_mater = worker
            source = _source(card, row) if row.flow_type == "OUT" else None
            if edit_lines:
                prefix = f"line_{row.id}_"
                product = products.get(normalize_name(data.get(prefix + "product")))
                type_name = data.get(prefix + "type")
                if not product or type_name not in BUNDLE_TYPE_VALUES:
                    raise ValueError("Choose an existing product and a listed bundle type for every row.")
                row.product_name, row.type_B = product, type_name
                row.date = _date(data.get(prefix + "date"), row.date)
                if row.flow_type == "OUT":
                    pieces = _quantity(data.get(prefix + "pieces"))
                    count = _quantity(data.get(prefix + "count"))
                    if count > 500 or (row.bundle and count != 1) or pieces * count > MAX_DATABASE_INTEGER:
                        raise ValueError("Check the bundle count and total pieces.")
                    row.outflow = pieces * count
                    source.update(name_of_prduct=product, type=type_name, qty=row.outflow,
                                  pieces_per_bundle=pieces, bundle_count=count)
                    sources.append(source)
                elif row.flow_type == "IN":
                    row.inflow = _quantity(data.get(prefix + "quantity"), allow_zero=True)
                else:
                    raise ValueError("This job contains an unsupported movement type.")
            if row.flow_type == "OUT" and row.bundle:
                bundle = bundles.get(row.bundle)
                if bundle is None:
                    raise ValueError("An original bundle is missing. Correct its stock record first.")
                previous = _snapshot(bundle)
                bundle.product, bundle.type_B, bundle.pieces = row.product_name, row.type_B, row.outflow
                bundle.given_to, bundle.given_by, bundle.given_date = worker, giver, row.date
                bundle.status = "GIVEN"
                if edit_lines:
                    try:
                        weight = float(data.get(f"line_{row.id}_kg"))
                    except (ValueError, TypeError):
                        raise ValueError("Enter a valid bundle weight.") from None
                    if not math.isfinite(weight) or weight < 0:
                        raise ValueError("Bundle weight must be a finite non-negative number.")
                    bundle.kg = weight
                    bundle.color = str(data.get(f"line_{row.id}_color") or "").strip()
                    if len(bundle.color) > 50:
                        raise ValueError("Bundle colour must be at most 50 characters.")
                    source.update(kg=bundle.kg, colour=bundle.color)
                _audit("bundle", bundle, previous, username)
            breakdown = breakdowns.get(row.id)
            if breakdown and any(old[name] != getattr(row, name) for name in ("inflow", "product_name", "type_B")):
                previous = _snapshot(breakdown)
                breakdown.entry_method, breakdown.calculation_rows = "direct", []
                _audit("return_breakdown", breakdown, previous, username)
            balances[(row.product_name, row.type_B)] += (row.outflow or 0) if row.flow_type == "OUT" else -(row.inflow or 0)
            _audit("movement", row, old, username)
        if any(value < 0 for value in balances.values()):
            raise ValueError("Returned pieces cannot exceed given pieces for any product and type.")
        running = defaultdict(int)
        for row in sorted(movements, key=lambda movement: (movement.date, movement.id)):
            key = (row.product_name, row.type_B)
            running[key] += (row.outflow or 0) if row.flow_type == "OUT" else -(row.inflow or 0)
            if running[key] < 0:
                raise ValueError("A return date cannot precede the pieces given for that product and type.")
        if any(row.flow_type == "OUT" and row.date < card.date for row in movements):
            raise ValueError("The job card date cannot be later than its given entries.")
        if edit_lines:
            card.product_list = sources
        _, _, _, after = _state(card)
        changed = [name for name in before["card"] if before["card"][name] != after["card"][name]]
        if before["movements"] != after["movements"]:
            changed.append("given_and_returns")
        if changed:
            db.session.add(EditLog(entity_type="jobcard", entity_id=card.id, action="UPDATE",
                                   old_values=before, new_values={**after, "reason": str(data.get("edit_reason") or "")[:500]},
                                   changed_fields=changed, username=username, changed_at=datetime.now()))
        db.session.commit()
        return "saved", changed
    except (ValueError, TypeError, OverflowError) as error:
        db.session.rollback()
        return "invalid", str(error)
    except Exception:
        db.session.rollback()
        raise
