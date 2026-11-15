"""Page shells remain valid and form controls survive the shared UI redesign."""

from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import unittest

import test_payroll
from form import Date_form_with_name
from flask import render_template
from flask_login import login_user
from data_Process import outworker_job_ledger, outworker_period_account


class PageMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.counts = {}
        self.ids = set()
        self.styles = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.counts[tag] = self.counts.get(tag, 0) + 1
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])
        if tag == "link" and values.get("rel") == "stylesheet":
            self.styles.append(values.get("href", ""))


class ApplicationUiTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_payroll.PayrollTest()
        self.fixture.setUp()
        self.app, self.client = self.fixture.app, self.fixture.client

    def tearDown(self):
        self.fixture.tearDown()

    def test_all_primary_pages_use_one_document_and_shared_design(self):
        paths = ["/admin_dashord", "/bale_entery", "/jobcard", "/manual_jobcard",
                 "/retune_product", "/outworker_report", "/product_report", "/cutter_report",
                 "/find_edit", "/edit", "/edit/product/1", "/edit-logs", "/add_items",
                 "/add_cutter", "/add_outworver", "/add_suppy", "/payroll", "/payroll/rates",
                 "/jobcard/ledger"]
        for path in paths:
            with self.subTest(page=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                page = PageMarkup(response.get_data(as_text=True))
                self.assertEqual(page.counts.get("html"), 1)
                self.assertEqual(page.counts.get("body"), 1)
                self.assertEqual(page.counts.get("main"), 1)
                self.assertIn("main-content", page.ids)
                self.assertTrue(any("style/app.css" in href for href in page.styles))
                for href in page.styles:
                    if href.startswith("/static/"):
                        resource = self.client.get(href)
                        try:
                            self.assertEqual(resource.status_code, 200)
                        finally:
                            resource.close()

    def test_job_pages_keep_their_interaction_targets(self):
        self.fixture.card()
        pages = {
            "/manual_jobcard": {"masterName", "masterSuggestions", "manualRows", "submitManual", "result", "grandTotal"},
            "/jobcard": {"custInput", "custSug", "billTable", "totalpic", "totalKg", "summaryContent"},
            "/job_retun?jobcard_id=1": {"jobName", "jobDate", "completedHistoryList"},
            "/jobcard/1/ledger": {"main-content"},
        }
        for path, expected_ids in pages.items():
            with self.subTest(page=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(expected_ids.issubset(PageMarkup(response.get_data(as_text=True)).ids))
        guest = self.app.test_client()
        page = PageMarkup(guest.get("/login").get_data(as_text=True))
        self.assertIn("main-content", page.ids)
        self.assertEqual(page.counts.get("body"), 1)

    def test_product_totals_remain_collapsed_and_all_templates_compile(self):
        self.fixture.card()
        worker_name = f"{self.fixture.worker.id}***{self.fixture.worker.name}--{self.fixture.worker.adders}/-"
        with self.app.test_request_context("/outworker_report"):
            login_user(self.fixture.user)
            form = Date_form_with_name()
            form.name.data = worker_name
            form.date_from.data, form.date_to.data = date(2026, 11, 1), date(2026, 11, 30)
            report = outworker_job_ledger(worker_name, form.date_from.data, form.date_to.data)
            report["account"] = outworker_period_account(worker_name, form.date_from.data, form.date_to.data)
            html = render_template("outworker_job_report.html", current_form=form, names=[worker_name],
                                   report=report, pending_returns=[])
            self.assertIn('<details class="product-totals">', html)
            self.assertEqual(PageMarkup(html).counts.get("body"), 1)
        for path in Path(self.app.template_folder).glob("*.html"):
            with self.subTest(template=path.name):
                self.app.jinja_env.get_template(path.name)


if __name__ == "__main__":
    unittest.main()
