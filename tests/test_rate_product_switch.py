import json
from modes import db, Item_data, OutworkerRate, EditLog
from payroll_service import save_rate, rate_version
from kept_products import save_product_value
from support import AppTestCase


class RateProductSwitchTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.other=Item_data(name='SECOND PRODUCT',size=1,meters=1,enter_user='admin')
        db.session.add(self.other);db.session.commit()
        save_rate(self.product.id,'','5','new','base',self.admin)
        save_rate(self.product.id,'good_cut','6','new','override',self.admin)
        save_product_value(self.product.id,'120',0,'value',self.admin)

    def rate(self, bundle_type=''):
        return OutworkerRate.query.filter_by(product_id=self.product.id,bundle_type=bundle_type).first()

    def post(self, changes, token='switch-save'):
        return self.client.post('/payroll/rates',data={'action':'save_and_switch',
            'product_id':self.product.id,'next_product_id':self.other.id,
            'changes':json.dumps(changes),'submission_token':token})

    def changes(self):
        return [{'field':'rate','bundle_type':'','value':'5.5','version':rate_version(self.rate())},
                {'field':'product_value','value':'125','version':'12000'},
                {'field':'rate','bundle_type':'good_cut','value':'','version':rate_version(self.rate('good_cut'))}]

    def test_save_all_switch_is_atomic_audited_and_retry_safe(self):
        changes=self.changes()
        response=self.post(changes)
        self.assertEqual(response.status_code,200)
        self.assertIn(f'product_id={self.other.id}',response.json['next_url'])
        self.assertEqual(self.rate().rate_units,55000)
        self.assertIsNone(self.rate('good_cut'))
        self.assertEqual(self.product.product_value_paise,12500)
        self.assertEqual(self.other.product_value_paise,0)
        count=EditLog.query.count()
        self.assertTrue(self.post(changes).json['success'])
        self.assertEqual(EditLog.query.count(),count)
        changes[0]['value']='9'
        self.assertEqual(self.post(changes).status_code,400)
        self.assertEqual(self.rate().rate_units,55000)

    def test_stale_last_field_rolls_back_all_other_changes(self):
        changes=self.changes();changes[-1]['version']='stale'
        count=EditLog.query.count()
        self.assertEqual(self.post(changes).status_code,400)
        self.assertEqual(self.rate().rate_units,50000)
        self.assertEqual(self.product.product_value_paise,12000)
        self.assertIsNotNone(self.rate('good_cut'))
        self.assertEqual(EditLog.query.count(),count)
        changes[-1]['version']=rate_version(self.rate('good_cut'))
        self.assertTrue(self.post(changes).json['success'])

    def test_invalid_or_duplicate_fields_cannot_partially_save(self):
        for index, changes in enumerate(([],[{'field':'bad'}],
                [self.changes()[0],self.changes()[0]],
                [self.changes()[0],{'field':'product_value','value':'-1','version':'12000'}])):
            with self.subTest(changes=changes):
                self.assertEqual(self.post(changes,f'invalid-{index}').status_code,400)
                self.assertEqual(self.rate().rate_units,50000)
                self.assertEqual(self.product.product_value_paise,12000)

    def test_product_switch_view_contains_complete_target_values(self):
        save_rate(self.other.id,'','7','new','other-base',self.admin)
        save_product_value(self.other.id,'90',0,'other-value',self.admin)
        page=self.client.get(f'/payroll/rates?product_id={self.other.id}').get_data(as_text=True)
        self.assertIn('Product value · SECOND PRODUCT',page)
        self.assertIn('value="90.00"',page)
        self.assertIn('value="7"',page)
        self.assertIn('ratesSwitchDialog',page)
        self.login_as(self.operator)
        self.assertIn(self.post(self.changes()).status_code,(302,403))
