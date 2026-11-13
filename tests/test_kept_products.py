"""Retained stock is payable work, never fake returned stock or a cash payment."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from support import AppTestCase
from modes import db, User, Jobcard, Jobmovement, JobKeptProduct, OutworkerAdvance, RequestDedup
from kept_products import record_kept_product, save_product_value
from data_entry import add_manual_jobcard, in_move_entery, RequestConflict
from data_Process import get_jobcard_return_data, get_jobcard_ledger, outworker_period_account
from payroll_service import (save_rate, payroll_preview, issue_payroll, payable_job_quotes,
                             advance_balance, payment_account, browser_payroll_snapshot, advance_entries)
from return_workspace import open_outworker_jobs
from simple_workflow import job_overview, weekly_job_overview, dashboard_movement_details
from schema_updates import ensure_product_value


class KeptProductsTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config['SIMPLE_WORKFLOW'] = True
        save_product_value(self.product.id, '120', 0, 'value', self.admin)
        save_rate(self.product.id, '', '5.5', 'new', 'rate', self.admin)

    def card(self, returned=48):
        card_id = add_manual_jobcard(self.manual_payload(pieces=50, count=1), self.admin, 'job')['jobData']['jobId']
        if returned:
            self.assertEqual(in_move_entery(self.return_payload(card_id, returned), self.admin, 'return')['code'], 101)
        return card_id

    def keep(self, card_id, quantity=2, token='keep', remaining=2, value=12000, **changes):
        args = dict(card_id=card_id, product_id=self.product.id, bundle_type='lump', quantity=quantity,
                    expected_value=value, expected_remaining=remaining, confirmed='yes', note='Retained by agreement',
                    token=token, user=self.admin)
        args.update(changes)
        return record_kept_product(**args)

    def pay(self, card_id, token, deduction='0'):
        preview = payroll_preview(self.worker.id, [card_id], deduction)
        return issue_payroll(self.worker.id, [card_id], deduction, preview['version'], 'Cash', '', '', token, self.admin)

    def test_48_returned_2_kept_pays_50_and_recovers_240(self):
        card_id = self.card()
        row = self.keep(card_id)
        self.assertEqual((row.pieces, row.unit_value_paise, row.amount_paise), (2, 12000, 24000))
        advance = db.session.get(OutworkerAdvance, row.advance_id)
        self.assertEqual((advance.amount_paise, advance.worker_id), (24000, self.worker.id))
        self.assertIn(f'Job #{card_id}', advance.reference)
        self.assertEqual(sum(m.inflow for m in Jobmovement.query.all()), 48)
        self.assertEqual(Jobmovement.query.filter_by(flow_type='IN').count(), 1)
        self.assertEqual(get_jobcard_return_data(card_id)['items'], [])
        job = get_jobcard_ledger(card_id)['job']
        self.assertEqual((job['given'], job['returned'], job['kept'], job['remaining'], job['status']), (50,48,2,0,'Complete'))
        self.assertEqual(job['last_activity'],row.date)
        self.assertEqual(job['ledger'][-1]['flow_type'], 'KEPT')
        self.assertEqual(job['ledger'][-1]['balance'], 0)
        quote = payable_job_quotes(self.worker)[0]
        self.assertEqual((quote['pieces'], quote['returned'], quote['kept'], quote['pending_return']), (50,48,2,0))
        snapshot = browser_payroll_snapshot(self.worker, [quote], advance_entries(self.worker.id), 24000)
        self.assertEqual(snapshot['jobs'][0]['kept'], 2)
        payroll = self.pay(card_id, 'pay', 'available')
        self.assertEqual((payroll.gross_paise, payroll.deduction_paise, payroll.net_paise), (27500,24000,3500))
        self.assertEqual(advance_balance(self.worker.id), 0)
        self.assertEqual(payable_job_quotes(self.worker), [])
        self.assertEqual(get_jobcard_ledger(card_id)['job']['payment_status'],'paid')

    def test_previously_paid_returns_are_not_paid_again(self):
        card_id = self.card()
        self.assertEqual(self.pay(card_id, 'pay48').gross_paise, 26400)
        self.keep(card_id)
        quote = payable_job_quotes(self.worker)[0]
        self.assertEqual((quote['already_paid'], quote['pieces'], quote['gross_paise']), (48,2,1100))
        self.assertEqual(self.pay(card_id, 'pay2', 'available').net_paise, 0)
        self.assertEqual(advance_balance(self.worker.id), 22900)
        self.assertEqual(get_jobcard_ledger(card_id)['job']['paid_pieces'], 50)

    def test_recovery_can_be_carried_forward_without_automatic_deduction(self):
        card_id = self.card()
        self.keep(card_id)
        self.assertEqual(self.pay(card_id, 'pay').net_paise, 27500)
        self.assertEqual(advance_balance(self.worker.id), 24000)
        event = next(e for e in payment_account(self.worker.id)['events'] if e.get('product_kept'))
        self.assertEqual(event['net_paise'], 0, 'Kept stock must not be shown as cash given.')

    def test_retry_is_exactly_once_and_changed_retry_is_conflict(self):
        card_id = self.card()
        row_id = self.keep(card_id).id
        self.assertEqual(self.keep(card_id).id, row_id)
        with self.assertRaises(RequestConflict):
            self.keep(card_id, quantity=1)
        self.assertEqual(JobKeptProduct.query.count(), 1)
        self.assertEqual(OutworkerAdvance.query.count(), 1)

    def test_quantity_confirmation_price_and_stale_balance_validation(self):
        card_id = self.card()
        for changes in [dict(quantity=0), dict(quantity=-1), dict(quantity='1.5'), dict(quantity=True),
                        dict(quantity=3), dict(confirmed=None), dict(value=11999),
                        dict(remaining=3), dict(bundle_type='good_cut'), dict(product_id=999999)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.keep(card_id, **changes)
        self.assertEqual(JobKeptProduct.query.count(), 0)
        self.assertEqual(OutworkerAdvance.query.count(), 0)
        self.keep(card_id, quantity=1)
        self.assertEqual(get_jobcard_return_data(card_id)['items'][0]['issued'], 1)
        self.assertEqual(payable_job_quotes(self.worker)[0]['pieces'], 49)

    def test_price_snapshot_survives_later_product_value_changes(self):
        card_id = self.card()
        row = self.keep(card_id)
        save_product_value(self.product.id, '130', 12000, 'price2', self.admin)
        db.session.refresh(row)
        self.assertEqual((row.unit_value_paise, row.amount_paise), (12000,24000))

    def test_missing_price_and_excessive_recovery_are_rejected(self):
        card_id = self.card()
        save_product_value(self.product.id, '0', 12000, 'disable', self.admin)
        with self.assertRaises(ValueError):
            self.keep(card_id, value=0)
        save_product_value(self.product.id, '999999999.99', 0, 'large', self.admin)
        with self.assertRaises(ValueError):
            self.keep(card_id, value=99999999999)
        self.assertEqual(OutworkerAdvance.query.count(), 0)

    def test_commit_failure_rolls_back_kept_advance_claim_and_log(self):
        card_id = self.card()
        count = RequestDedup.query.count()
        with patch('kept_products.db.session.commit', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                self.keep(card_id)
        self.assertEqual((JobKeptProduct.query.count(), OutworkerAdvance.query.count(), RequestDedup.query.count()), (0,0,count))
        self.keep(card_id)
        self.assertEqual(OutworkerAdvance.query.count(), 1)

    def test_concurrent_distinct_kept_requests_cannot_charge_twice(self):
        card_id = self.card()
        product_id, auth_id = self.product.id, self.admin.get_id()
        gate = Barrier(2)
        def submit(index):
            with self.app.app_context():
                user = User.query.filter_by(auth_id=auth_id).one()
                gate.wait(timeout=10)
                try:
                    record_kept_product(card_id, product_id, 'lump', 2, 12000, 2, 'yes', '', f'keep-{index}', user)
                    return 'saved'
                except ValueError:
                    return 'rejected'
                finally:
                    db.session.remove()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        self.assertCountEqual(results, ['saved', 'rejected'])
        self.assertEqual((JobKeptProduct.query.count(), OutworkerAdvance.query.count()), (1,1))

    def test_reports_close_job_and_keep_physical_inflow_separate(self):
        card_id = self.card()
        self.keep(card_id)
        today = datetime.now().date()
        overview = job_overview()
        self.assertEqual((overview['given'], overview['returned'], overview['kept'], overview['pending'], overview['open_jobs']), (50,48,2,0,0))
        self.assertEqual(open_outworker_jobs(self.worker), [])
        period = outworker_period_account(self.worker_name, today, today)['totals']
        self.assertEqual((period['given'], period['returned'], period['kept'], period['closing'], period['pieces_left']), (50,48,2,0,0))
        week = weekly_job_overview(date_from=today, date_to=today)
        self.assertEqual((week['given'], week['returned'], week['kept'], week['closing']), (50,48,2,0))
        details = dashboard_movement_details(week, 'all')
        self.assertEqual(details[-1]['balance'], 0)
        self.assertEqual(details[-1]['kept'], 2)
        tomorrow = outworker_period_account(self.worker_name, today + timedelta(days=1), today + timedelta(days=1))['totals']
        self.assertEqual((tomorrow['opening'], tomorrow['closing']), (0,0))
        for path in [f'/job_retun?jobcard_id={card_id}', f'/jobcard/{card_id}/ledger',
                     f'/payroll?worker_id={self.worker.id}', '/admin_dashord',
                     '/dashboard/movements?kind=all']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)

    def test_return_and_kept_race_cannot_consume_same_remaining_pieces(self):
        card_id = self.card()
        payload = self.return_payload(card_id, 2, key='racing-return')
        product_id, auth_id = self.product.id, self.admin.get_id()
        gate = Barrier(2)
        def submit(kind):
            with self.app.app_context():
                user = User.query.filter_by(auth_id=auth_id).one()
                gate.wait(timeout=10)
                try:
                    if kind == 'return':
                        return in_move_entery(payload, user, 'racing-return')
                    return record_kept_product(card_id, product_id, 'lump', 2, 12000, 2, 'yes', '', 'racing-keep', user).id
                except ValueError:
                    return 'rejected'
                finally:
                    db.session.remove()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(submit, ['return', 'keep']))
        physical = sum(row.inflow for row in Jobmovement.query.filter_by(flow_type='IN').all())
        kept = sum(row.pieces for row in JobKeptProduct.query.all())
        self.assertEqual(physical + kept, 50)
        self.assertIn((physical, kept), [(48,2),(50,0)])
        self.assertEqual(OutworkerAdvance.query.count(), 1 if kept else 0)
        self.assertEqual(get_jobcard_ledger(card_id)['job']['remaining'], 0)

    def test_product_rename_preserves_kept_balance_and_payroll_link(self):
        card_id = self.card()
        self.keep(card_id)
        self.assertEqual(self.edit('product', self.product.id, {'name': 'RENAMED'})[0], 'saved')
        self.assertEqual(get_jobcard_return_data(card_id)['items'], [])
        quote = payable_job_quotes(self.worker)[0]
        self.assertEqual((quote['pieces'], quote['kept']), (50,2))
        self.assertEqual(quote['lines'][0]['product'], 'RENAMED')

    def test_kept_only_pieces_use_their_bundle_type_wage_rate(self):
        payload = self.manual_payload(pieces=30, count=1)
        payload['rows'].append(dict(product='VIM', type='good_cut', pieces=20, count=1))
        card_id = add_manual_jobcard(payload, self.admin, 'typed-job')['jobData']['jobId']
        save_rate(self.product.id, 'good_cut', '5.7', 'new', 'typed-rate', self.admin)
        self.keep(card_id, quantity=5, remaining=20, bundle_type='good_cut')
        quote = payable_job_quotes(self.worker)[0]
        self.assertEqual((quote['returned'], quote['kept'], quote['pieces'], quote['pending_return']), (0,5,5,45))
        self.assertEqual((quote['lines'][0]['type'], quote['gross_paise']), ('good_cut',2850))

    def test_future_dated_stock_cannot_be_kept_before_it_was_given(self):
        card_id = self.card()
        given = Jobmovement.query.filter_by(jobcard=str(card_id), flow_type='OUT').one()
        given.date = datetime.now() + timedelta(days=1)
        db.session.commit()
        with self.assertRaises(ValueError):
            self.keep(card_id)
        self.assertEqual(OutworkerAdvance.query.count(), 0)

    def legacy_return(self, quantity):
        row = Jobmovement(date=datetime.now(), jobcard=None, bundle=None, partculer='Historical return',
                          product_name=self.product.name, name_of_mater=self.worker_name, enter_user='admin',
                          type_B='lump', flow_type='IN', inflow=quantity)
        db.session.add(row)
        db.session.commit()
        return row

    def test_legacy_return_cannot_consume_pieces_already_kept(self):
        from return_reconciliation import matching_jobs, assign_return
        card_id = self.card()
        self.keep(card_id)
        legacy = self.legacy_return(2)
        self.assertEqual(matching_jobs(legacy), [])
        with self.assertRaises(ValueError):
            assign_return(legacy.id, card_id, self.admin)
        self.assertIsNone(db.session.get(Jobmovement, legacy.id).jobcard)
        self.assertEqual(get_jobcard_ledger(card_id)['job']['remaining'], 0)

    def test_legacy_return_can_consume_only_balance_after_partial_retention(self):
        from return_reconciliation import matching_jobs, assign_return
        card_id = self.card(returned=45)
        self.keep(card_id, remaining=5)
        legacy = self.legacy_return(3)
        self.assertEqual(matching_jobs(legacy)[0]['remaining'], 3)
        assign_return(legacy.id, card_id, self.admin)
        job = get_jobcard_ledger(card_id)['job']
        self.assertEqual((job['returned'],job['kept'],job['remaining']), (48,2,0))

    def test_http_price_setup_and_confirmed_keep(self):
        card_id = self.card()
        page = self.client.get(f'/job_retun?jobcard_id={card_id}')
        self.assertIn('Record pieces kept by outworker', page.get_data(as_text=True))
        response = self.client.post(f'/jobcard/{card_id}/kept', data=dict(product_id=self.product.id,
            bundle_type='lump', pieces='2', expected_value='12000', expected_remaining='2',
            confirmed='yes', note='Agreed', submission_token='http-keep'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(JobKeptProduct.query.one().amount_paise, 24000)
        self.assertIn('Record pieces kept by outworker', self.client.get(response.location).get_data(as_text=True))
        self.assertEqual(self.client.post('/payroll/rates', data=dict(action='product_value',
            product_id=self.product.id, product_value='125', expected_value='12000',
            submission_token='http-value')).status_code, 302)
        db.session.refresh(self.product)
        self.assertEqual(self.product.product_value_paise, 12500)

    def test_retained_job_cannot_be_edited_to_erase_recovery(self):
        from jobcard_edit import jobcard_edit_context
        card_id = self.card()
        self.keep(card_id)
        given = jobcard_edit_context(card_id)['given'][0]
        self.assertEqual(self.job_edit(card_id, {f'line_{given["id"]}_pieces':49})[0], 'invalid')
        html = self.client.get(f'/edit/jobcard/{card_id}').get_data(as_text=True)
        self.assertNotIn('class="edit-fields" disabled', html)
        self.assertIn('Pieces kept by outworker', html)

    def test_one_editor_updates_given_returns_kept_and_linked_debt_atomically(self):
        from jobcard_edit import jobcard_edit_context, save_jobcard_edit
        from modes import EditLog
        card_id = self.card()
        kept = self.keep(card_id)
        context = jobcard_edit_context(card_id)
        changes = {f'line_{context["given"][0]["id"]}_pieces':60,
                   f'line_{context["returns"][0]["id"]}_quantity':50,
                   f'kept_{kept.id}_pieces':4, f'kept_{kept.id}_value':'130.00',
                   f'kept_{kept.id}_note':'Corrected kept count and value'}
        with patch('jobcard_edit.save_jobcard_edit', wraps=save_jobcard_edit) as save:
            status, detail = self.job_edit(card_id, changes)
            original_request = save.call_args
        self.assertEqual(status,'saved',detail)
        db.session.expire_all()
        row = db.session.get(JobKeptProduct, kept.id)
        self.assertEqual((row.pieces,row.unit_value_paise,row.amount_paise),(4,13000,52000))
        self.assertEqual(db.session.get(OutworkerAdvance,row.advance_id).amount_paise,52000)
        quote = payable_job_quotes(self.worker)[0]
        self.assertEqual((quote['returned'],quote['kept'],quote['pending_return']),(50,4,6))
        log = EditLog.query.filter_by(entity_type='jobcard',entity_id=card_id).one()
        self.assertIn('kept_and_recoveries',log.changed_fields)
        self.assertEqual(log.old_values['kept'][0]['pieces'],2)
        self.assertEqual(log.new_values['kept'][0]['pieces'],4)
        self.assertEqual(save_jobcard_edit(*original_request.args, **original_request.kwargs)[0],'duplicate')
        self.assertEqual(OutworkerAdvance.query.count(),1)

    def test_invalid_kept_correction_rolls_back_movements_and_debt(self):
        from jobcard_edit import jobcard_edit_context
        card_id = self.card()
        kept = self.keep(card_id)
        returned = jobcard_edit_context(card_id)['returns'][0]
        changes = {f'line_{returned["id"]}_quantity':49, f'kept_{kept.id}_pieces':3}
        self.assertEqual(self.job_edit(card_id,changes)[0],'invalid')
        db.session.expire_all()
        self.assertEqual(Jobmovement.query.filter_by(flow_type='IN').one().inflow,48)
        self.assertEqual(db.session.get(JobKeptProduct,kept.id).pieces,2)
        self.assertEqual(OutworkerAdvance.query.one().amount_paise,24000)

    def test_new_kept_entry_invalidates_existing_edit_snapshot(self):
        from jobcard_edit import jobcard_edit_context
        card_id = self.card()
        version = jobcard_edit_context(card_id)['version']
        self.keep(card_id)
        self.assertEqual(self.job_edit(card_id,version=version)[0],'conflict')

    def test_collected_recovery_locks_editor_and_invalidates_old_snapshot(self):
        from jobcard_edit import jobcard_edit_context
        from payroll_service import receive_advance
        card_id = self.card()
        kept = self.keep(card_id)
        version = jobcard_edit_context(card_id)['version']
        receive_advance(self.worker.id, kept.advance_id, '10', '24000', 'Cash', '', '', 'recover', self.admin)
        self.assertEqual(self.job_edit(card_id,version=version)[0],'conflict')
        self.assertEqual(self.job_edit(card_id,token='locked-correction')[0],'invalid')
        html = self.client.get(f'/edit/jobcard/{card_id}').get_data(as_text=True)
        self.assertIn('class="edit-fields" disabled',html)
        self.assertEqual(OutworkerAdvance.query.one().amount_paise,24000)

    def test_kept_corrections_reject_zero_and_before_given_dates(self):
        card_id = self.card()
        kept = self.keep(card_id)
        for index,change in enumerate(({f'kept_{kept.id}_pieces':0},
                                       {f'kept_{kept.id}_value':'0'},
                                       {f'kept_{kept.id}_date':'2000-01-01T00:00:00'})):
            self.assertEqual(self.job_edit(card_id,change,token=f'invalid-kept-{index}')[0],'invalid')
        self.assertEqual(OutworkerAdvance.query.one().amount_paise,24000)

    def test_kept_job_worker_change_moves_its_unrecovered_debt(self):
        from modes import Outworker
        from payroll_service import worker_label
        card_id = self.card()
        kept = self.keep(card_id)
        other = Outworker(name='OTHER',adders='CITY',number=99,enter_user='admin')
        db.session.add(other)
        db.session.commit()
        self.assertEqual(self.job_edit(card_id,{'given_to':worker_label(other)})[0],'saved')
        db.session.expire_all()
        self.assertEqual(db.session.get(JobKeptProduct,kept.id).worker_id,other.id)
        self.assertEqual(advance_balance(self.worker.id),0)
        self.assertEqual(advance_balance(other.id),24000)

    def test_product_value_upgrade_is_additive_and_idempotent(self):
        engine = create_engine('sqlite:///:memory:')
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql('CREATE TABLE ItemData(id INTEGER PRIMARY KEY, name TEXT)')
                connection.exec_driver_sql("INSERT INTO ItemData VALUES(1,'OLD')")
            ensure_product_value(engine)
            ensure_product_value(engine)
            with engine.connect() as connection:
                self.assertEqual(tuple(connection.exec_driver_sql('SELECT * FROM ItemData').one()), (1,'OLD',0))
        finally:
            engine.dispose()
