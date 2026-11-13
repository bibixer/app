"""Write-lock failures are retryable and do not consume submission tokens."""
import sqlite3
from contextlib import ExitStack
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, TimeoutError as PoolTimeout

from database_writes import DatabaseBusy, begin_write
from data_entry import add_manual_jobcard
from modes import db, Item_data, Jobcard, RequestDedup
from support import AppTestCase


class DatabaseContentionTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config['SIMPLE_WORKFLOW'] = True

    def test_both_sqlite_databases_use_wal_and_wait_for_writers(self):
        for engine in db.engines.values():
            with engine.connect() as connection:
                self.assertEqual(connection.exec_driver_sql('PRAGMA journal_mode').scalar(), 'wal')
                self.assertEqual(connection.exec_driver_sql('PRAGMA busy_timeout').scalar(), 60000)

    def test_both_pools_can_support_32_handlers_without_cross_pool_starvation(self):
        with ExitStack() as stack:
            for _ in range(32):
                for engine in db.engines.values():
                    connection = stack.enter_context(engine.connect())
                    self.assertEqual(connection.exec_driver_sql('SELECT 1').scalar(), 1)

    def test_real_lock_timeout_leaves_key_available_for_retry(self):
        db.session.remove()
        with db.engine.connect() as owner:
            owner.exec_driver_sql('BEGIN IMMEDIATE')
            db.session.execute(text('PRAGMA busy_timeout=20'))
            try:
                with self.assertRaises(DatabaseBusy):
                    begin_write(RequestDedup)
                self.assertEqual(RequestDedup.query.count(), 0)
            finally:
                owner.rollback()
        # The same submission succeeds once the external writer releases its lock.
        response = self.client.post('/submit-manual-jobcard', json=self.manual_payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Jobcard.query.count(), 1)
        self.assertTrue(self.client.post('/submit-manual-jobcard', json=self.manual_payload()).json['duplicate'])

    def test_api_busy_response_is_503_and_can_be_retried_without_duplicates(self):
        error = OperationalError('BEGIN IMMEDIATE', {}, sqlite3.OperationalError('database is locked'))
        with patch('database_writes.db.session.execute', side_effect=error):
            response = self.client.post('/submit-manual-jobcard', json=self.manual_payload())
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json['retryable'])
        self.assertFalse(response.json['success'])
        self.assertEqual(response.headers['Retry-After'], '2')
        self.assertEqual(RequestDedup.query.count(), 0)
        self.assertEqual(self.client.post('/submit-manual-jobcard', json=self.manual_payload()).status_code, 200)
        self.assertEqual(Jobcard.query.count(), 1)

    def test_form_busy_error_does_not_blame_duplicate_names(self):
        data = dict(name='LOCK TEST', aliases='', submission_token='same-product')
        with patch('data_entry.begin_write', side_effect=DatabaseBusy('busy')):
            response = self.client.post('/add_items', data=data)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('duplicate name or alias', response.get_data(as_text=True))
        self.assertIsNone(Item_data.query.filter_by(name='LOCK TEST').first())
        self.assertEqual(self.client.post('/add_items', data=data).status_code, 302)
        self.assertEqual(Item_data.query.filter_by(name='LOCK TEST').count(), 1)

    def test_busy_page_renders_even_when_user_database_cannot_load(self):
        user_id = self.admin.get_id()
        with patch('sqlalchemy.orm.query.Query.first', side_effect=PoolTimeout('pool exhausted')):
            response = self.client.post('/add_items', data={})
        self.assertEqual(response.status_code, 503)
        self.assertIn('Save needs a retry', response.get_data(as_text=True))
        with self.client.session_transaction() as session:
            self.assertEqual(session['_user_id'], user_id)
        self.assertEqual(self.client.get('/manual_jobcard').status_code, 200)

    def test_flushed_caller_corrections_stay_atomic_with_next_save(self):
        first = add_manual_jobcard(self.manual_payload(), self.admin, 'first')['jobData']['jobId']
        original = db.session.get(Jobcard, first)
        corrected = datetime(2026, 11, 1)
        original.date = corrected
        db.session.flush()
        add_manual_jobcard(self.manual_payload(key='second'), self.admin, 'second')
        db.session.expire_all()
        self.assertEqual(db.session.get(Jobcard, first).date, corrected)

    def test_completed_retry_does_not_wait_for_an_unrelated_writer(self):
        payload = self.manual_payload()
        first = self.client.post('/submit-manual-jobcard', json=payload).json
        db.session.remove()
        with db.engine.connect() as owner:
            owner.exec_driver_sql('BEGIN IMMEDIATE')
            db.session.execute(text('PRAGMA busy_timeout=20'))
            try:
                with patch('data_entry.begin_write', side_effect=AssertionError('Replay must not acquire a writer lock')):
                    response = self.client.post('/submit-manual-jobcard', json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json['duplicate'])
                self.assertEqual(response.json['jobData'], first['jobData'])
            finally:
                owner.rollback()
        self.assertEqual(Jobcard.query.count(), 1)
