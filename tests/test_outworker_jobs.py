"""All-date job browsing, payment filters and direct edit links."""
import re
from datetime import datetime

from support import AppTestCase
from data_entry import add_manual_jobcard, in_move_entery
from data_Process import get_jobcard_ledger
from modes import db, Jobcard, Jobmovement, Outworker
from payroll_service import save_rate, payroll_preview, issue_payroll, worker_label


class OutworkerJobsTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config['SIMPLE_WORKFLOW'] = True
        save_rate(self.product.id,'','5.5','new','jobs-rate',self.admin)

    def card(self,key,returned=0,pay=False):
        card_id=add_manual_jobcard(self.manual_payload(pieces=10,count=1),self.admin,key)['jobData']['jobId']
        if returned:
            in_move_entery(self.return_payload(card_id,returned),self.admin,f'{key}-return')
        if pay:
            preview=payroll_preview(self.worker.id,[card_id],'0')
            issue_payroll(self.worker.id,[card_id],'0',preview['version'],'Cash','','',f'{key}-pay',self.admin)
        return card_id

    def jobs(self,**query):
        response=self.client.get('/outworker/jobs',query_string={'worker_id':self.worker.id,**query})
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        return {int(value) for value in re.findall(r'data-job-id="(\d+)"',html)},html

    def test_all_dates_completed_jobs_details_and_edit_links(self):
        old=self.card('old',returned=10)
        card=db.session.get(Jobcard,old)
        card.date=datetime(2020,1,1)
        Jobmovement.query.filter_by(jobcard=str(old),flow_type='OUT').one().date=card.date
        db.session.commit()
        new=self.card('new')
        ids,html=self.jobs()
        self.assertEqual(ids,{old,new})
        self.assertIn('2020',html)
        self.assertIn('Movement ledger',html)
        self.assertIn('Returns: 10 pieces',html)
        for card_id in ids:
            self.assertIn(f'href="/edit/jobcard/{card_id}"',html)
        self.assertIn('data-payment-status="unpaid"',html)
        _,alias_html=self.jobs(worker_id='',worker='RAM CITY')
        self.assertIn(f'data-job-id="{old}"',alias_html)

    def test_payment_status_and_ready_to_pay_filters(self):
        unpaid=self.card('unpaid')
        ready=self.card('ready',returned=10)
        partial=self.card('partial',returned=5,pay=True)
        paid=self.card('paid',returned=10,pay=True)
        self.assertEqual(self.jobs(payment_status='unpaid')[0],{unpaid,ready})
        self.assertEqual(self.jobs(payment_status='partial')[0],{partial})
        self.assertEqual(self.jobs(payment_status='paid')[0],{paid})
        self.assertEqual(self.jobs(payment_status='ready')[0],{ready})
        self.assertEqual(self.jobs(payment_status='invalid')[0],{unpaid,ready,partial,paid})
        job=get_jobcard_ledger(partial)['job']
        self.assertEqual((job['payment_status'],job['payable_pieces'],job['remaining']),('partial',0,5))
        self.assertIn('Fully paid',self.jobs(payment_status='paid')[1])
        self.assertIn('/payroll/',self.jobs(payment_status='paid')[1])

    def test_only_selected_outworkers_jobs_are_included(self):
        own=self.card('own')
        other_card=self.card('other')
        other=Outworker(name='OTHER',adders='CITY',number=9,enter_user='admin')
        db.session.add(other)
        db.session.flush()
        db.session.get(Jobcard,other_card).given_to=worker_label(other)
        for row in Jobmovement.query.filter_by(jobcard=str(other_card)):
            row.name_of_mater=worker_label(other)
        db.session.commit()
        self.assertEqual(self.jobs()[0],{own})

    def test_outworker_report_and_job_ledger_link_to_all_jobs_and_edits(self):
        card_id=self.card('links')
        response=self.client.post('/outworker_report',data={'name':self.worker_name,
            'date_from':'2000-01-01','date_to':'2099-12-31'})
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        self.assertIn(f'href="/outworker/jobs?worker_id={self.worker.id}"',html)
        self.assertIn(f'href="/edit/jobcard/{card_id}"',html)
        html=self.client.get(f'/jobcard/{card_id}/ledger').get_data(as_text=True)
        self.assertIn('/outworker/jobs?worker=',html)

    def test_empty_accounts_invalid_selection_and_access_control(self):
        self.assertEqual(self.client.get('/outworker/jobs').status_code,200)
        self.assertEqual(self.jobs()[0],set())
        self.assertEqual(self.client.get('/outworker/jobs?worker=NOT-FOUND').status_code,302)
        self.login_as(self.operator)
        self.assertEqual(self.client.get('/outworker/jobs?worker_id=1').status_code,302)
        self.client.get('/logout')
        self.assertEqual(self.client.get('/outworker/jobs?worker_id=1').status_code,302)
