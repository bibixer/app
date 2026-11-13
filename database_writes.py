"""SQLite connection policy and fresh, serialized write transactions."""

import sqlite3

from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError, TimeoutError as PoolTimeout
from sqlalchemy.engine import make_url

from modes import db


class DatabaseBusy(Exception):
    """The save could not be confirmed; retry using the same submission key."""


def sqlite_pool_options(url):
    parsed = make_url(url)
    if parsed.get_backend_name() == 'sqlite' and parsed.database not in (None, '', ':memory:'):
        # Requests use both the users and business databases. Keep enough slots
        # in both pools for the supported worker count, including stress runs,
        # so handlers do not hold one database while exhausting the other pool.
        return dict(pool_size=32, max_overflow=32, pool_timeout=65)
    return {}


def is_database_busy(error):
    if isinstance(error, PoolTimeout):
        return True
    original = getattr(error, 'orig', error)
    code = getattr(original, 'sqlite_errorcode', 0)
    return isinstance(original, sqlite3.OperationalError) and (
        (code & 255) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
        or 'database is locked' in str(original).lower()
    )


def configure_sqlite(engine, timeout_ms=60000):
    if engine.dialect.name != 'sqlite':
        return

    def connect(connection, _record):
        from piece_totals import SQLitePieceSum
        connection.create_aggregate('exact_piece_sum', 1, SQLitePieceSum)
        cursor = connection.cursor()
        try:
            cursor.execute(f'PRAGMA busy_timeout={int(timeout_ms)}')
            cursor.execute('PRAGMA foreign_keys=ON')
            # Readers can continue while a writer commits. SQLite still permits
            # only one writer; business balance checks run under that lock.
            cursor.execute('PRAGMA journal_mode=WAL')
        finally:
            cursor.close()

    event.listen(engine, 'connect', connect)


def begin_write(model):
    """Start at a service write boundary, discarding earlier read snapshots.

    A busy timeout alone cannot fix a stale read-to-write upgrade. Acquire the
    writer lock before re-reading quantities, versions, or retry claims. Caller
    changes, when present, remain part of the same atomic transaction.
    """
    if db.session.new or db.session.dirty or db.session.deleted:
        # Some service callers prepare related corrections before entering the
        # write service. Preserve those changes; flushing obtains the write lock
        # and their commit/rollback stays atomic with the request claim.
        try:
            db.session.flush()
        except OperationalError as error:
            db.session.rollback()
            if is_database_busy(error):
                raise DatabaseBusy('The database is busy. Retry the same submission.') from error
            raise
        return
    engine = db.session.get_bind(mapper=model)
    if engine.dialect.name == 'sqlite':
        connection = db.session.connection(bind_arguments={'mapper': model})
        if connection.connection.driver_connection.in_transaction:
            # A caller may already have flushed related changes (so dirty/new
            # are now empty). Do not roll back that owned transaction either.
            return
    db.session.rollback()
    if engine.dialect.name != 'sqlite':
        return
    try:
        db.session.execute(text('BEGIN IMMEDIATE'), bind_arguments={'mapper': model})
    except (OperationalError, PoolTimeout) as error:
        db.session.rollback()
        if is_database_busy(error):
            raise DatabaseBusy('The database is busy. Nothing was saved. Retry the same submission.') from error
        raise
