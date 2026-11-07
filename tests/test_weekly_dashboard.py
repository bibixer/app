"""Weekly movements, carried balances, pie data, and job issue date boundaries."""

from datetime import date, datetime

from modes import db, Jobcard, Jobmovement, Item_data
from simple_workflow import weekly_job_overview
from support import AppTestCase


class WeeklyDashboardTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config['SIMPLE_WORKFLOW'] = True

    def card(self, issued):
        card = Jobcard(date=datetime.fromisoformat(issued), given_to=self.worker_name,
                       given_by='admin', product_list=[])
        db.session.add(card)
        db.session.flush()
        return card

    def movement(self, card, when, given=0, returned=0, product=None):
        db.session.add(Jobmovement(
            date=datetime.fromisoformat(when), jobcard=str(card.id) if card else None,
            product_name=product or self.product.name, type_B='lump', partculer='Test movement',
            name_of_mater=self.worker_name, enter_user='admin',
            flow_type='OUT' if given else 'IN', outflow=given, inflow=returned,
        ))

    def history(self):
        old = self.card('2026-11-01')
        self.movement(old, '2026-11-01', given=100)
        self.movement(old, '2026-11-03T23:59:59.999999', returned=20)
        self.movement(old, '2026-11-06', returned=30)
        issued = self.card('2026-11-05')
        self.movement(issued, '2026-11-05', given=50)
        self.movement(issued, '2026-11-08', returned=10)
        self.movement(issued, '2026-11-11', returned=20)
        db.session.commit()
        return old, issued

    def test_carry_forward_includes_old_jobs_but_only_current_week_movements(self):
        old, issued = self.history()
        report = weekly_job_overview(date(2026, 11, 8))
        self.assertEqual((report['week_start'], report['week_end']), (date(2026,11,4), date(2026,11,10)))
        self.assertEqual((report['opening'], report['given'], report['returned'], report['closing']), (80, 50, 40, 90))
        self.assertEqual([card.id for card, values in report['recent']], [issued.id])
        self.assertEqual(report['recent'][0][1], {'given': 50, 'returned': 10, 'pending': 40})
        next_week = weekly_job_overview(date(2026,11,11))
        self.assertEqual(next_week['opening'], report['closing'])
        self.assertEqual((next_week['given'], next_week['returned'], next_week['closing']), (0,20,70))
        self.assertEqual(next_week['jobs'], 0)

    def test_pies_split_products_and_single_product_uses_full_circle(self):
        self.history()
        first = weekly_job_overview(date(2026,11,4))
        self.assertTrue(first['inflow_pie']['slices'][0]['full'])
        other = Item_data(name='SECOND PRODUCT', size=0, meters=0, enter_user='admin')
        db.session.add(other)
        card = self.card('2026-11-06')
        self.movement(card, '2026-11-06', given=80, product=other.name)
        self.movement(card, '2026-11-09', returned=20, product=other.name)
        db.session.commit()
        report = weekly_job_overview(date(2026,11,4))
        self.assertEqual((report['outflow_pie']['total'], report['inflow_pie']['total']), (130,60))
        for field, pie in [('given','outflow_pie'), ('returned','inflow_pie')]:
            self.assertEqual(sum(row['quantity'] for row in report[pie]['slices']), report[field])
            self.assertEqual(len(report[pie]['slices']), 2)
        out_colors = {row['name']: row['color'] for row in report['outflow_pie']['slices']}
        self.assertEqual(out_colors, {row['name']:row['color'] for row in report['inflow_pie']['slices']})

    def test_exact_week_boundaries_and_empty_charts(self):
        card = self.card('2026-11-04T00:00:00')
        self.movement(card, '2026-11-04T00:00:00', given=10)
        self.movement(card, '2026-11-10T23:59:59.999999', returned=3)
        self.movement(card, '2026-11-11T00:00:00', returned=2)
        db.session.commit()
        report = weekly_job_overview(date(2026,11,10))
        self.assertEqual((report['given'],report['returned'],report['closing']), (10,3,7))
        empty = weekly_job_overview(date(2026,10,1))
        self.assertEqual(empty['inflow_pie'], {'total':0,'slices':[]})
        self.assertEqual(empty['outflow_pie'], {'total':0,'slices':[]})

    def test_week_selection_and_page_order_and_invalid_dates(self):
        self.history()
        response = self.client.get('/admin_dashord?week=2026-11-08')
        self.assertEqual(response.status_code,200)
        html = response.get_data(as_text=True)
        self.assertIn('04 Nov 2026',html)
        for label in ('Total outflow', 'Total inflow', 'Balance c/f', 'Balance b/f', 'Outflow by product','Inflow by product','Job issue data'):
            self.assertIn(label,html)
        self.assertLess(html.index('Outflow by product'),html.index('Job issue data'))
        self.assertIn('<circle cx="0" cy="0" r="90"',html)
        for invalid in ('bad','0001-01-01','9999-12-31'):
            self.assertEqual(self.client.get('/admin_dashord',query_string={'week':invalid}).status_code,302)
