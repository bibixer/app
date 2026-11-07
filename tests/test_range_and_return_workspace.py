"""Exact dashboard ranges, ledger detail, worker returns and manual label output."""

import csv
from datetime import datetime, date
from pathlib import Path
from unittest.mock import patch

from data_entry import add_manual_jobcard, in_move_entery
from data_print_format import job_cade_print
from modes import db, Jobcard, Jobmovement, Outworker, ReturnBreakdown
from return_workspace import open_outworker_jobs
from simple_workflow import dashboard_period, dashboard_movement_details
from support import AppTestCase


class RangeAndReturnWorkspaceTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config['SIMPLE_WORKFLOW'] = True

    def card(self, pieces=10, returned=0, key='job'):
        card_id = add_manual_jobcard(self.manual_payload(pieces=pieces,count=1),self.admin,key)['jobData']['jobId']
        if returned:
            self.assertEqual(in_move_entery(self.return_payload(card_id,returned),self.admin,f'{key}-return')['code'],101)
        return db.session.get(Jobcard,card_id)

    def test_exact_range_opening_closing_and_full_movement_details(self):
        card = self.card(pieces=100,returned=20)
        movements = Jobmovement.query.order_by(Jobmovement.id).all()
        movements[0].date = datetime(2026,11,1)
        movements[1].date = datetime(2026,11,4,23,59,59)
        card.date = datetime(2026,11,1)
        second = self.card(pieces=50,returned=10,key='second')
        movements = Jobmovement.query.filter_by(jobcard=str(second.id)).order_by(Jobmovement.id).all()
        movements[0].date = datetime(2026,11,6)
        movements[1].date = datetime(2026,11,8,23,59,59,999999)
        second.date = datetime(2026,11,6)
        breakdown = ReturnBreakdown.query.filter_by(movement_id=movements[1].id).one()
        breakdown.entry_method = 'calculator'
        breakdown.calculation_rows = [{'pieces':5,'count':2}]
        db.session.commit()
        report = dashboard_period({'date_from':'2026-11-05','date_to':'2026-11-08'})
        self.assertEqual((report['opening'],report['given'],report['returned'],report['closing']),(80,50,10,120))
        self.assertEqual([row[0].id for row in report['recent']],[second.id])
        self.assertEqual(len(dashboard_movement_details(report,'opening')),2)
        self.assertEqual(len(dashboard_movement_details(report,'closing')),4)
        self.assertEqual(sum(row['given'] for row in dashboard_movement_details(report,'given')),50)
        args={'date_from':'2026-11-05','date_to':'2026-11-08'}
        html=self.client.get('/admin_dashord',query_string=args).get_data(as_text=True)
        self.assertIn('name="date_from"',html)
        self.assertIn('name="date_to"',html)
        self.assertIn('Open Balance b/f details in a new tab',html)
        self.assertIn('target="_blank"',html)
        args['kind']='returned'
        response=self.client.get('/dashboard/movements',query_string=args)
        self.assertEqual(response.status_code,200)
        self.assertIn('5 × 2 = 10',response.get_data(as_text=True))
        self.assertIn(f'#{second.id}',response.get_data(as_text=True))
        self.login_as(self.operator)
        self.assertEqual(self.client.get('/dashboard/movements',query_string=args).status_code,302)

    def test_invalid_ranges_are_rejected_without_server_errors(self):
        for args in ({'date_from':'2026-11-09','date_to':'2026-11-01'},
                     {'date_from':'2026-11-01'}, {'date_to':'2026-11-01'},
                     {'date_from':'bad','date_to':'2026-11-01'}):
            self.assertEqual(self.client.get('/admin_dashord',query_string=args).status_code,302)
            self.assertEqual(self.client.get('/dashboard/movements',query_string=args).status_code,302)

    def test_worker_workspace_includes_only_that_workers_incomplete_jobs(self):
        first=self.card(returned=3,key='first')
        second=self.card(pieces=20,key='second')
        complete=self.card(returned=10,key='complete')
        other=Outworker(name='OTHER',adders='CITY',number=55,enter_user='admin')
        db.session.add(other)
        db.session.commit()
        another=self.card(key='another')
        another.given_to=f'{other.id}***{other.name}--{other.adders}/-'
        for row in Jobmovement.query.filter_by(jobcard=str(another.id)):
            row.name_of_mater=another.given_to
        db.session.commit()
        jobs=open_outworker_jobs(self.worker)
        self.assertEqual({job['card'].id for job in jobs},{first.id,second.id})
        self.assertEqual(sum(job['pending'] for job in jobs),27)
        self.login_as(self.operator)
        response=self.client.get('/returns/outworker?worker=RAM+CITY')
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        self.assertIn(f'data-job-id="{first.id}"',html)
        self.assertIn(f'data-job-id="{second.id}"',html)
        self.assertNotIn(f'data-job-id="{complete.id}"',html)
        self.assertNotIn(f'data-job-id="{another.id}"',html)
        embedded=self.client.get(f'/job_retun?jobcard_id={first.id}&embedded=1').get_data(as_text=True)
        self.assertNotIn('aria-label="Main navigation"',embedded)
        self.assertIn('Quick Calc',embedded)
        self.assertIn('RETURN_EMBEDDED = true',embedded)
        self.assertIn('Open all incomplete jobs',self.client.get('/retune_product').get_data(as_text=True))

    def test_outworker_accounts_payroll_link_preserves_selected_worker(self):
        self.card()
        response=self.client.post('/outworker_report',data={'name':self.worker_name,
                                  'date_from':'2026-01-01','date_to':'2027-01-01'})
        self.assertEqual(response.status_code,200)
        self.assertIn(f'href="/payroll?worker_id={self.worker.id}"',response.get_data(as_text=True))
        response=self.client.get(f'/payroll?worker_id={self.worker.id}')
        self.assertEqual(response.status_code,200)
        self.assertIn(self.worker.name,response.get_data(as_text=True))

    def test_manual_save_publishes_existing_csv_format_once_in_configured_folder(self):
        root=Path(self.temp.name)/'configured-labels'
        self.app.config['LABEL_PRINT_ROOT']=str(root)
        payload=self.manual_payload(pieces=36,count=2)
        with patch('data_entry.job_cade_print',wraps=job_cade_print) as printer:
            response=self.client.post('/submit-manual-jobcard',json=payload)
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.json['print_warning'])
            files=list((root/'jobcard').glob('*.csv'))
            self.assertEqual(len(files),1)
            with files[0].open(newline='') as source:
                row=next(csv.DictReader(source))
            self.assertEqual((row['Product_1'],row['Pattern_1_line1'],row['Total_1']),
                             (self.product.name,'36x2','72'))
            self.assertIn(files[0].name,response.json['label_csvs'])
            self.assertTrue(self.client.post('/submit-manual-jobcard',json=payload).json['duplicate'])
            printer.assert_called_once()
            self.assertEqual(len(list((root/'jobcard').iterdir())),1)

    def test_export_failure_does_not_lose_job_or_allow_duplicate_job(self):
        self.job_cade_print.side_effect=OSError('folder unavailable')
        payload=self.manual_payload()
        with self.assertLogs(level='ERROR'):
            response=self.client.post('/submit-manual-jobcard',json=payload)
        self.assertTrue(response.json['success'])
        self.assertIn('CSV export failed',response.json['print_warning'])
        self.assertTrue(self.client.post('/submit-manual-jobcard',json=payload).json['duplicate'])
        self.assertEqual(Jobcard.query.count(),1)
        self.job_cade_print.assert_called_once()
