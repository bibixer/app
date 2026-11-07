"""Optional real Firefox checks. Enable with BH_RUN_BROWSER_TESTS=1."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
import unittest
import urllib.error
import urllib.request

from werkzeug.serving import make_server

from data_entry import add_manual_jobcard, in_move_entery
from data_Process import get_jobcard_return_data
from jobcard_edit import jobcard_edit_context
from modes import db
from support import AppTestCase


@unittest.skipUnless(os.environ.get("BH_RUN_BROWSER_TESTS") == "1", "Set BH_RUN_BROWSER_TESTS=1 for Firefox checks")
class BrowserFlowsTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config['SIMPLE_WORKFLOW'] = True
        native = Path("/snap/firefox/current/usr/lib/firefox")
        driver = os.environ.get("BH_GECKODRIVER") or (str(native / "geckodriver") if (native / "geckodriver").exists() else shutil.which("geckodriver"))
        binary = os.environ.get("BH_FIREFOX_BINARY") or (str(native / "firefox") if (native / "firefox").exists() else shutil.which("firefox"))
        if not driver or not binary:
            self.skipTest("Firefox and geckodriver are required for browser checks")
        server = make_server("127.0.0.1", 0, self.app, threaded=True)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.base_url = f"http://127.0.0.1:{server.server_port}"
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        self.driver_url = f"http://127.0.0.1:{port}"
        log = open(Path(self.temp.name, "firefox.log"), "w")
        self.addCleanup(log.close)
        environment = dict(os.environ)
        if os.environ.get("BH_BROWSER_DISABLE_SANDBOX") == "1":
            environment.update(MOZ_DISABLE_CONTENT_SANDBOX="1", MOZ_DISABLE_RDD_SANDBOX="1", MOZ_DISABLE_GPU_SANDBOX="1")
        process = subprocess.Popen([driver, "--host", "127.0.0.1", "--port", str(port)], env=environment, stdout=log, stderr=log)
        def stop_driver():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self.addCleanup(stop_driver)
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                if process.poll() is not None:
                    self.fail("Firefox driver exited: " + Path(log.name).read_text()[-1500:])
                time.sleep(.05)
        result = self.request("/session", {"capabilities": {"alwaysMatch": {
            "browserName": "firefox", "pageLoadStrategy": "eager",
            "moz:firefoxOptions": {"binary": binary, "args": ["-headless"]},
        }}})
        self.session = result["sessionId"]
        self.command("/timeouts", {"pageLoad": 10000, "script": 10000})
        self.navigate("/login")
        cookie = self.client.get_cookie(self.app.config["SESSION_COOKIE_NAME"])
        self.command("/cookie", {"cookie": {"name": cookie.key, "value": cookie.value, "path": "/", "httpOnly": True}})

    def request(self, path, data=None):
        req = urllib.request.Request(self.driver_url + path, data=json.dumps(data).encode() if data is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)["value"]
        except urllib.error.HTTPError as error:
            self.fail(error.read().decode()[:2000])

    def command(self, path, data=None):
        return self.request(f"/session/{self.session}" + path, data)

    def script(self, code):
        return self.command("/execute/sync", {"script": code, "args": []})

    def navigate(self, path):
        self.command("/url", {"url": self.base_url + path})

    def element(self, selector):
        result = self.command("/element", {"using": "css selector", "value": selector})
        return next(iter(result.values()))

    def type(self, selector, text):
        self.command(f"/element/{self.element(selector)}/value", {"text": text})

    def click(self, selector):
        self.command(f"/element/{self.element(selector)}/click", {})

    def wait_for(self, condition):
        for _ in range(100):
            if self.script("return " + condition):
                return
            time.sleep(.05)
        details = self.script("return {url:location.href,messages:[...document.querySelectorAll('.flash,.notice')].map(n=>n.textContent),invalid:[...document.querySelectorAll('input:invalid,select:invalid,textarea:invalid')].map(n=>({name:n.name,value:n.value,error:n.validationMessage}))}")
        self.fail("Browser condition was not met: " + condition + " " + json.dumps(details))

    def active(self, selector):
        self.assertTrue(self.script(f"return document.activeElement.matches({json.dumps(selector)})"), selector)

    def test_manual_alias_and_type_keyboard_flow(self):
        self.navigate("/manual_jobcard")
        self.type("#masterName", "1\ue007")
        self.active("#manualRows .product")
        self.type("#manualRows .product", "VIM\ue007")
        self.assertEqual(self.script("return document.querySelector('#manualRows .product').value"), self.product.name)
        self.type("#manualRows .pieces", "30\ue007")
        self.type("#manualRows .count", "4\ue007")
        self.active("#manualRows .bundle-type")
        self.type("#manualRows .bundle-type", "\ue015")
        self.active("#manualRows .bundle-type")
        self.type("#manualRows .bundle-type", "\ue007")
        self.active("#manualRows tr:nth-child(2) .product")
        self.type("#manualRows tr:nth-child(2) .product", "\ue003")
        self.active("#manualRows tr:first-child .bundle-type")

    def test_admin_corrects_return_from_job_page_and_raw_movement_is_blocked(self):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, "manual")["jobData"]["jobId"]
        in_move_entery(self.return_payload(card_id, 120), self.admin, "return")
        returned = jobcard_edit_context(card_id)["returns"][0]
        self.navigate(f"/edit/jobcard/{card_id}")
        selector = f'[name="line_{returned["id"]}_quantity"]'
        self.command(f"/element/{self.element(selector)}/clear", {})
        self.type(selector, "50")
        self.type('[name="edit_reason"]', "Corrected returned count")
        self.click('input[type="submit"]')
        self.wait_for("[...document.querySelectorAll('.flash')].some(node=>node.textContent.includes('Saved.'))")
        db.session.expire_all()
        self.assertEqual(get_jobcard_return_data(card_id)["items"][0]["issued"], 70)
        version = self.script("return document.querySelector('[name=version]').value")
        self.click(".restore-return")
        self.assertEqual(self.script(f'return document.querySelector({json.dumps(selector)}).value'), "0")
        self.assertIn("50 pieces", self.script("return document.querySelector('.restore-feedback').textContent"))
        self.type('[name="edit_reason"]', "Restore incorrect return to pending")
        self.click('input[type="submit"]')
        self.wait_for("document.querySelector('[name=version]').value!==" + json.dumps(version))
        db.session.expire_all()
        self.assertEqual(get_jobcard_return_data(card_id)["items"][0]["issued"], 120)
        self.navigate(f'/edit/movement/{returned["id"]}')
        self.assertIn("managed by the app", self.script("return document.body.textContent"))

    def test_calculator_shortcuts_and_print_expansion(self):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, "manual")["jobData"]["jobId"]
        self.navigate(f"/job_retun?jobcard_id={card_id}")
        self.wait_for("!!document.querySelector('.return-input')")
        self.script("document.querySelector('.return-input').focus()")
        self.command("/actions", {"actions": [{"type": "key", "id": "keyboard", "actions": [
            {"type": "keyDown", "value": "\ue009"}, {"type": "keyDown", "value": "c"},
            {"type": "keyUp", "value": "c"}, {"type": "keyUp", "value": "\ue009"}]}]})
        self.active(".calc-pieces")
        self.type(".calc-pieces", "\ue00c")
        self.active(".return-input")
        self.navigate("/outworker_report")
        self.script("document.querySelector('[name=name]').value=" + json.dumps(self.worker_name) +
                    ";document.querySelector('[name=date_from]').value='2026-01-01';" +
                    "document.querySelector('[name=date_to]').value='2027-01-01';document.querySelector('.filter-form').requestSubmit()")
        self.wait_for("!!document.querySelector('.product-totals')")
        self.assertFalse(self.script("return document.querySelector('.product-totals').open"))
        self.assertTrue(self.script("const states=[...document.querySelectorAll('details')].map(d=>d.open);" +
                                   "window.dispatchEvent(new Event('beforeprint'));const expanded=[...document.querySelectorAll('details')].every(d=>d.open);" +
                                   "window.dispatchEvent(new Event('afterprint'));return expanded&&JSON.stringify(states)===JSON.stringify([...document.querySelectorAll('details')].map(d=>d.open))"))

    def test_primary_pages_fit_phone_viewport_and_navigation_opens(self):
        self.command("/window/rect", {"width": 1440, "height": 1000})
        self.navigate("/manual_jobcard")
        for path in ("/manual_jobcard", "/retune_product", "/add_items", "/edit", "/payroll?worker_id=1", "/users", "/admin_dashord", "/returns/outworker?worker_id=1"):
            self.command("/frame", {"id": None})
            self.script("document.body.innerHTML='<iframe id=phone style=\"border:0;width:390px;height:844px\"></iframe>';" +
                        "document.querySelector('iframe').src=" + json.dumps(self.base_url + path))
            frame = self.element("#phone")
            self.command("/frame", {"id": {"element-6066-11e4-a52e-4f735466cecf": frame}})
            self.wait_for("!!document.querySelector('#main-content')&&getComputedStyle(document.body).getPropertyValue('--ui-bg').trim()!==''")
            sizes = self.script("return {viewport:innerWidth,page:document.documentElement.scrollWidth,main:document.querySelector('main').getBoundingClientRect().right}")
            self.assertEqual(sizes["viewport"], 390)
            self.assertLessEqual(sizes["page"], 390)
            self.assertLessEqual(sizes["main"], 390)
            self.click("#appMenuOpen")
            self.wait_for("document.querySelector('#appDrawer').classList.contains('open')&&Math.abs(new DOMMatrix(getComputedStyle(document.querySelector('#appDrawer')).transform).m41)<.5")
            self.click("#appMenuClose")
            self.wait_for("!document.querySelector('#appDrawer').classList.contains('open')")
        self.command("/frame", {"id": None})

    def test_partial_job_payroll_selection_and_later_returns(self):
        from payroll_service import save_rate
        from modes import OutworkerPayrollJob
        save_rate(self.product.id, '', '5.5', 'new', 'browser-rate', self.admin)
        card_id = add_manual_jobcard(self.manual_payload(pieces=10, count=1), self.admin,
                                     'browser-job')['jobData']['jobId']
        in_move_entery(self.return_payload(card_id, 5), self.admin, 'browser-first-return')
        payment_ids = []
        for batch in (1, 2):
            self.navigate(f'/payroll?worker_id={self.worker.id}')
            self.assertIn('Awaiting return: ' + ('5' if batch == 1 else '0'),
                          self.script('return document.body.textContent'))
            self.click(f'input[name="job_ids"][value="{card_id}"]')
            self.click('form:has(input[name="action"][value="preview"]) button[type="submit"]')
            self.wait_for("!!document.querySelector('#payroll-preview')")
            self.assertIn('paying 5 pieces', self.script("return document.querySelector('#payroll-preview').textContent"))
            self.click('form:has(input[name="action"][value="pay"]) button[type="submit"]')
            self.wait_for("/\\/payroll\\/\\d+$/.test(location.pathname)")
            payment_ids.append(self.script('return location.pathname'))
            db.session.expire_all()
            self.assertEqual(sum(row.pieces for row in OutworkerPayrollJob.query.all()), batch * 5)
            if batch == 1:
                self.assertEqual(get_jobcard_return_data(card_id)['items'][0]['issued'], 5)
                in_move_entery(self.return_payload(card_id, 5, key='browser-rest'), self.admin, 'browser-rest')
        self.assertNotEqual(payment_ids[0], payment_ids[1])
        self.navigate(f'/payroll?worker_id={self.worker.id}')
        self.assertIn('No returned unpaid pieces', self.script('return document.body.textContent'))

    def test_weekly_product_pies_and_week_navigation(self):
        from modes import Item_data
        db.session.add(Item_data(name='SECOND PRODUCT', size=0, meters=0, enter_user='admin'))
        db.session.commit()
        for index, name in enumerate(('VIM', 'SECOND PRODUCT')):
            card_id = add_manual_jobcard(self.manual_payload(product=name,pieces=10,count=1),
                                         self.admin,f'pie-job-{index}')['jobData']['jobId']
            in_move_entery(self.return_payload(card_id,4),self.admin,f'pie-return-{index}')
        self.navigate('/admin_dashord')
        self.wait_for("document.querySelectorAll('.dash-pie svg path').length===4")
        self.assertEqual(self.script("return document.querySelectorAll('[data-pie-chart]').length"),2)
        self.script("document.querySelector('.dash-pie-legend button').focus()")
        self.wait_for("document.querySelector('.dash-pie-readout').textContent.includes('%')")
        self.assertTrue(self.script("return !!document.querySelector('.dash-pie svg .is-active')"))
        self.click('.dash-week-selector nav a:first-child')
        self.wait_for("document.querySelector('.dash-empty')?.textContent.includes('No outflow')")
        self.assertIn('No inflow',self.script('return document.body.textContent'))

    def test_worker_returns_save_one_job_without_losing_another_jobs_draft(self):
        from modes import Jobmovement
        ids=[add_manual_jobcard(self.manual_payload(pieces=10,count=1),self.admin,
                                f'workspace-{index}')['jobData']['jobId'] for index in range(2)]
        self.navigate(f'/returns/outworker?worker_id={self.worker.id}')
        self.wait_for("document.querySelectorAll('.return-job-frame').length===2")
        def enter_job(index):
            self.command('/frame',{'id':None})
            self.script(f"document.querySelectorAll('.return-job-frame')[{index}].scrollIntoView()")
            element=self.element(f'[data-job-id="{ids[index]}"] iframe')
            self.command('/frame',{'id':{'element-6066-11e4-a52e-4f735466cecf':element}})
            self.wait_for("!!document.querySelector('.return-input')")
        enter_job(0)
        self.type('.return-input','3')
        enter_job(1)
        self.type('.return-input','7')
        enter_job(0)
        # Keep receipt windows/downloads inside this isolated browser test.
        self.script("window.open=()=>null;const click=HTMLAnchorElement.prototype.click;HTMLAnchorElement.prototype.click=function(){if(!this.download)return click.call(this)}")
        self.click('.btn-submit')
        self.command('/frame',{'id':None})
        self.wait_for(f"document.querySelector('[data-job-id=\"{ids[0]}\"]').dataset.remaining==='7'")
        self.assertEqual(self.script("return document.querySelector('#open-return-pieces').textContent"),'17')
        enter_job(1)
        self.assertEqual(self.script("return document.querySelector('.return-input').value"),'7')
        self.command('/frame',{'id':None})
        db.session.expire_all()
        self.assertEqual(Jobmovement.query.filter_by(jobcard=str(ids[0]),flow_type='IN').one().inflow,3)
        self.assertEqual(Jobmovement.query.filter_by(jobcard=str(ids[1]),flow_type='IN').count(),0)

    def test_custom_dashboard_dates_and_new_tab_details(self):
        from modes import Jobcard
        card_id=add_manual_jobcard(self.manual_payload(pieces=10,count=1),self.admin,'range-browser')['jobData']['jobId']
        day=db.session.get(Jobcard,card_id).date.date().isoformat()
        self.navigate('/admin_dashord')
        self.script(f"document.querySelector('#dashboard-from').value='{day}';document.querySelector('#dashboard-to').value='{day}'")
        self.click('.dash-week-selector form button')
        self.wait_for("location.search.includes('date_from=')&&location.search.includes('date_to=')")
        before=self.command('/window/handles')
        self.click('a.dash-given')
        for _ in range(100):
            handles=self.command('/window/handles')
            if len(handles)>len(before):
                break
            time.sleep(.05)
        self.assertEqual(len(handles),len(before)+1)
        self.command('/window',{'handle':next(handle for handle in handles if handle not in before)})
        self.wait_for("location.pathname==='/dashboard/movements'")
        self.assertIn('Outflow / given details',self.script('return document.body.textContent'))
        self.assertIn(f'#{card_id}',self.script('return document.body.textContent'))
