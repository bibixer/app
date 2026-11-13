"""Exact piece totals, including oversized historical SQLite ledgers."""
from sqlalchemy.sql.functions import GenericFunction
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import TypeDecorator, Integer


class ExactInteger(TypeDecorator):
    impl = Integer
    cache_ok = True

    def process_result_value(self, value, dialect):
        return int(value) if value is not None else None


class piece_sum(GenericFunction):
    type = ExactInteger()
    inherit_cache = True


@compiles(piece_sum)
def default_sum(element, compiler, **kwargs):
    return 'sum(%s)' % compiler.process(element.clauses, **kwargs)


@compiles(piece_sum, 'sqlite')
def sqlite_sum(element, compiler, **kwargs):
    return 'exact_piece_sum(%s)' % compiler.process(element.clauses, **kwargs)


class SQLitePieceSum:
    def __init__(self):
        self.total = 0

    def step(self, value):
        if value is not None:
            self.total += int(value)

    def finalize(self):
        # sqlite3 cannot return Python integers outside the signed 64-bit range.
        return str(self.total)
