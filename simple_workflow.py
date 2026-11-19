"""V2 manual-only workflow boundaries, job dashboard and administrator accounts."""

import hashlib
import hmac
import json
from datetime import date, datetime, time, timedelta
import math

from flask import abort, flash, jsonify, redirect, render_template, request, url_for, current_app
from flask_login import current_user, login_required
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from form import WriteForm
from modes import db, User, UserAccessLog, Jobcard, Jobmovement, Item_data, Outworker
from validation import record_id
from item_aliases import normalize_name
from database_writes import begin_write
from piece_totals import piece_sum
from kept_products import kept_totals, kept_movement_pairs
from modes import JobKeptProduct

CORE_ENTITIES = frozenset({'jobcard', 'product', 'outworker'})

RETIRED_ROUTES = {
    'bale_entery': '/bale_entery', 'lump_home': '/lumpentry',
    'bundle_entery': '/bundle_entery', 'add_cuter': '/add_cutter',
    'add_suppy': '/add_suppy', 'cutter_report': '/cutter_report',
    'product_report': '/product_report', 'find_edit': '/find_edit',
    'submit_jobcard': '/submit-jobcard',
}
DISABLED_ENDPOINTS = frozenset(RETIRED_ROUTES)


def job_overview():
    """Lifetime product totals, with pending balances calculated per job and type."""
    grouped = db.session.query(
        Jobmovement.jobcard, Jobmovement.product_name, Jobmovement.type_B,
        func.coalesce(piece_sum(Jobmovement.outflow), 0),
        func.coalesce(piece_sum(Jobmovement.inflow), 0),
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
    kept = kept_totals()
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
        kept_quantity = kept[(str(parsed), product, kind)]
        if kept_quantity:
            product_total['kept'] = product_total.get('kept', 0) + kept_quantity
        pending = max(0, given - returned - kept_quantity)
        product_total['pending'] += pending
        total = totals.setdefault(parsed, {'given': 0, 'returned': 0, 'pending': 0})
        total['given'] += given
        total['returned'] += returned
        if kept_quantity:
            total['kept'] = total.get('kept', 0) + kept_quantity
        total['pending'] += pending
    recent = Jobcard.query.order_by(Jobcard.date.desc(), Jobcard.id.desc()).limit(20).all()
    return {
        'jobs': len(card_ids),
        'given': sum(row['given'] for row in product_totals.values()),
        'returned': sum(row['returned'] for row in product_totals.values()),
        'kept': sum(row.get('kept', 0) for row in product_totals.values()),
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


def report_period(day=None, *, date_from=None, date_to=None):
    """Resolve the weekly default or an inclusive custom range."""
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
    return {'week_start': first, 'week_end': last, 'custom_range': custom,
            'previous_week': first - timedelta(days=7), 'next_week': first + timedelta(days=7)}


def weekly_job_overview(day=None, *, date_from=None, date_to=None):
    """Period account (Wednesday–Tuesday by default), with balances at the To date."""
    period = report_period(day, date_from=date_from, date_to=date_to)
    first, last = period['week_start'], period['week_end']
    start = datetime.combine(first, time.min)
    end = datetime.combine(last + timedelta(days=1), time.min)
    products = {normalize_name(item.name): {'name': item.name, 'opening': 0, 'given': 0, 'returned': 0, 'closing': 0}
                for item in Item_data.query.order_by(Item_data.name).all()}
    from sqlalchemy import case
    rows = db.session.query(
        Jobmovement.product_name,
        func.coalesce(piece_sum(case((Jobmovement.date < start,
                                     func.coalesce(Jobmovement.outflow, 0) - func.coalesce(Jobmovement.inflow, 0)), else_=0)), 0),
        func.coalesce(piece_sum(case((Jobmovement.date >= start, Jobmovement.outflow), else_=0)), 0),
        func.coalesce(piece_sum(case((Jobmovement.date >= start, Jobmovement.inflow), else_=0)), 0),
    ).filter(Jobmovement.date < end).group_by(Jobmovement.product_name).all()
    for name, opening, given, returned in rows:
        product = products.setdefault(normalize_name(name), dict(name=name or 'Unnamed product',
                                      opening=0, given=0, returned=0, closing=0))
        product['opening'] += opening
        product['given'] += given
        product['returned'] += returned
        product['closing'] += opening + given - returned
    names = {row.id: row.name for row in Item_data.query.all()}
    for row in JobKeptProduct.query.filter(JobKeptProduct.date < end).all():
        name = names.get(row.product_id, row.product_name)
        product = products.setdefault(normalize_name(name), dict(name=name, opening=0, given=0, returned=0, closing=0))
        if row.date < start:
            product['opening'] -= row.pieces
        else:
            product['kept'] = product.get('kept', 0) + row.pieces
        product['closing'] -= row.pieces
    product_rows = sorted(products.values(), key=lambda row: normalize_name(row['name']))
    cards = Jobcard.query.filter(Jobcard.date >= start, Jobcard.date < end).order_by(Jobcard.date.desc(), Jobcard.id.desc()).all()
    balances = {}
    if cards:
        movements = db.session.query(Jobmovement.jobcard, Jobmovement.product_name, Jobmovement.type_B,
                                     func.coalesce(piece_sum(Jobmovement.outflow), 0),
                                     func.coalesce(piece_sum(Jobmovement.inflow), 0)).filter(
            Jobmovement.jobcard.in_([str(card.id) for card in cards]), Jobmovement.date < end,
        ).group_by(Jobmovement.jobcard, Jobmovement.product_name, Jobmovement.type_B).all()
        kept = kept_totals(before=end)
        for card_id, name, kind, given, returned in movements:
            balance = balances.setdefault(int(card_id), {'given': 0, 'returned': 0, 'pending': 0})
            balance['given'] += given
            balance['returned'] += returned
            kept_quantity = kept[(str(card_id), name, kind)]
            if kept_quantity:
                balance['kept'] = balance.get('kept', 0) + kept_quantity
            balance['pending'] += max(0, given - returned - kept_quantity)
    totals = {field: sum(row[field] for row in product_rows) for field in ('opening', 'given', 'returned', 'closing')}
    totals['kept'] = sum(row.get('kept', 0) for row in product_rows)
    return {**totals, **period,
            'product_totals': product_rows, 'outflow_pie': _product_pie(product_rows, 'given'),
            'inflow_pie': _product_pie(product_rows, 'returned'), 'jobs': len(cards),
            'recent': [(card, balances.get(card.id, {'given': 0, 'returned': 0, 'pending': 0})) for card in cards]}


def report_period_selection(values):
    if 'date_from' in values or 'date_to' in values:
        return {'date_from': date.fromisoformat(values.get('date_from', '')),
                'date_to': date.fromisoformat(values.get('date_to', ''))}
    return {'day': date.fromisoformat(values['week']) if values.get('week') else None}


def dashboard_period(values):
    return weekly_job_overview(**report_period_selection(values))


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
    if kind not in {'given', 'returned'}:
        pairs += kept_movement_pairs(start if kind == 'opening' else end)
        pairs.sort(key=lambda pair: (pair[0].date, pair[0].flow_type == 'KEPT', int(str(pair[0].id).lstrip('K'))))
    breakdowns = {row.movement_id: row for row in ReturnBreakdown.query.filter(
        ReturnBreakdown.movement_id.in_([movement.id for movement, card in pairs])).all()} if pairs else {}
    entries, balance = [], 0
    for movement, card in pairs:
        balance += (movement.outflow or 0) - (movement.inflow or 0) - getattr(movement, 'kept', 0)
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
                        'kept': getattr(movement, 'kept', 0),
                        'brought_forward': movement.date < start,
                        'patterns': patterns, 'breakdown': breakdown})
    return entries


def user_version(user):
    return hashlib.sha256(
        f'{user.id}:{user.username}:{user.role}:{user.is_active}:{user.password}:{user.auth_id}'.encode()
    ).hexdigest()


def dashboard_job_balances(report, kind, entries, product_filter='', sort_by='age_desc'):
    """Job/product balances at the selected cutoff, never today's live balance."""
    snapshots = dashboard_movement_details(report, 'closing') if kind in {'given', 'returned'} else entries
    def group_key(entry):
        movement, card = entry['movement'], entry['card']
        return ('job', card.id) if card else ('unlinked', str(movement.jobcard or ''), movement.name_of_mater)
    selected = {group_key(entry) for entry in entries} if kind in {'given', 'returned'} else None
    groups = {}
    for entry in snapshots:
        key = group_key(entry)
        if selected is not None and key not in selected:
            continue
        movement, card = entry['movement'], entry['card']
        if product_filter.strip().casefold() not in str(movement.product_name or '').casefold():
            continue
        group = groups.setdefault(key, {'card': card, 'worker': card.given_to if card else movement.name_of_mater,
                                        'given': 0, 'returned': 0, 'kept': 0, 'products': {}})
        product_key = (movement.product_name, movement.type_B)
        product = group['products'].setdefault(product_key, {'name': product_key[0], 'type': product_key[1],
                                                           'given': 0, 'returned': 0, 'kept': 0})
        for field in ('given', 'returned', 'kept'):
            group[field] += entry[field]
            product[field] += entry[field]
    jobs, unlinked, product_totals = [], [], {}
    for group in groups.values():
        products = list(group['products'].values())
        for product in products:
            product['remaining'] = product['given'] - product['returned'] - product['kept']
        if kind in {'opening', 'closing'} and not any(product['remaining'] for product in products):
            continue
        group['products'] = sorted(products, key=lambda row: (row['name'] or '', row['type'] or ''))
        group['remaining'] = group['given'] - group['returned'] - group['kept']
        group['pieces_left'] = sum(max(0, product['remaining']) for product in products)
        group['check_balance'] = any(product['remaining'] < 0 for product in products)
        cutoff = report['week_start'] if kind == 'opening' else report['week_end']
        group['age_days'] = max(0, (cutoff - group['card'].date.date()).days) if group['card'] else None
        (jobs if group['card'] else unlinked).append(group)
        for product in products:
            key = (product['name'], product['type'])
            total = product_totals.setdefault(key, {'name': key[0], 'type': key[1], 'given': 0,
                'returned': 0, 'kept': 0, 'remaining': 0, 'pieces_left': 0, 'jobs': 0, 'unlinked': 0})
            for field in ('given', 'returned', 'kept', 'remaining'):
                total[field] += product[field]
            total['pieces_left'] += max(0, product['remaining'])
            total['jobs'] += bool(group['card']) and product['remaining'] != 0
            total['unlinked'] += not bool(group['card'])
    def order(row):
        name = str(row.get('worker') or '')
        product = min((str(item['name'] or '').casefold() for item in row['products']), default='')
        age = row['age_days'] or 0
        tie = row['card'].id if row.get('card') else name
        if sort_by == 'age_asc':
            return (age, name, tie)
        if sort_by == 'quantity_desc':
            return (-row['pieces_left'], name, tie)
        if sort_by == 'quantity_asc':
            return (row['pieces_left'], name, tie)
        if sort_by == 'product':
            return (product, name, tie)
        return (-age, name, tie)
    jobs.sort(key=order)
    workers = {}
    for job in jobs:
        worker = workers.setdefault(job['worker'], {'worker': job['worker'], 'jobs': [], 'products': {},
            'given': 0, 'returned': 0, 'kept': 0, 'remaining': 0, 'pieces_left': 0, 'age_days': 0,
            'worker_id': record_id(str(job['worker']).split('***', 1)[0])})
        worker['jobs'].append(job)
        worker['age_days'] = max(worker['age_days'], job['age_days'])
        for field in ('given', 'returned', 'kept', 'remaining', 'pieces_left'):
            worker[field] += job[field]
        for product in job['products']:
            key = (product['name'], product['type'])
            total = worker['products'].setdefault(key, {'name': key[0], 'type': key[1],
                'given': 0, 'returned': 0, 'kept': 0, 'remaining': 0, 'pieces_left': 0})
            for field in ('given', 'returned', 'kept', 'remaining'):
                total[field] += product[field]
            total['pieces_left'] += max(0, product['remaining'])
    for worker in workers.values():
        worker['products'] = sorted(worker['products'].values(), key=lambda row: (row['name'] or '', row['type'] or ''))
    workers = sorted(workers.values(), key=order)
    rows = jobs + unlinked
    return {'jobs': jobs, 'workers': workers, 'unlinked': unlinked,
            'products': sorted(product_totals.values(), key=lambda row: (row['name'] or '', row['type'] or '')),
            'totals': {field: sum(row[field] for row in rows)
                       for field in ('given', 'returned', 'kept', 'remaining', 'pieces_left')}}


def _require_another_active_admin(target_id):
    admins = User.query.filter_by(role=1, is_active=True).filter(User.id != target_id).count()
    if admins == 0:
        raise ValueError('Keep at least one other active administrator before changing this account.')


def save_user_access(values, token, actor_id):
    """Account changes and their deduplication/audit use the same users transaction."""
    try:
        # Serialize user writes, then refresh authority after acquiring the SQLite lock.
        begin_write(User)
        db.session.execute(update(User).where(User.id == actor_id).values(role=User.role))
        db.session.expire_all()
        actor = db.session.get(User, actor_id)
        if actor is None or actor.role != 1 or not actor.is_active:
            raise ValueError('Administrator access is required.')
        if not isinstance(token, str) or not token.strip() or len(token) > 128:
            raise ValueError('Reload this form before saving.')
        key = hashlib.sha256(f'{actor.id}:users:{token}'.encode()).hexdigest()
        # Account payloads can contain a password. A plain fast digest would
        # expose an offline password-guessing oracle if only the audit DB leaked.
        signing_key = current_app.secret_key
        if isinstance(signing_key, str):
            signing_key = signing_key.encode()
        digest = hmac.new(signing_key, json.dumps({k: v for k, v in dict(values).items()
                                           if k not in {'version', 'csrf_token', 'submission_token'}},
                                          sort_keys=True, default=str).encode(), hashlib.sha256).hexdigest()
        previous = UserAccessLog.query.filter_by(request_key=key).first()
        if previous:
            matches = previous.payload_hash == digest
            db.session.rollback()
            if not matches:
                raise ValueError('This request ID was already used for a different account change.')
            return 'This account change was already saved.'
        action = values.get('action')
        old_role = None
        role = None
        message = 'User account saved.'
        if action == 'create':
            try:
                role = int(values.get('role', ''))
            except (ValueError, TypeError):
                raise ValueError('New accounts must have Administrator access.')
            if role != 1:
                raise ValueError('The Operator role is no longer available. New accounts must be Administrators.')
            name = str(values.get('username', '')).strip().lower()
            password = values.get('password', '')
            if not name or len(name) > 100 or any(c.isspace() for c in name):
                raise ValueError('Enter a username of up to 100 characters without spaces.')
            if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
                raise ValueError('Use a password between 8 and 128 characters.')
            user = User(name, password, role)
            # Audit IDs must not be reassigned after an account is deleted.
            user.id = max(db.session.query(func.max(User.id)).scalar() or 0,
                          db.session.query(func.max(UserAccessLog.user_id)).scalar() or 0) + 1
            db.session.add(user)
            db.session.flush()
        elif action == 'update':
            target_id = record_id(values.get('user_id'))
            user = db.session.get(User, target_id) if target_id else None
            if user is None:
                raise ValueError('User not found.')
            if values.get('version') != user_version(user):
                raise ValueError('This account changed. Reload and review before saving.')
            try:
                role = 1 if values.get('grant_admin') == '1' else int(values.get('role', user.role))
            except (ValueError, TypeError):
                raise ValueError('Select valid account access.')
            # Keep legacy restrictions unless an administrator explicitly upgrades
            # the account. Do not offer or assign the retired role to other users.
            if role != 1 and role != user.role:
                raise ValueError('The Operator role is no longer available. Disable the account to remove access.')
            if user.id == actor.id and role != 1:
                raise ValueError('You cannot remove your own administrator access.')
            old_role = user.role
            if user.is_active and user.role == 1 and role != 1:
                _require_another_active_admin(user.id)
            user.role = role
            password = values.get('password', '')
            if password:
                if len(password) < 8 or len(password) > 128:
                    raise ValueError('Use a password between 8 and 128 characters.')
                user.password = generate_password_hash(password)
            if password or old_role != role:
                user.revoke_sessions()
        elif action in ('set_active', 'delete'):
            target_id = record_id(values.get('user_id'))
            user = db.session.get(User, target_id) if target_id else None
            if user is None:
                raise ValueError('User not found.')
            if values.get('version') != user_version(user):
                raise ValueError('This account changed. Reload and review before saving.')
            if user.id == actor.id:
                raise ValueError('You cannot disable or delete your own account.')
            old_role = user.role
            role = user.role
            if action == 'set_active':
                active_value = values.get('active')
                if active_value not in ('0', '1'):
                    raise ValueError('Choose whether the account should be enabled or disabled.')
                is_active = active_value == '1'
                if not is_active and user.is_active and user.role == 1:
                    _require_another_active_admin(user.id)
                user.is_active = is_active
                user.revoke_sessions()
                action = 'enabled' if is_active else 'disabled'
                message = 'User account enabled.' if is_active else 'User account disabled.'
            else:
                if user.is_active and user.role == 1:
                    _require_another_active_admin(user.id)
                action = 'deleted'
                role = 0
                message = 'User account deleted.'
                db.session.add(UserAccessLog(
                    request_key=key, changed_at=datetime.now(), actor=actor.username,
                    user_id=user.id, action=action, old_role=old_role, new_role=role,
                    payload_hash=digest,
                ))
                db.session.delete(user)
        else:
            raise ValueError('Choose a valid account action.')
        if action != 'deleted':
            db.session.add(UserAccessLog(
                request_key=key, changed_at=datetime.now(), actor=actor.username,
                user_id=user.id, action=action, old_role=old_role, new_role=role,
                payload_hash=digest,
            ))
        db.session.commit()
        return message
    except IntegrityError:
        db.session.rollback()
        raise ValueError('That username already exists. Reload and check the account list.')
    except Exception:
        db.session.rollback()
        raise


def register_simple_workflow(app, admin_required):
    # Compatibility URLs only: no retired V1 handler or write implementation is
    # registered, even if an older config file sets SIMPLE_WORKFLOW=False.
    def retired_workflow():
        return render_template('disabled_workflow.html', message='This workflow has been retired. Use manual job cards.'), 410

    for endpoint, path in RETIRED_ROUTES.items():
        app.add_url_rule(path, endpoint, retired_workflow,
                         methods=['POST'] if endpoint == 'submit_jobcard' else ['GET', 'POST'])

    @app.before_request
    def enforce_manual_workflow():
        endpoint = request.endpoint
        disabled = endpoint in DISABLED_ENDPOINTS
        if endpoint in {'edit_entry', 'edit_search'}:
            entity = ((request.view_args or {}).get('entity_type') if endpoint == 'edit_entry'
                      else request.args.get('type'))
            disabled = entity not in CORE_ENTITIES and entity != 'movement'
        if disabled:
            message = 'This workflow has been retired. Use manual job cards.'
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
