"""Small, transactional upgrades for existing SQLite installations."""

from sqlalchemy import inspect
import secrets
from contextlib import contextmanager


@contextmanager
def schema_transaction(engine):
    """Serialize inspection and DDL together, including concurrent app starts."""
    with engine.connect() as connection:
        if engine.dialect.name == 'sqlite':
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        else:
            connection.begin()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def ensure_product_value(engine):
    with schema_transaction(engine) as connection:
        columns = {c['name'] for c in inspect(connection).get_columns('ItemData')}
        if 'product_value_paise' not in columns:
            connection.exec_driver_sql('ALTER TABLE ItemData ADD COLUMN product_value_paise BIGINT NOT NULL DEFAULT 0 CHECK(product_value_paise >= 0 AND product_value_paise <= 99999999999)')


def ensure_outworker_contact_number(engine):
    with schema_transaction(engine) as connection:
        columns = {column['name'] for column in inspect(connection).get_columns('OutworkData')}
        if 'contact_number' not in columns:
            connection.exec_driver_sql('ALTER TABLE OutworkData ADD COLUMN contact_number VARCHAR(10)')


def ensure_payroll_receipt_archive(engine):
    with schema_transaction(engine) as connection:
        columns = {column['name'] for column in inspect(connection).get_columns('outworker_payroll')}
        if 'receipt_archive' not in columns:
            connection.exec_driver_sql('ALTER TABLE outworker_payroll ADD COLUMN receipt_archive JSON')


def ensure_security_schema(engine, users_engine):
    """Additive upgrades: retain historical rows, constrain future ledger writes."""
    with schema_transaction(users_engine) as connection:
        columns = {c['name'] for c in inspect(connection).get_columns('users')}
        if 'auth_id' not in columns:
            connection.exec_driver_sql('ALTER TABLE users ADD COLUMN auth_id VARCHAR(64)')
        rows = connection.exec_driver_sql('SELECT id FROM users WHERE auth_id IS NULL').all()
        for row in rows:
            connection.exec_driver_sql('UPDATE users SET auth_id=? WHERE id=?',
                                       (secrets.token_hex(32), row[0]))
        connection.exec_driver_sql('CREATE UNIQUE INDEX IF NOT EXISTS ix_users_auth_id ON users(auth_id)')
        columns = {c['name'] for c in inspect(connection).get_columns('user_access_log')}
        if 'payload_hash' not in columns:
            connection.exec_driver_sql('ALTER TABLE user_access_log ADD COLUMN payload_hash VARCHAR(64)')
    with schema_transaction(engine) as connection:
        columns = {c['name'] for c in inspect(connection).get_columns('request_dedup')}
        for name, sql_type in [('payload_hash', 'VARCHAR(64)'), ('receipt', 'JSON')]:
            if name not in columns:
                connection.exec_driver_sql(f'ALTER TABLE request_dedup ADD COLUMN {name} {sql_type}')
        if engine.dialect.name != 'sqlite':
            return
        from validation import MAX_PIECES
        from bundle_types import BUNDLE_TYPE_VALUES
        types = ','.join("'" + value.replace("'", "''") + "'" for value in BUNDLE_TYPE_VALUES)
        for operation in ('INSERT', 'UPDATE'):
            connection.exec_driver_sql(f'''
                CREATE TRIGGER IF NOT EXISTS validate_movement_{operation.lower()}
                BEFORE {operation} ON JobmovementData BEGIN
                    SELECT CASE WHEN typeof(NEW.outflow) != 'integer'
                        OR typeof(NEW.inflow) != 'integer'
                        OR NEW.outflow < 0 OR NEW.inflow < 0
                        OR NEW.outflow > {MAX_PIECES} OR NEW.inflow > {MAX_PIECES}
                        THEN RAISE(ABORT, 'Invalid movement quantity') END;
                    SELECT CASE WHEN NEW.flow_type IS NULL OR NEW.type_B IS NULL
                        OR NEW.flow_type NOT IN ('IN','OUT') OR NEW.type_B NOT IN ({types})
                        OR (NEW.flow_type='IN' AND NEW.outflow != 0)
                        OR (NEW.flow_type='OUT' AND NEW.inflow != 0)
                        THEN RAISE(ABORT, 'Invalid movement direction or bundle type') END;
                    SELECT CASE WHEN
                        ((NEW.jobcard IS NULL OR NEW.jobcard='') AND NEW.flow_type='OUT')
                        OR (NEW.jobcard IS NOT NULL AND NEW.jobcard != '' AND NOT EXISTS
                            (SELECT 1 FROM JobcardData WHERE CAST(id AS TEXT)=CAST(NEW.jobcard AS TEXT)))
                        THEN RAISE(ABORT, 'Movement references a missing job card') END;
                END
            ''')
        connection.exec_driver_sql('''
            CREATE TRIGGER IF NOT EXISTS protect_jobcard_delete BEFORE DELETE ON JobcardData
            WHEN EXISTS (SELECT 1 FROM JobmovementData WHERE jobcard=CAST(OLD.id AS TEXT))
            BEGIN SELECT RAISE(ABORT, 'Job card still has movements'); END
        ''')
        connection.exec_driver_sql('''
            CREATE TRIGGER IF NOT EXISTS protect_jobcard_id BEFORE UPDATE OF id ON JobcardData
            WHEN NEW.id != OLD.id AND EXISTS
                (SELECT 1 FROM JobmovementData WHERE jobcard=CAST(OLD.id AS TEXT))
            BEGIN SELECT RAISE(ABORT, 'Job card still has movements'); END
        ''')


def ensure_user_active_column(engine):
    """Add account enable/disable state to existing user databases."""
    with schema_transaction(engine) as connection:
        if 'users' not in inspect(connection).get_table_names():
            return
        columns = {column['name'] for column in inspect(connection).get_columns('users')}
        if 'is_active' not in columns:
            connection.exec_driver_sql(
                'ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE'
            )


def allow_job_payment_installments(engine):
    """Replace the old one-payment-per-job constraint, preserving every receipt row."""
    if engine.dialect.name != 'sqlite':
        return
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        try:
            constraints = inspect(connection).get_unique_constraints('outworker_payroll_job')
            if not any(row['column_names'] == ['jobcard_id'] for row in constraints):
                connection.commit()
                return
            connection.exec_driver_sql('''
                CREATE TABLE outworker_payroll_job_installments (
                    id INTEGER NOT NULL PRIMARY KEY,
                    payroll_id INTEGER NOT NULL REFERENCES outworker_payroll(id),
                    jobcard_id INTEGER NOT NULL REFERENCES "JobcardData"(id),
                    pieces INTEGER NOT NULL,
                    amount_paise BIGINT NOT NULL,
                    lines JSON NOT NULL,
                    UNIQUE (payroll_id, jobcard_id)
                )
            ''')
            connection.exec_driver_sql('''
                INSERT INTO outworker_payroll_job_installments
                    (id, payroll_id, jobcard_id, pieces, amount_paise, lines)
                SELECT id, payroll_id, jobcard_id, pieces, amount_paise, lines
                FROM outworker_payroll_job
            ''')
            connection.exec_driver_sql('DROP TABLE outworker_payroll_job')
            connection.exec_driver_sql('ALTER TABLE outworker_payroll_job_installments RENAME TO outworker_payroll_job')
            connection.exec_driver_sql('CREATE INDEX ix_outworker_payroll_job_payroll_id ON outworker_payroll_job (payroll_id)')
            connection.exec_driver_sql('CREATE INDEX ix_outworker_payroll_job_jobcard_id ON outworker_payroll_job (jobcard_id)')
            connection.commit()
        except Exception:
            connection.rollback()
            raise
