"""Item aliases are alternate input names, never separate stock identities."""

import re

from sqlalchemy import func

from modes import Item_data, ItemAlias


def normalize_name(value):
    return " ".join(str(value or "").strip().upper().split())


def parse_aliases(value):
    aliases = []
    for part in re.split(r"[,\n]", value or ""):
        alias = normalize_name(part)
        if not alias or alias in aliases:
            continue
        if len(alias) > 50:
            raise ValueError("Each alias must be 50 characters or fewer")
        aliases.append(alias)
    if len(aliases) > 30:
        raise ValueError("An item can have at most 30 aliases")
    return aliases


def validate_names(name, aliases, item_id=None):
    name = normalize_name(name)
    if not name or len(name) > 50:
        raise ValueError("Item name must be between 1 and 50 characters")
    if name in aliases:
        raise ValueError("An alias cannot be the same as the item name")
    names = [name, *aliases]
    existing_items = Item_data.query.filter(
        func.upper(Item_data.name).in_(names)
    ).all()
    if any(item.id != item_id for item in existing_items):
        raise ValueError("Item name or alias is already used by another item")
    existing_aliases = ItemAlias.query.filter(ItemAlias.alias.in_(names)).all()
    if any(alias.item_id != item_id for alias in existing_aliases):
        raise ValueError("Item name or alias is already used by another item")


def resolve_item_name(value):
    name = normalize_name(value)
    item = Item_data.query.filter(func.upper(Item_data.name) == name).first()
    if item:
        return item.name
    alias = ItemAlias.query.filter_by(alias=name).first()
    return alias.item.name if alias else None


def item_name_suggestions():
    names = [item.name for item in Item_data.query.order_by(Item_data.name).all()]
    names.extend(alias.alias for alias in ItemAlias.query.order_by(ItemAlias.alias).all())
    return names

def item_name_mapping():
    """Map each full name and alias to the stored full item name."""
    items = Item_data.query.order_by(Item_data.name).all()
    mapping = {normalize_name(item.name): item.name for item in items}
    for alias in ItemAlias.query.order_by(ItemAlias.alias).all():
        mapping[alias.alias] = alias.item.name
    return mapping
