"""Existing receipts survive the partial-payroll SQLite upgrade and failed upgrades."""

import unittest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from schema_updates import allow_job_payment_installments


class PayrollSchemaUpgradeTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            connection.exec_driver_sql('CREATE TABLE outworker_payroll (id INTEGER PRIMARY KEY)')
            connection.exec_driver_sql('CREATE TABLE "JobcardData" (id INTEGER PRIMARY KEY)')
            connection.exec_driver_sql('INSERT INTO outworker_payroll VALUES (1), (2)')
            connection.exec_driver_sql('INSERT INTO "JobcardData" VALUES (7)')
            connection.exec_driver_sql('''CREATE TABLE outworker_payroll_job (
                id INTEGER PRIMARY KEY, payroll_id INTEGER NOT NULL REFERENCES outworker_payroll(id),
                jobcard_id INTEGER NOT NULL UNIQUE REFERENCES "JobcardData"(id),
                pieces INTEGER NOT NULL, amount_paise BIGINT NOT NULL, lines JSON NOT NULL)''')
            connection.exec_driver_sql('CREATE INDEX ix_outworker_payroll_job_payroll_id ON outworker_payroll_job (payroll_id)')
            connection.exec_driver_sql('INSERT INTO outworker_payroll_job VALUES (1, 1, 7, 5, 2750, ?)',
                                       ('[{"product_id":1,"product":"VIMAL","type":"lump","pieces":5,"rate":"5.5"}]',))

    def test_upgrade_preserves_rows_and_allows_another_payment_for_same_job(self):
        with self.engine.connect() as connection:
            original = connection.exec_driver_sql('SELECT * FROM outworker_payroll_job').all()
        allow_job_payment_installments(self.engine)
        allow_job_payment_installments(self.engine)
        with self.engine.begin() as connection:
            self.assertEqual(connection.exec_driver_sql('SELECT * FROM outworker_payroll_job').all(), original)
            connection.exec_driver_sql('INSERT INTO outworker_payroll_job VALUES (2, 2, 7, 5, 2750, ?)', (original[0][-1],))
            self.assertEqual(connection.exec_driver_sql('SELECT sum(pieces) FROM outworker_payroll_job').scalar(), 10)
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.exec_driver_sql('INSERT INTO outworker_payroll_job VALUES (3, 2, 7, 5, 2750, ?)', (original[0][-1],))

    def test_failed_upgrade_rolls_back_ddl_and_keeps_original_receipt(self):
        def fail_rename(connection, cursor, statement, parameters, context, many):
            if statement.startswith('ALTER TABLE'):
                raise RuntimeError('simulated upgrade failure')
        event.listen(self.engine, 'before_cursor_execute', fail_rename)
        try:
            with self.assertRaises(RuntimeError):
                allow_job_payment_installments(self.engine)
        finally:
            event.remove(self.engine, 'before_cursor_execute', fail_rename)
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql('SELECT pieces FROM outworker_payroll_job').scalar(), 5)
            self.assertNotIn('outworker_payroll_job_installments', inspect(connection).get_table_names())
            self.assertTrue(any(row['column_names'] == ['jobcard_id']
                                for row in inspect(connection).get_unique_constraints('outworker_payroll_job')))
