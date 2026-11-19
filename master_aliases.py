"""Alternate names for Outworkers, always resolved to their ID-based value."""

from collections import Counter

from sqlalchemy import func

from item_aliases import normalize_name, parse_aliases
from modes import Outworker, OutworkerAlias
from validation import identity_text


def master_full_name(worker):
    return f"{worker.id}***{worker.name}--{worker.adders}/-"


def validate_worker_contact(name, address, number, worker_id=None):
    if any(row.id != worker_id and normalize_name(row.name) == normalize_name(name)
           and normalize_name(row.adders) == normalize_name(address) and row.mobile == number
           for row in Outworker.query):
        raise ValueError("This outworker with the same address and contact number already exists.")


def validate_master_aliases(name, aliases, worker_id=None):
    name = identity_text(normalize_name(name), "Outworker name")
    if not name or len(name) > 50:
        raise ValueError("Master name must be between 1 and 50 characters")
    if name in aliases:
        raise ValueError("An alias cannot be the same as the master name")
    if any(alias.isdigit() or "***" in alias for alias in aliases):
        raise ValueError("Master IDs and full ID-based names cannot be used as aliases")
    other_aliases = OutworkerAlias.query.filter(
        OutworkerAlias.alias.in_([name, *aliases])
    ).all()
    if any(alias.worker_id != worker_id for alias in other_aliases):
        raise ValueError("Master name or alias is already used by another master")
    other_names = Outworker.query.filter(
        func.upper(Outworker.name).in_(aliases)
    ).all()
    if any(worker.id != worker_id for worker in other_names):
        raise ValueError("An alias is already used as another master's name")


def master_name_mapping():
    workers = Outworker.query.order_by(Outworker.id).all()
    counts = Counter(normalize_name(worker.name) for worker in workers)
    mapping = {}
    for worker in workers:
        full = master_full_name(worker)
        mapping[normalize_name(full)] = full
        name = normalize_name(worker.name)
        if counts[name] == 1:
            mapping[name] = full
    for alias in OutworkerAlias.query.order_by(OutworkerAlias.id).all():
        mapping[alias.alias] = master_full_name(alias.worker)
    for worker in workers:
        mapping[str(worker.id)] = master_full_name(worker)
    return mapping


def resolve_master_name(value):
    return master_name_mapping().get(normalize_name(value))


def master_name_options():
    workers = Outworker.query.order_by(Outworker.name, Outworker.id).all()
    counts = Counter(normalize_name(worker.name) for worker in workers)
    options = []
    for worker in workers:
        full = master_full_name(worker)
        label = f"#{worker.id} {worker.name} — {worker.adders}"
        options.append({"value": full, "label": label})
        options.append({"value": str(worker.id), "label": label})
        if counts[normalize_name(worker.name)] == 1:
            options.append({"value": worker.name, "label": label})
        options.extend(
            {"value": alias.alias, "label": label}
            for alias in worker.alias_rows
        )
    return options
