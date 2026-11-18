"""Audit history rendering, existing server filters and safe value display."""
from datetime import datetime

from modes import db, EditLog
from support import AppTestCase


class EditHistoryUiTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.older = EditLog(entity_type='product',entity_id=self.product.id,action='UPDATE',
            username='admin',changed_at=datetime(2026,11,17,10,20,30),
            changed_fields=['name','size'],old_values={'name':'OLD PRODUCT','size':0},
            new_values={'name':'NEW PRODUCT','size':2})
        self.newer = EditLog(entity_type='outworker',entity_id=self.worker.id,action='CASCADE_UPDATE',
            username='<script>unsafe</script>',changed_at=datetime(2026,11,18,12,30,45),
            changed_fields=['name'],old_values={'name':'OLD WORKER'},new_values={'name':'NEW WORKER'})
        db.session.add_all([self.older,self.newer])
        db.session.commit()

    def test_history_has_timeline_comparisons_snapshots_and_safe_values(self):
        response=self.client.get('/edit-logs')
        self.assertEqual(response.status_code,200)
        page=response.get_data(as_text=True)
        for text in ('Edit history','2 records shown','Changed field','Before','After',
                     'Full saved snapshots','OLD WORKER','NEW WORKER','OLD PRODUCT','NEW PRODUCT'):
            self.assertIn(text,page)
        self.assertLess(page.index(f'data-log-id="{self.newer.id}"'),page.index(f'data-log-id="{self.older.id}"'))
        self.assertIn('18 Nov 2026 · 12:30:45',page)
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;',page)
        self.assertNotIn('<script>unsafe</script>',page)
        self.assertIn('scope="row">Size',page)
        self.assertIn('<pre>0</pre>',page)

    def test_filters_and_empty_states_keep_history_read_only(self):
        page=self.client.get(f'/edit-logs?entity_type=product&entity_id={self.product.id}').get_data(as_text=True)
        self.assertIn('1 record shown',page)
        self.assertIn(f'data-log-id="{self.older.id}"',page)
        self.assertNotIn(f'data-log-id="{self.newer.id}"',page)
        page=self.client.get('/edit-logs?entity_type=product&entity_id=999999').get_data(as_text=True)
        self.assertIn('No edits recorded for these filters.',page)
        self.assertIn('Show all edit history',page)
        self.assertEqual(EditLog.query.count(),2)

    def test_access_stays_admin_only(self):
        self.login_as(self.operator)
        self.assertIn(self.client.get('/edit-logs').status_code,(302,403))
