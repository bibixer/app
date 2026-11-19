"""Cash receipts and cash payments recorded by the outworker workflows."""

from datetime import datetime, time, timedelta

from sqlalchemy import case, exists, literal, select, union_all

from modes import db, JobKeptProduct, OutworkerAdvance, OutworkerAdvanceReceipt, OutworkerPayroll
from piece_totals import piece_sum


def cash_book_period(first, last, *, include_entries=False):
    start = datetime.combine(first, time.min)
    end = datetime.combine(last + timedelta(days=1), time.min)

    def cash_rows(model, kind, recorded_at, amount):
        return select(
            literal(kind).label('kind'), model.id.label('record_id'), recorded_at.label('recorded_at'),
            model.worker_id, model.worker_name, model.recorded_by, model.reference, model.note,
            amount.label('amount'),
        ).where(model.method == 'Cash', recorded_at < end, amount > 0)

    advances = cash_rows(OutworkerAdvance, 'advance', OutworkerAdvance.paid_at, OutworkerAdvance.amount_paise).where(
        ~exists().where(JobKeptProduct.advance_id == OutworkerAdvance.id)
    )
    payrolls = cash_rows(OutworkerPayroll, 'payroll', OutworkerPayroll.paid_at, OutworkerPayroll.net_paise)
    repayments = cash_rows(OutworkerAdvanceReceipt, 'repayment',
                           OutworkerAdvanceReceipt.received_at, OutworkerAdvanceReceipt.amount_paise)
    movements = union_all(advances, payrolls, repayments).cte('cash_movements')
    cash = movements.c
    received = cash.kind == 'repayment'
    signed = case((received, cash.amount), else_=-cash.amount)
    before_period = cash.recorded_at < start

    if not include_entries:
        opening, debit, credit = db.session.execute(select(
            piece_sum(case((before_period, signed), else_=0)),
            piece_sum(case((~before_period & ~received, cash.amount), else_=0)),
            piece_sum(case((~before_period & received, cash.amount), else_=0)),
        ).select_from(movements)).one()
        opening, debit, credit = opening or 0, debit or 0, credit or 0
        return {'opening': opening, 'debit': debit, 'credit': credit, 'closing': opening + credit - debit}

    # Fetch opening and rows together so the page reflects one database snapshot.
    opening_row = select(literal('opening'), literal(None), literal(None), literal(None), literal(None),
                         literal(None), literal(None), literal(None), piece_sum(signed)).where(before_period)
    period_rows = select(movements).where(~before_period)
    ledger = union_all(period_rows, opening_row).subquery().c
    sequence = case((ledger.kind == 'advance', 0), (ledger.kind == 'payroll', 1), else_=2)
    rows = iter(db.session.execute(select(*ledger).order_by(
        ledger.recorded_at.asc().nulls_first(), sequence, ledger.record_id)))
    opening = int(next(rows).amount or 0)
    balance = opening
    debit = credit = 0
    entries = []
    for row in rows:
        entry = dict(row._mapping)
        incoming = row.kind == 'repayment'
        entry['credit'] = row.amount if incoming else 0
        entry['debit'] = 0 if incoming else row.amount
        credit += entry['credit']
        debit += entry['debit']
        balance += entry['credit'] - entry['debit']
        entry['balance'] = balance
        entries.append(entry)
    return {'opening': opening, 'debit': debit, 'credit': credit, 'closing': balance, 'entries': entries}
