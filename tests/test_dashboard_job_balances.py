"""Historical carried balances, worker drilldowns, product filters and ageing."""
from datetime import datetime

from support import AppTestCase
from data_entry import add_manual_jobcard, in_move_entery
from kept_products import record_kept_product, save_product_value
from modes import db, Jobcard, Jobmovement, Outworker, Item_data
from payroll_service import worker_label
from simple_workflow import dashboard_period, dashboard_movement_details, dashboard_job_balances


class DashboardJobBalancesTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config['SIMPLE_WORKFLOW']=True
        self.args={'date_from':'2026-11-11','date_to':'2026-11-17'}

    def card(self,key,pieces=178,returned=149,issued='2026-11-08',product=None,worker=None):
        payload=self.manual_payload(pieces=pieces,count=1,product=product or self.product.name)
        if worker:
            payload['customer']=worker_label(worker)
        card_id=add_manual_jobcard(payload,self.admin,key)['jobData']['jobId']
        if returned:
            in_move_entery(self.return_payload(card_id,returned),self.admin,key+'-return')
        card=db.session.get(Jobcard,card_id)
        card.date=datetime.fromisoformat(issued)
        for row in Jobmovement.query.filter_by(jobcard=str(card_id)):
            row.date=card.date if row.flow_type=='OUT' else datetime(2026,11,9)
        db.session.commit()
        return card_id

    def balance(self,kind='opening',**options):
        report=dashboard_period(self.args)
        entries=dashboard_movement_details(report,kind)
        return dashboard_job_balances(report,kind,entries,**options)

    def test_opening_uses_historical_returns_kept_and_age_not_live_balance(self):
        card_id=self.card('example')
        save_product_value(self.product.id,'120',0,'price',self.admin)
        kept=record_kept_product(card_id,self.product.id,'lump',4,12000,29,'yes','','keep',self.admin)
        kept.date=datetime(2026,11,10)
        db.session.commit()
        in_move_entery(self.return_payload(card_id,5),self.admin,'later-return')
        Jobmovement.query.filter_by(jobcard=str(card_id),flow_type='IN').order_by(Jobmovement.id.desc()).first().date=datetime(2026,11,12)
        db.session.commit()
        opening=self.balance()
        row=opening['jobs'][0]
        self.assertEqual((row['given'],row['returned'],row['kept'],row['pieces_left'],row['age_days']),(178,149,4,25,3))
        self.assertEqual(opening['workers'][0]['pieces_left'],25)
        self.assertEqual(opening['products'][0]['remaining'],25)
        self.assertEqual(self.balance('closing')['jobs'][0]['pieces_left'],20)
        self.assertEqual(self.balance('returned')['jobs'][0]['returned'],154)

    def test_completed_jobs_are_not_in_carried_balance_and_age_sorts(self):
        recent=self.card('recent',pieces=30,returned=0)
        old=self.card('old',pieces=20,returned=0,issued='2026-11-01')
        complete=self.card('complete',pieces=10,returned=10)
        self.assertEqual([row['card'].id for row in self.balance()['jobs']],[old,recent])
        self.assertEqual([row['card'].id for row in self.balance(sort_by='age_asc')['jobs']],[recent,old])
        self.assertEqual([row['card'].id for row in self.balance(sort_by='quantity_desc')['jobs']],[recent,old])
        self.assertEqual([row['card'].id for row in self.balance(sort_by='quantity_asc')['jobs']],[old,recent])
        self.assertNotIn(complete,[row['card'].id for row in self.balance()['jobs']])
        self.assertEqual(self.balance()['workers'][0]['age_days'],10)

    def test_product_filter_worker_groups_and_product_sort(self):
        first=self.card('vimal',pieces=20,returned=0)
        product=Item_data(name='AAA PRODUCT',size=2,meters=1,enter_user='admin')
        other=Outworker(name='OTHER',adders='CITY',number=9,enter_user='admin')
        db.session.add_all([product,other])
        db.session.commit()
        second=self.card('aaa',pieces=40,returned=0,product=product.name,worker=other)
        result=self.balance(sort_by='product')
        self.assertEqual([row['card'].id for row in result['jobs']],[second,first])
        result=self.balance(sort_by='quantity_desc')
        self.assertEqual(result['workers'][0]['worker_id'],other.id)
        result=self.balance(product_filter='vImAl')
        self.assertEqual([row['card'].id for row in result['jobs']],[first])
        self.assertEqual(result['totals']['pieces_left'],20)
        self.assertEqual(len(result['workers']),1)
        self.assertEqual(self.balance(product_filter='NOT FOUND')['jobs'],[])

    def test_unlinked_returns_do_not_disappear_or_hide_positive_job_balance(self):
        self.card('given',pieces=30,returned=0)
        db.session.add(Jobmovement(date=datetime(2026,11,10),jobcard=None,partculer='Older return',
            product_name=self.product.name,name_of_mater=self.worker_name,enter_user='admin',
            type_B='lump',flow_type='IN',inflow=5,outflow=0))
        db.session.commit()
        result=self.balance()
        self.assertEqual(len(result['unlinked']),1)
        self.assertEqual((result['totals']['remaining'],result['totals']['pieces_left']),(25,30))
        self.assertEqual(result['products'][0]['remaining'],25)
        html=self.client.get('/dashboard/movements',query_string={**self.args,'kind':'opening'}).get_data(as_text=True)
        self.assertIn('Unlinked movements need review',html)

    def test_both_views_edit_links_controls_and_permissions(self):
        card_id=self.card('http',pieces=30,returned=0)
        for view in ('workers','jobs'):
            response=self.client.get('/dashboard/movements',query_string={**self.args,'kind':'opening','view':view})
            self.assertEqual(response.status_code,200)
            html=response.get_data(as_text=True)
            self.assertIn(f'data-balance-job="{card_id}"',html)
            self.assertIn(f'href="/edit/jobcard/{card_id}"',html)
            self.assertIn('Product-wise balances',html)
            self.assertIn('Job age (days)',html)
            if view=='workers':
                self.assertIn('data-balance-worker=',html)
        self.login_as(self.operator)
        self.assertEqual(self.client.get('/dashboard/movements',query_string=self.args).status_code,302)

    def test_outflow_headers_distinguish_period_movements_from_job_totals(self):
        card_id=self.card('outflow-names',pieces=30,returned=0,issued='2026-11-12')
        response=self.client.get('/dashboard/movements',query_string={**self.args,'kind':'given','view':'jobs'})
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        for label in ('Job card / issue date','Outworker name','Job age (days)','Total given',
                      'Total returned','Kept by outworker','Pending pieces','Product-wise balances'):
            self.assertIn(label,html)
        self.assertIn('cumulative quantities, not just movements during the selected dates',html)
        self.assertIn(f'data-balance-job="{card_id}"',html)
