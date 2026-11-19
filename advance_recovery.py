"""Ledger reports for direct advance repayments and payroll deductions."""

from datetime import datetime, time, timedelta

from sqlalchemy import case, exists, literal, select, union_all

from modes import db, JobKeptProduct, Outworker, OutworkerAdvance, OutworkerAdvanceReceipt, OutworkerPayroll
from piece_totals import piece_sum


def outstanding_worker_totals(worker_id=None):
    changes = union_all(
        select(OutworkerAdvance.worker_id, OutworkerAdvance.amount_paise.label('amount')),
        select(OutworkerPayroll.worker_id, -OutworkerPayroll.deduction_paise),
        select(OutworkerAdvanceReceipt.worker_id, -OutworkerAdvanceReceipt.amount_paise),
    ).subquery()
    query = select(Outworker.id, Outworker.name, Outworker.adders,
                   piece_sum(changes.c.amount).label('balance')).join(
        changes, changes.c.worker_id == Outworker.id
    ).group_by(Outworker.id, Outworker.name, Outworker.adders).order_by(Outworker.name, Outworker.id)
    if worker_id is not None:
        query = query.where(Outworker.id == worker_id)
    return [row for row in db.session.execute(query) if row.balance > 0]


def list_advances(worker_id=None):
    kept = exists().where(JobKeptProduct.advance_id == OutworkerAdvance.id)
    query = select(OutworkerAdvance.id, OutworkerAdvance.paid_at, OutworkerAdvance.worker_id,
                   OutworkerAdvance.amount_paise, OutworkerAdvance.method, OutworkerAdvance.reference,
                   Outworker.name, Outworker.adders, kept.label('kept')
                   ).join(Outworker, Outworker.id == OutworkerAdvance.worker_id)
    if worker_id is not None:
        query = query.where(OutworkerAdvance.worker_id == worker_id)
    return db.session.execute(query.order_by(OutworkerAdvance.paid_at.desc(),
                                            OutworkerAdvance.id.desc())).all()


def advance_recovery_period(first, last):
    start = datetime.combine(first, time.min)
    end = datetime.combine(last + timedelta(days=1), time.min)

    def recovery_rows(kind, recorded_at, amount):
        return select(literal(kind).label('kind'), amount.label('amount')).where(
            recorded_at >= start, recorded_at < end, amount > 0)

    recovery = union_all(
        recovery_rows('repayment', OutworkerAdvanceReceipt.received_at, OutworkerAdvanceReceipt.amount_paise),
        recovery_rows('deduction', OutworkerPayroll.paid_at, OutworkerPayroll.deduction_paise),
    ).subquery()
    rows = recovery.c
    direct = rows.kind == 'repayment'
    received, deducted = db.session.execute(select(
        piece_sum(case((direct, rows.amount), else_=0)),
        piece_sum(case((~direct, rows.amount), else_=0)),
    ).select_from(recovery)).one()
    return {'received': received or 0, 'deducted': deducted or 0,
            'recovered': (received or 0) + (deducted or 0)}
