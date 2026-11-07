"""V2 manual-only workflow boundaries, job dashboard and administrator accounts."""

import hashlib
from datetime import date, datetime, time, timedelta
import math

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from form import WriteForm
from modes import db, User, UserAccessLog, Jobcard, Jobmovement, Item_data, Outworker
from validation import record_id
from item_aliases import normalize_name

CORE_ENTITIES = frozenset({'jobcard', 'product', 'outworker'})
DISABLED_ENDPOINTS = frozenset({
    'bale_entery', 'lump_home', 'bundle_entery', 'add_cuter', 'add_suppy',
    'cutter_report', 'product_report', 'find_edit', 'submit_jobcard',
})


def job_overview():
    """Lifetime product totals, with pending balances calculated per job and type."""
    grouped = db.session.query(
        Jobmovement.jobcard, Jobmovement.product_name, Jobmovement.type_B,
        func.coalesce(func.sum(Jobmovement.outflow), 0),
        func.coalesce(func.sum(Jobmovement.inflow), 0),
    ).group_by(
        Jobmovement.jobcard, Jobmovement.product_name, Jobmovement.type_B,
    ).all()
    configured_products = Item_data.query.order_by(Item_data.name).all()
    product_totals = {
        normalize_name(product.name): {'name': product.name, 'given': 0, 'returned': 0, 'pending': 0}
        for product in configured_products
    }
    card_ids = {row[0] for row in db.session.query(Jobcard.id).all()}
    totals = {}
    unlinked = {'given': 0, 'returned': 0}
    for card_id, product, kind, given, returned in grouped:
        product_total = product_totals.setdefault(
            normalize_name(product), {'name': product or 'Unnamed product', 'given': 0, 'returned': 0, 'pending': 0},
        )
        product_total['given'] += given
        product_total['returned'] += returned
        parsed = record_id(str(card_id))
        if parsed not in card_ids:
            unlinked['given'] += given
            unlinked['returned'] += returned
            continue
        pending = max(0, given - returned)
        product_total['pending'] += pending
        total = totals.setdefault(parsed, {'given': 0, 'returned': 0, 'pending': 0})
        total['given'] += given
        total['returned'] += returned
        total['pending'] += pending
    recent = Jobcard.query.order_by(Jobcard.date.desc(), Jobcard.id.desc()).limit(20).all()
    return {
        'jobs': len(card_ids),
        'given': sum(row['given'] for row in product_totals.values()),
        'returned': sum(row['returned'] for row in product_totals.values()),
        'open_jobs': sum(row['pending'] > 0 for row in totals.values()),
        'pending': sum(row['pending'] for row in totals.values()),
        'products': len(configured_products), 'workers': Outworker.query.count(),
        'product_totals': sorted(product_totals.values(), key=lambda row: normalize_name(row['name'])),
        'unlinked': unlinked,
        'recent': [(card, totals.get(card.id, {'given': 0, 'returned': 0, 'pending': 0})) for card in recent],
    }


def _product_pie(products, field):
    palette = ('#8571ed', '#2fae9b', '#e7a454', '#5997dd', '#d579a1', '#8cae59', '#ad80ce', '#53b6cb')
    total = sum(max(0, product[field]) for product in products)
    slices, angle = [], -math.pi / 2
    for index, product in enumerate(products):
        quantity = product[field]
        if quantity <= 0:
            continue
        span = quantity / total * math.tau
        end = angle + span
        path = (f'M 0 0 L {math.cos(angle)*90:.6f} {math.sin(angle)*90:.6f} '
                f'A 90 90 0 {int(span > math.pi)} 1 {math.cos(end)*90:.6f} {math.sin(end)*90:.6f} Z')
        slices.append({'name': product['name'], 'quantity': quantity, 'percent': round(quantity / total * 100, 1),
                       'color': palette[index] if index < len(palette) else f'hsl({index*137.5%360:.1f} 55% 52%)',
                       'path': path, 'full': quantity == total})
        angle = end
    return {'total': total, 'slices': slices}


def weekly_job_overview(day=None, *, date_from=None, date_to=None):
    """Period account (Wednesday–Tuesday by default), with balances at the To date."""
    custom = date_from is not None or date_to is not None
    if custom and (not isinstance(date_from, date) or not isinstance(date_to, date) or date_from > date_to):
        raise ValueError('Enter valid From and To dates, with From on or before To.')
    if day is None and not custom:
        from data_Process import get_current_week_range
        day = get_current_week_range()['from_date'].date()
    if not custom and not isinstance(day, date):
        raise ValueError('Choose a valid date within the week.')
    first = date_from if custom else day - timedelta(days=(day.weekday() - 2) % 7)
    last = date_to if custom else first + timedelta(days=6)
    # Leave room for navigation to the adjacent weeks and the exclusive end.
    if first < date(1900, 1, 10) or last > date(9999, 12, 15):
        raise ValueError('Choose a week between 1900 and 9999.')
    start = datetime.combine(first, time.min)
    end = datetime.combine(last + timedelta(days=1), time.min)
    products = {normalize_name(item.name): {'name': item.name, 'opening': 0, 'given': 0, 'returned': 0, 'closing': 0}
                for item in Item_data.query.order_by(Item_data.name).all()}
    from sqlalchemy import case
    rows = db.session.query(
        Jobmovement.product_name,
        func.coalesce(func.sum(case((Jobmovement.date < start,
                                     func.coalesce(Jobmovement.outflow, 0) - func.coalesce(Jobmovement.inflow, 0)), else_=0)), 0),
        func.coalesce(func.sum(case((Jobmovement.date >= start, Jobmovement.outflow), else_=0)), 0),
        func.coalesce(func.sum(case((Jobmovement.date >= start, Jobmovement.inflow), else_=0)), 0),
    ).filter(Jobmovement.date < end).group_by(Jobmovement.product_name).all()
    for name, opening, given, returned in rows:
        product = products.setdefault(normalize_name(name), {'name': name or 'Unnamed product'})
        product.update(opening=opening, given=given, returned=returned, closing=opening + given - returned)
    product_rows = sorted(products.values(), key=lambda row: normalize_name(row['name']))
    cards = Jobcard.query.filter(Jobcard.date >= start, Jobcard.date < end).order_by(Jobcard.date.desc(), Jobcard.id.desc()).all()
    balances = {}
    if cards:
        movements = db.session.query(Jobmovement.jobcard, Jobmovement.product_name, Jobmovement.type_B,
                                     func.coalesce(func.sum(Jobmovement.outflow), 0),
                                     func.coalesce(func.sum(Jobmovement.inflow), 0)).filter(
            Jobmovement.jobcard.in_([str(card.id) for card in cards]), Jobmovement.date < end,
        ).group_by(Jobmovement.jobcard, Jobmovement.product_name, Jobmovement.type_B).all()
        for card_id, name, kind, given, returned in movements:
            balance = balances.setdefault(int(card_id), {'given': 0, 'returned': 0, 'pending': 0})
            balance['given'] += given
            balance['returned'] += returned
            balance['pending'] += max(0, given - returned)
    totals = {field: sum(row[field] for row in product_rows) for field in ('opening', 'given', 'returned', 'closing')}
    return {**totals, 'week_start': first, 'week_end': last, 'custom_range': custom,
            'previous_week': first - timedelta(days=7), 'next_week': first + timedelta(days=7),
            'product_totals': product_rows, 'outflow_pie': _product_pie(product_rows, 'given'),
            'inflow_pie': _product_pie(product_rows, 'returned'), 'jobs': len(cards),
            'recent': [(card, balances.get(card.id, {'given': 0, 'returned': 0, 'pending': 0})) for card in cards]}


def dashboard_period(values):
    if 'date_from' in values or 'date_to' in values:
        return weekly_job_overview(date_from=date.fromisoformat(values.get('date_from', '')),
                                   date_to=date.fromisoformat(values.get('date_to', '')))
    day = date.fromisoformat(values['week']) if values.get('week') else None
    return weekly_job_overview(day)


def dashboard_movement_details(report, kind):
    from modes import ReturnBreakdown
    from sqlalchemy import cast, String
    if kind not in {'all', 'given', 'returned', 'opening', 'closing'}:
        raise ValueError('Unknown movement detail type.')
    start = datetime.combine(report['week_start'], time.min)
    end = datetime.combine(report['week_end'] + timedelta(days=1), time.min)
    query = db.session.query(Jobmovement, Jobcard).outerjoin(
        Jobcard, Jobmovement.jobcard == cast(Jobcard.id, String))
    query = query.filter(Jobmovement.date < (start if kind == 'opening' else end))
    if kind in {'given', 'returned'}:
        query = query.filter(Jobmovement.date >= start)
        query = query.filter(Jobmovement.outflow > 0 if kind == 'given' else Jobmovement.inflow > 0)
    pairs = query.order_by(Jobmovement.date, Jobmovement.id).all()
    breakdowns = {row.movement_id: row for row in ReturnBreakdown.query.filter(
        ReturnBreakdown.movement_id.in_([movement.id for movement, card in pairs])).all()} if pairs else {}
    entries, balance = [], 0
    for movement, card in pairs:
        balance += (movement.outflow or 0) - (movement.inflow or 0)
        breakdown = breakdowns.get(movement.id)
        patterns = []
        if card and movement.flow_type == 'OUT':
            for item in card.product_list if isinstance(card.product_list, list) else []:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get('item_id', ''))
                if item_id and (f'line {item_id}' == movement.partculer.split(', ')[-1]
                                or (movement.bundle and item_id == str(movement.bundle))):
                    patterns.append({'pieces': item.get('pieces_per_bundle', item.get('qty')),
                                     'count': item.get('bundle_count', 1)})
        entries.append({'movement': movement, 'card': card, 'balance': balance,
                        'given': movement.outflow or 0, 'returned': movement.inflow or 0,
                        'brought_forward': movement.date < start,
                        'patterns': patterns, 'breakdown': breakdown})
    return entries


def user_version(user):
    return hashlib.sha256(f'{user.id}:{user.username}:{user.role}:{user.password}'.encode()).hexdigest()


def save_user_access(values, token, actor_id):
    """Account changes and their deduplication/audit use the same users transaction."""
    try:
        # Serialize user writes, then refresh authority after acquiring the SQLite lock.
        db.session.execute(update(User).where(User.id == actor_id).values(role=User.role))
        db.session.expire_all()
        actor = db.session.get(User, actor_id)
        if actor is None or actor.role != 1:
            raise ValueError('Administrator access is required.')
        if not isinstance(token, str) or not token.strip() or len(token) > 128:
            raise ValueError('Reload this form before saving.')
        key = hashlib.sha256(f'{actor.id}:users:{token}'.encode()).hexdigest()
        if UserAccessLog.query.filter_by(request_key=key).first():
            db.session.rollback()
            return 'This account change was already saved.'
        try:
            role = int(values.get('role', ''))
        except (ValueError, TypeError):
            raise ValueError('Select Administrator or Operator.')
        if role not in (1, 2):
            raise ValueError('Select Administrator or Operator.')
        action = values.get('action')
        old_role = None
        if action == 'create':
            name = str(values.get('username', '')).strip().lower()
            password = values.get('password', '')
            if not name or len(name) > 100 or any(c.isspace() for c in name):
                raise ValueError('Enter a username of up to 100 characters without spaces.')
            if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
                raise ValueError('Use a password between 8 and 128 characters.')
            user = User(name, password, role)
            db.session.add(user)
            db.session.flush()
        elif action == 'update':
            target_id = record_id(values.get('user_id'))
            user = db.session.get(User, target_id) if target_id else None
            if user is None:
                raise ValueError('User not found.')
            if values.get('version') != user_version(user):
                raise ValueError('This account changed. Reload and review before saving.')
            if user.id == actor.id and role != 1:
                raise ValueError('You cannot remove your own administrator access.')
            old_role = user.role
            user.role = role
            password = values.get('password', '')
            if password:
                if len(password) < 8 or len(password) > 128:
                    raise ValueError('Use a password between 8 and 128 characters.')
                user.password = generate_password_hash(password)
        else:
            raise ValueError('Choose a valid account action.')
        db.session.add(UserAccessLog(
            request_key=key, changed_at=datetime.now(), actor=actor.username,
            user_id=user.id, action=action, old_role=old_role, new_role=role,
        ))
        db.session.commit()
        return 'User account saved.'
    except IntegrityError:
        db.session.rollback()
        raise ValueError('That username already exists. Reload and check the account list.')
    except Exception:
        db.session.rollback()
        raise


def register_simple_workflow(app, admin_required):
    @app.before_request
    def enforce_manual_workflow():
        if not app.config.get('SIMPLE_WORKFLOW'):
            return
        endpoint = request.endpoint
        disabled = endpoint in DISABLED_ENDPOINTS
        if endpoint in {'edit_entry', 'edit_search'}:
            entity = ((request.view_args or {}).get('entity_type') if endpoint == 'edit_entry'
                      else request.args.get('type'))
            disabled = entity not in CORE_ENTITIES and entity != 'movement'
        if disabled:
            message = 'This workflow is disabled in V2. Use manual job cards.'
            if endpoint in {'submit_jobcard', 'edit_search'}:
                return jsonify(success=False, code=410, message=message), 410
            return render_template('disabled_workflow.html', message=message), 410

    @app.route('/users', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def manage_users():
        form = WriteForm()
        if form.validate_on_submit():
            try:
                flash(save_user_access(request.form, form.submission_token.data, current_user.id), 'success')
                return redirect(url_for('manage_users'))
            except ValueError as error:
                flash(str(error), 'danger')
        elif request.method == 'POST':
            flash('This form expired. Reload and try again.', 'danger')
        return render_template(
            'manage_users.html', id=current_user.role, form=form,
            users=User.query.order_by(User.username).all(), user_version=user_version,
            access_logs=UserAccessLog.query.order_by(UserAccessLog.id.desc()).limit(50).all(),
        )
