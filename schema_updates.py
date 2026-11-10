"""Small, transactional upgrades for existing SQLite installations."""

from sqlalchemy import inspect


def ensure_user_active_column(engine):
    """Add account enable/disable state to existing user databases."""
    with engine.begin() as connection:
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
