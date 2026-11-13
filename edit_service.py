import hashlib
import json
import math
from datetime import datetime
from math import ceil
from sqlalchemy import String, cast, or_

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from modes import (
    db, Bale_date, Lump, Bundle, Jobcard, Jobmovement, Cuter, Item_data, ItemAlias, OutworkerAlias,
    Outworker, Party, EditLog, RequestDedup, OutworkerPayrollJob, ReturnBreakdown,
)
from master_aliases import validate_master_aliases
from item_aliases import normalize_name, parse_aliases, validate_names
from entry_integrity import validate_update, validate_affected_jobs
from validation import MAX_DATABASE_INTEGER, MAX_PIECES, record_id
from database_writes import begin_write


ENTITY_CONFIG = {
    "bale": {
        "model": Bale_date,
        "title": "Bale",
        "fields": {
            "part_name": "text", "lot_number": "int", "lot_count": "int",
            "bale_number": "int", "bale_date": "datetime",
            "cut_by": "text", "product": "text",
        },
    },
    "lump": {
        "model": Lump,
        "title": "Lump",
        "fields": {
            "bale_id": "int", "cut_by": "text", "bundle_type": "text",
            "product": "text", "meters": "float", "meters_add_remove": "float",
            "color": "text", "number_of_bundlie": "int",
        },
    },
    "bundle": {
        "model": Bundle,
        "title": "Bundle",
        "fields": {
            "product": "text", "color": "text", "pieces": "int", "kg": "float",
            "type_B": "text", "s_no": "int", "status": "status",
            "given_to": "optional_text", "given_by": "optional_text",
            "given_date": "optional_datetime",
        },
    },
    "jobcard": {
        "model": Jobcard,
        "title": "Job card",
        "fields": {"date": "datetime", "given_to": "text", "given_by": "text"},
    },
    "movement": {
        "model": Jobmovement,
        "title": "Job movement",
        "fields": {
            "date": "datetime", "jobcard": "optional_text", "bundle": "optional_text",
            "partculer": "text", "product_name": "text", "name_of_mater": "text",
            "type_B": "text", "flow_type": "flow", "outflow": "int", "inflow": "int",
        },
    },
    "cutter": {"model": Cuter, "title": "Cutter", "fields": {"name": "text"}},
    "product": {
        "model": Item_data, "title": "Product",
        "fields": {"name": "text", "aliases": "aliases", "meters": "float", "size": "float"},
    },
    "outworker": {
        "model": Outworker, "title": "Outworker",
        "fields": {"name": "text", "aliases": "aliases", "adders": "text", "number": "int"},
    },
    "party": {"model": Party, "title": "Party", "fields": {"name": "text"}},
}


def _json_value(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value


def snapshot(obj, fields):
    return {
        field: ("\n".join(sorted(row.alias for row in obj.alias_rows))
                if field == "aliases" else _json_value(getattr(obj, field)))
        for field in fields
    }


def version_for(values):
    raw = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse(value, kind):
    if kind == "aliases":
        return "\n".join(sorted(parse_aliases(value)))
    value = value.strip() if isinstance(value, str) else value
    if kind.startswith("optional_") and value == "":
        return None
    base_kind = kind.removeprefix("optional_")
    if base_kind == "int":
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("Enter a whole number.")
        parsed = int(value)
        if abs(parsed) > MAX_DATABASE_INTEGER:
            raise ValueError("This number is too large to save.")
        return parsed
    if base_kind == "float":
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("Enter a finite number.")
        return parsed
    if base_kind == "datetime":
        return datetime.fromisoformat(value)
    if base_kind == "status":
        normalized = value.upper()
        if normalized not in {"READY", "GIVEN"}:
            raise ValueError("Status must be READY or GIVEN")
        return normalized
    if base_kind == "flow":
        normalized = value.upper()
        if normalized not in {"IN", "OUT"}:
            raise ValueError("Flow type must be IN or OUT")
        return normalized
    if value == "":
        raise ValueError("Required fields cannot be empty")
    return value


def get_entry(entity_type, entity_id):
    config = ENTITY_CONFIG.get(entity_type)
    if not config or record_id(entity_id) is None:
        return None, None
    return config, db.session.get(config["model"], entity_id)


def edit_context(entity_type, entity_id):
    if entity_type == "movement":
        return None
    if entity_type == "jobcard":
        from jobcard_edit import jobcard_edit_context
        return jobcard_edit_context(entity_id)
    config, obj = get_entry(entity_type, entity_id)
    if not config or not obj:
        return None
    values = snapshot(obj, config["fields"])
    fields = [
        {"name": name, "kind": kind, "value": values[name]}
        for name, kind in config["fields"].items()
    ]
    return {
        "title": config["title"], "entity_type": entity_type,
        "entity_id": entity_id, "fields": fields, "version": version_for(values),
    }


def _add_log(entity_type, obj, old, new, username, action="UPDATE"):
    changed = [key for key in old if old.get(key) != new.get(key)]
    if not changed:
        return
    db.session.add(EditLog(
        entity_type=entity_type,
        entity_id=obj.id,
        action=action,
        old_values=old,
        new_values=new,
        changed_fields=changed,
        username=username,
        changed_at=datetime.now(),
    ))


def _logged_update(entity_type, obj, updates, username, action="CASCADE_UPDATE"):
    fields = list(updates)
    old = snapshot(obj, fields)
    for key, value in updates.items():
        setattr(obj, key, value)
    new = snapshot(obj, fields)
    _add_log(entity_type, obj, old, new, username, action)


def _sync_jobcard_products(old_name, new_name, username):
    for card in Jobcard.query.all():
        old_list = json.loads(json.dumps(card.product_list))
        new_list = json.loads(json.dumps(card.product_list))
        for item in new_list:
            if item.get("name_of_prduct") == old_name:
                item["name_of_prduct"] = new_name
        if old_list != new_list:
            card.product_list = new_list
            _add_log("jobcard", card, {"product_list": old_list},
                     {"product_list": new_list}, username, "CASCADE_UPDATE")


def _sync_related(entity_type, obj, changed, username, old):
    if entity_type == "bale":
        updates = {}
        if "cut_by" in changed:
            updates["cut_by"] = obj.cut_by
        if "product" in changed:
            updates["product"] = obj.product
        if updates:
            for lump in Lump.query.filter_by(bale_id=obj.id).all():
                previous = snapshot(lump, updates)
                _logged_update("lump", lump, updates, username)
                _sync_related("lump", lump, list(updates), username, previous)

    elif entity_type == "lump":
        mapping = {"product": "product", "color": "color", "bundle_type": "type_B"}
        updates = {target: getattr(obj, source) for source, target in mapping.items() if source in changed}
        if updates:
            for bundle in Bundle.query.filter_by(lump_id=obj.id).all():
                previous = snapshot(bundle, updates)
                _logged_update("bundle", bundle, updates, username)
                _sync_related("bundle", bundle, list(updates), username, previous)

    elif entity_type == "bundle":
        movement_updates = {}
        for source, target in (("product", "product_name"), ("type_B", "type_B"),
                               ("pieces", "outflow"), ("given_to", "name_of_mater")):
            if source in changed:
                movement_updates[target] = getattr(obj, source)
        movements = Jobmovement.query.filter_by(bundle=str(obj.id), flow_type="OUT").all()
        for movement in movements:
            if movement_updates:
                _logged_update("movement", movement, movement_updates, username)
            if movement.jobcard:
                card = db.session.get(Jobcard, int(movement.jobcard))
                if card:
                    old_list = json.loads(json.dumps(card.product_list))
                    new_list = json.loads(json.dumps(card.product_list))
                    for item in new_list:
                        if str(item.get("item_id")) == str(obj.id):
                            item.update({
                                "name_of_prduct": obj.product, "type": obj.type_B,
                                "qty": obj.pieces, "kg": obj.kg,
                            })
                    if old_list != new_list:
                        card.product_list = new_list
                        _add_log("jobcard", card, {"product_list": old_list},
                                 {"product_list": new_list}, username, "CASCADE_UPDATE")

    elif entity_type == "jobcard" and "given_to" in changed:
        for movement in Jobmovement.query.filter_by(jobcard=str(obj.id)).all():
            _logged_update("movement", movement, {"name_of_mater": str(obj.given_to)}, username)
            if movement.bundle:
                bundle = db.session.get(Bundle, int(movement.bundle))
                if bundle:
                    _logged_update("bundle", bundle, {"given_to": str(obj.given_to)}, username)

    elif entity_type == "movement" and obj.flow_type == "OUT" and obj.bundle:
        bundle = db.session.get(Bundle, int(obj.bundle))
        if bundle:
            mapping = {
                "product_name": "product", "type_B": "type_B",
                "outflow": "pieces", "name_of_mater": "given_to",
            }
            updates = {target: getattr(obj, source) for source, target in mapping.items() if source in changed}
            if updates:
                _logged_update("bundle", bundle, updates, username)
        if obj.jobcard:
            card = db.session.get(Jobcard, int(obj.jobcard))
            if card:
                old_list = json.loads(json.dumps(card.product_list))
                new_list = json.loads(json.dumps(card.product_list))
                for item in new_list:
                    if str(item.get("item_id")) == str(obj.bundle):
                        item.update({
                            "name_of_prduct": obj.product_name,
                            "type": obj.type_B,
                            "qty": obj.outflow,
                            **({"kg": bundle.kg} if bundle else {}),
                        })
                if old_list != new_list:
                    card.product_list = new_list
                    _add_log("jobcard", card, {"product_list": old_list},
                             {"product_list": new_list}, username, "CASCADE_UPDATE")

    elif entity_type == "cutter" and "name" in changed:
        old_name = old["name"]
        for bale in Bale_date.query.filter_by(cut_by=old_name).all():
            _logged_update("bale", bale, {"cut_by": obj.name}, username)
        for lump in Lump.query.filter_by(cut_by=old_name).all():
            _logged_update("lump", lump, {"cut_by": obj.name}, username)

    elif entity_type == "product" and "name" in changed:
        old_name = old["name"]
        for bale in Bale_date.query.filter_by(product=old_name).all():
            _logged_update("bale", bale, {"product": obj.name}, username)
        for lump in Lump.query.filter_by(product=old_name).all():
            _logged_update("lump", lump, {"product": obj.name}, username)
        for bundle in Bundle.query.filter_by(product=old_name).all():
            _logged_update("bundle", bundle, {"product": obj.name}, username)
        for movement in Jobmovement.query.filter_by(product_name=old_name).all():
            _logged_update("movement", movement, {"product_name": obj.name}, username)
        _sync_jobcard_products(old_name, obj.name, username)

    elif entity_type == "outworker" and ({"name", "adders"} & set(changed)):
        old_full = f'{obj.id}***{old["name"]}--{old["adders"]}/-'
        new_full = f"{obj.id}***{obj.name}--{obj.adders}/-"
        for card in Jobcard.query.filter_by(given_to=old_full).all():
            _logged_update("jobcard", card, {"given_to": new_full}, username)
        for movement in Jobmovement.query.filter_by(name_of_mater=old_full).all():
            _logged_update("movement", movement, {"name_of_mater": new_full}, username)
        for bundle in Bundle.query.filter_by(given_to=old_full).all():
            _logged_update("bundle", bundle, {"given_to": new_full}, username)

    elif entity_type == "party" and "name" in changed:
        for bale in Bale_date.query.filter_by(part_name=old["name"]).all():
            _logged_update("bale", bale, {"part_name": obj.name}, username)


def save_entry(entity_type, entity_id, form_data, expected_version, request_key, username):
    if entity_type == "movement":
        return "invalid", "Movement records are system-managed. Correct the job card instead."
    if entity_type == "jobcard":
        from jobcard_edit import save_jobcard_edit
        return save_jobcard_edit(entity_id, form_data, expected_version, request_key, username)
    config = ENTITY_CONFIG.get(entity_type)
    if not config:
        return "not_found", None
    if not isinstance(request_key, str) or not request_key.strip() or len(request_key) > 128:
        return "invalid", "A valid submission token is required. Reload the form."
    request_key = hashlib.sha256(f"{username}:edit:{entity_type}:{entity_id}:{request_key}".encode()).hexdigest()

    begin_write(RequestDedup)
    digest = hashlib.sha256(json.dumps({'data': {k: v for k, v in dict(form_data).items()
                                               if k not in {'version', 'csrf_token', 'submission_token'}}},
                                      sort_keys=True, default=str).encode()).hexdigest()
    previous = RequestDedup.query.filter_by(request_key=request_key).first()
    if previous:
        matches = previous.payload_hash == digest
        db.session.rollback()
        return ('duplicate', None) if matches else ('conflict', 'This request was already used for different data.')
    try:
        db.session.add(RequestDedup(
            request_key=request_key, endpoint=f"edit:{entity_type}:{entity_id}",
            username=username, created_at=datetime.now(),
            payload_hash=digest,
        ))
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return "duplicate", None

    # The unique insert above obtains SQLite's write lock. Load the row only
    # after that point so the optimistic version check sees the newest commit.
    db.session.expire_all()
    obj = db.session.get(config["model"], entity_id)
    if not obj:
        db.session.rollback()
        return "not_found", None
    fields = config["fields"]
    old = snapshot(obj, fields)
    if version_for(old) != expected_version:
        db.session.rollback()
        return "conflict", None

    try:
        updates = {name: _parse(form_data.get(name, ""), kind) for name, kind in fields.items()}
        if entity_type in {"cutter", "product", "outworker", "party"} and "name" in updates:
            updates["name"] = normalize_name(updates["name"])
        non_negative = {"meters", "size", "pieces", "kg", "outflow", "inflow"}
        positive = {"lot_number", "lot_count", "bale_number", "number_of_bundlie", "bale_id", "number", "s_no"}
        if any(updates.get(field, 0) < 0 for field in non_negative & updates.keys()):
            raise ValueError("Quantity, weight, size, and meter values cannot be negative")
        if any(updates.get(field, 0) > MAX_PIECES for field in {'pieces', 'outflow', 'inflow'} & updates.keys()):
            raise ValueError('Piece quantities cannot exceed 1,000,000,000.')
        if any(updates.get(field, 0) <= 0 for field in positive & updates.keys()):
            raise ValueError("Count and reference values must be greater than zero")
        if entity_type == "lump" and not db.session.get(Bale_date, updates["bale_id"]):
            raise ValueError("Bale ID does not exist")
        if entity_type == "movement" and updates["flow_type"] != old["flow_type"]:
            raise ValueError("Movement direction is immutable; add a correcting movement instead")
        if entity_type in {"product", "outworker"}:
            aliases = parse_aliases(updates["aliases"])
            if entity_type == "product":
                validate_names(updates["name"], aliases, obj.id)
            else:
                validate_master_aliases(updates["name"], aliases, obj.id)
        validate_update(entity_type, obj, updates, old)
        for field, value in updates.items():
            if field == "aliases":
                continue
            setattr(obj, field, value)
        if entity_type in {"product", "outworker"}:
            alias_model = ItemAlias if entity_type == "product" else OutworkerAlias
            key = "item_id" if entity_type == "product" else "worker_id"
            requested = set(aliases)
            existing = {row.alias: row for row in obj.alias_rows}
            for alias, row in existing.items():
                if alias not in requested:
                    db.session.delete(row)
            db.session.flush()
            for alias in aliases:
                if alias not in existing:
                    db.session.add(alias_model(**{key: obj.id, "alias": alias}))
            db.session.flush()
            db.session.expire(obj, ["alias_rows"])
        new = snapshot(obj, fields)
        changed = [key for key in old if old[key] != new[key]]
        if changed and entity_type in {"jobcard", "movement", "bundle"}:
            paid_ids = db.session.query(OutworkerPayrollJob.jobcard_id)
            if entity_type == "jobcard":
                paid = OutworkerPayrollJob.query.filter_by(jobcard_id=obj.id).first()
            elif entity_type == "movement":
                references = {str(old.get("jobcard") or ""), str(obj.jobcard or "")}
                paid = any(str(row[0]) in references for row in paid_ids.all())
            else:
                references = {row.jobcard for row in Jobmovement.query.filter_by(bundle=str(obj.id)).all()}
                paid = any(str(row[0]) in references for row in paid_ids.all())
            if paid:
                raise ValueError("This entry belongs to an issued payroll. Its paid job data cannot be edited.")
        _add_log(entity_type, obj, old, new, username)
        _sync_related(entity_type, obj, changed, username, old)
        validate_affected_jobs(entity_type, obj, old)
        db.session.commit()
        return "saved", changed
    except IntegrityError:
        db.session.rollback()
        return "invalid", "That value conflicts with an existing entry"
    except (ValueError, TypeError) as exc:
        db.session.rollback()
        return "invalid", str(exc)
    except Exception:
        db.session.rollback()
        raise


def audit_logs(entity_type=None, entity_id=None, limit=500):
    query = EditLog.query
    if entity_type:
        query = query.filter_by(entity_type=entity_type)
    if entity_id is not None:
        query = query.filter_by(entity_id=entity_id)
    return query.order_by(EditLog.changed_at.desc(), EditLog.id.desc()).limit(limit).all()

SEARCH_FIELDS = {
    "bale": ("part_name", "lot_number", "lot_count", "bale_number", "cut_by", "product", "bale_date"),
    "lump": ("bale_id", "cut_by", "bundle_type", "product", "color", "meters"),
    "bundle": ("product", "color", "pieces", "kg", "type_B", "s_no", "status", "given_to"),
    "jobcard": ("given_to", "given_by", "date", "product_list"),
    "movement": ("jobcard", "bundle", "partculer", "product_name", "name_of_mater", "type_B", "flow_type", "date", "outflow", "inflow"),
    "cutter": ("name",),
    "product": ("name",),
    "outworker": ("name", "adders", "number"),
    "party": ("name",),
}


def _entry_preview(entity_type, row):
    if entity_type == "bale":
        return f"{row.part_name} · {row.product}", f"Lot {row.lot_number}/{row.lot_count} · Bale {row.bale_number} · {row.bale_date:%d-%m-%Y}"
    if entity_type == "lump":
        return row.product, f"Bale #{row.bale_id} · {row.bundle_type} · Cut by {row.cut_by}"
    if entity_type == "bundle":
        return row.product, f"{row.type_B} · {row.pieces} pieces · {row.status} · {row.color or ''}"
    if entity_type == "jobcard":
        return row.given_to, f"{row.date:%d-%m-%Y} · Given by {row.given_by} · {len(row.product_list or [])} lines"
    if entity_type == "movement":
        qty = row.outflow if row.flow_type == "OUT" else row.inflow
        return row.product_name, f"{row.flow_type} {qty} · {row.name_of_mater} · Job #{row.jobcard or '-'}"
    if entity_type == "product":
        aliases = ", ".join(sorted(alias.alias for alias in row.alias_rows))
        return row.name, f"Aliases: {aliases}" if aliases else "No aliases"
    if entity_type == "outworker":
        aliases = ", ".join(sorted(alias.alias for alias in row.alias_rows))
        details = f"{row.adders} · {row.number}"
        return row.name, f"{details} · Aliases: {aliases}" if aliases else details
    return row.name, ""


def search_entries(entity_type, search="", page=1, page_size=40):
    """Search every editable type and return one bounded page of results."""
    config = ENTITY_CONFIG.get(entity_type)
    if not config or entity_type == "movement":
        return None
    try:
        page_size = max(1, min(int(page_size), 100))
    except (TypeError, ValueError, OverflowError):
        page_size = 40
    try:
        page = max(1, int(page or 1))
    except (TypeError, ValueError, OverflowError):
        page = 1
    model = config["model"]
    query = model.query
    search = (search or "").strip()[:100]
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        clauses = [cast(model.id, String).ilike(pattern, escape="\\")]
        clauses.extend(
            cast(getattr(model, field), String).ilike(pattern, escape="\\")
            for field in SEARCH_FIELDS[entity_type]
        )
        if entity_type == "product":
            clauses.append(Item_data.alias_rows.any(ItemAlias.alias.ilike(pattern, escape="\\")))
        if entity_type == "outworker":
            clauses.append(Outworker.alias_rows.any(OutworkerAlias.alias.ilike(pattern, escape="\\")))
        query = query.filter(or_(*clauses))
    total = query.count()
    page = max(1, min(int(page or 1), max(1, ceil(total / page_size))))
    if entity_type in {"product", "outworker"}:
        query = query.options(selectinload(model.alias_rows))
    rows = query.order_by(model.id.desc()).limit(page_size).offset((page - 1) * page_size).all()
    items = []
    for row in rows:
        title, details = _entry_preview(entity_type, row)
        items.append({"id": row.id, "title": title, "details": details})
    return {"items": items, "total": total, "page": page, "pages": max(1, ceil(total / page_size))}

