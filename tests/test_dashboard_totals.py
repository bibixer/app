"""Dashboard piece totals cover all history and preserve per-job shortages."""

from datetime import datetime

from data_entry import add_manual_jobcard, in_move_entery
from modes import db, Item_data, Jobmovement
from simple_workflow import job_overview
from support import AppTestCase


class DashboardTotalsTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config['SIMPLE_WORKFLOW'] = True

    def job(self, product='VIM', pieces=10, returned=0, kind='lump', key='job'):
        data = self.manual_payload(product=product, pieces=pieces, count=1)
        data['rows'][0]['type'] = kind
        card_id = add_manual_jobcard(data, self.admin, key)['jobData']['jobId']
        if returned:
            result = in_move_entery(self.return_payload(card_id, returned), self.admin, f'{key}-return')
            self.assertEqual(result['code'], 101)
        return card_id

    def test_all_time_and_product_totals_include_types_and_canonical_product_names(self):
        other = Item_data(name='SECOND PRODUCT', size=0, meters=0, enter_user='admin')
        unused = Item_data(name='UNUSED PRODUCT', size=0, meters=0, enter_user='admin')
        db.session.add_all([other, unused])
        db.session.commit()
        self.job(returned=5, key='first')
        self.job(pieces=8, kind='good_cut', key='second')
        self.job(product=other.name, pieces=20, returned=6, key='third')
        report = job_overview()
        self.assertEqual((report['given'], report['returned'], report['pending']), (38, 11, 27))
        products = {row['name']: row for row in report['product_totals']}
        self.assertNotIn('VIM', products)
        self.assertEqual(products[self.product.name], {'name': self.product.name, 'given': 18, 'returned': 5, 'pending': 13})
        self.assertEqual(products[other.name], {'name': other.name, 'given': 20, 'returned': 6, 'pending': 14})
        self.assertEqual(products[unused.name]['given'], 0)
        response = self.client.get('/admin_dashord')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        for text in ('Total outflow', 'Total inflow', 'Product-wise period account',
                     'Grand total · all products', other.name, unused.name):
            self.assertIn(text, html)

    def test_totals_cover_more_than_twenty_recent_cards(self):
        for index in range(21):
            self.job(pieces=2, returned=1, key=f'history-{index}')
        report = job_overview()
        self.assertEqual(len(report['recent']), 20)
        self.assertEqual((report['jobs'], report['given'], report['returned'], report['pending']), (21, 42, 21, 21))

    def test_legacy_unlinked_movements_are_included_in_all_piece_totals(self):
        self.job(returned=5)
        db.session.add(Jobmovement(
            date=datetime(2025, 1, 1), jobcard=None, partculer='Legacy return',
            product_name=self.product.name, name_of_mater=self.worker_name,
            enter_user='admin', type_B='lump', flow_type='IN', outflow=0, inflow=3,
        ))
        db.session.commit()
        report = job_overview()
        self.assertEqual((report['given'], report['returned'], report['pending']), (10, 8, 5))
        self.assertEqual(report['unlinked'], {'given': 0, 'returned': 3})
        self.assertIn('Balance b/f', self.client.get('/admin_dashord').get_data(as_text=True))

    def test_extra_return_on_one_job_does_not_hide_another_job_shortage(self):
        first = self.job(key='first')
        self.job(key='second')
        # Simulate an older, inconsistent record that current return validation rejects.
        db.session.add(Jobmovement(
            date=datetime.now(), jobcard=str(first), partculer='Older return',
            product_name=self.product.name, name_of_mater=self.worker_name,
            enter_user='admin', type_B='lump', flow_type='IN', outflow=0, inflow=12,
        ))
        db.session.commit()
        report = job_overview()
        self.assertEqual((report['given'], report['returned'], report['pending']), (20, 12, 10))
        self.assertEqual(report['product_totals'][0]['pending'], 10)
        self.assertEqual(report['open_jobs'], 1)
