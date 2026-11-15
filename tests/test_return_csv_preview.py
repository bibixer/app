"""Return print queue and saved receipt previews use isolated databases/folders."""
import csv
from pathlib import Path
from unittest.mock import patch

from data_entry import add_manual_jobcard
from data_print_format import job_return_print
from modes import Jobmovement
from support import AppTestCase


class ReturnCsvPreviewTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config['LABEL_PRINT_ROOT'] = self.temp.name
        self.card_id = add_manual_jobcard(self.manual_payload(pieces=50, count=1), self.admin, 'job')['jobData']['jobId']

    def test_return_exports_existing_label_format_once_and_previews_saved_receipt(self):
        payload = self.return_payload(self.card_id, 12)
        payload['items'][0].update(entry_method='calculator', calculation_rows=[{'pieces': 3, 'count': 4}])
        with patch('data_entry.job_return_print', wraps=job_return_print) as exporter:
            response = self.client.post('/summit-retune', json=payload)
            self.assertTrue(response.json['success'])
            duplicate = self.client.post('/summit-retune', json=payload)
            self.assertTrue(duplicate.json['duplicate'])
            exporter.assert_called_once()
            second = self.client.post('/summit-retune', json=self.return_payload(self.card_id, 5, key='second'))
            self.assertTrue(second.json['success'])
        files = list((Path(self.temp.name) / 'job+retun').glob('*.csv'))
        self.assertEqual(len(files), 2)
        return_id = response.json['jobData']['jobData']['return_id']
        first_file = next(path for path in files if path.name.startswith(f'return_{return_id}_'))
        with first_file.open(newline='') as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row['job_number'], str(self.card_id))
        self.assertEqual(row['Pattern_1_line1'], '3x4')
        self.assertEqual(row['Total_1'], '12')
        self.assertIn('received by admin', row['name'])
        self.assertFalse(list(first_file.parent.glob('*.tmp')))
        page = self.client.get(f'/job_retun?jobcard_id={self.card_id}&saved_return=return-1').get_data(as_text=True)
        self.assertIn('Saved Job Return', page)
        self.assertIn('3X4', page)
        self.assertIn('12 pieces', page)
        self.assertIn(f'/edit/jobcard/{self.card_id}', page)
        self.assertEqual(Jobmovement.query.filter_by(flow_type='IN').count(), 2)
        self.login_as(self.operator)
        page = self.client.get(f'/job_retun?jobcard_id={self.card_id}&saved_return=return-1').get_data(as_text=True)
        self.assertNotIn('id="savedReturnPreview"', page)

    def test_export_failure_does_not_rollback_or_duplicate_return(self):
        payload = self.return_payload(self.card_id, 50)
        self.job_return_print.side_effect = OSError('unavailable print drive')
        first = self.client.post('/summit-retune', json=payload)
        self.assertTrue(first.json['success'])
        self.assertIn('CSV export failed', first.json['jobData']['print_warning'])
        self.assertTrue(self.client.post('/summit-retune', json=payload).json['duplicate'])
        self.job_return_print.assert_called_once()
        self.assertEqual(Jobmovement.query.filter_by(flow_type='IN').count(), 1)
        page = self.client.get(f'/job_retun?jobcard_id={self.card_id}&saved_return=return-1&csv_warning=1').get_data(as_text=True)
        self.assertIn('Saved Job Return', page)
        self.assertIn('CSV export failed', page)

    def test_receipt_cannot_be_shown_on_a_different_job(self):
        self.client.post('/summit-retune', json=self.return_payload(self.card_id, 2))
        other = add_manual_jobcard(self.manual_payload(pieces=5, count=1), self.admin, 'other')['jobData']['jobId']
        page = self.client.get(f'/job_retun?jobcard_id={other}&saved_return=return-1').get_data(as_text=True)
        self.assertNotIn('id="savedReturnPreview"', page)
