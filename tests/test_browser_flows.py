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
        details['frames'] = self.script("return [...document.querySelectorAll('iframe')].map(f=>({src:f.src,height:f.offsetHeight,ready:f.contentDocument?.readyState,text:f.contentDocument?.body?.textContent?.slice(0,250),inputs:[...(f.contentDocument?.querySelectorAll('.return-input')||[])].map(i=>i.value)}))")
        details['layout'] = self.script("return {open:document.querySelector('details.kept-item')?.open,frame:frameElement?.clientHeight,main:document.querySelector('main')?.getBoundingClientRect().height}")
        self.fail("Browser condition was not met: " + condition + " " + json.dumps(details))

    def active(self, selector):
        self.assertTrue(self.script(f"return document.activeElement.matches({json.dumps(selector)})"), selector)

    def assert_five_visible_suggestions(self, selector):
        self.assertTrue(self.script("""
            const list=document.querySelector(%s), rows=[...list.querySelectorAll('[role=option]')];
            const bottom=list.getBoundingClientRect().bottom-parseFloat(getComputedStyle(list).paddingBottom)-1;
            return rows.length>5 && rows[4].getBoundingClientRect().bottom<=bottom+1
                && rows[5].getBoundingClientRect().top>=bottom-1 && list.scrollHeight>list.clientHeight;
        """ % json.dumps(selector)))

    def test_outworker_edit_matches_setup_and_keeps_existing_aliases(self):
        from modes import OutworkerAlias
        self.navigate(f'/edit/outworker/{self.worker.id}')
        self.assertEqual(self.script("return getComputedStyle(document.querySelector('.header-box')).backgroundColor"),'rgb(0, 0, 0)')
        self.assertEqual(self.script("return getComputedStyle(document.querySelector('input[type=submit]')).backgroundColor"),'rgb(35, 196, 131)')
        self.assertFalse(self.script("return !!document.querySelector('[name=aliases]')"))
        self.command(f'/element/{self.element("[name=name]")}/clear',{})
        self.type('[name=name]','UPDATED WORKER')
        self.click('input[type=submit]')
        self.wait_for("document.querySelector('.notice')?.textContent.includes('Saved.')")
        db.session.expire_all()
        self.assertEqual(self.worker.name,'UPDATED WORKER')
        self.assertEqual(OutworkerAlias.query.filter_by(worker_id=self.worker.id).one().alias,'RAM CITY')
        self.command('/window/rect',{'width':390,'height':844})
        self.wait_for('document.documentElement.scrollWidth<=innerWidth')
        self.click('.outworker-edit-links a:first-child')
        self.wait_for("document.querySelector('#entityType')?.value==='outworker'")

    def test_edit_center_surfaces_search_default_and_mobile_layout(self):
        self.navigate('/add_outworver')
        self.click('.outworker-edit-link')
        self.wait_for("document.querySelector('#entryList').getAttribute('aria-busy')==='false'")
        self.assertEqual(self.script("return document.querySelector('#entityType').value"), 'outworker')
        self.assertIn('RAM', self.script("return document.querySelector('#entryList').textContent"))
        for selector in ('.edit-hero','.edit-workspace','.entry'):
            self.assertNotEqual(self.script(f"return getComputedStyle(document.querySelector('{selector}')).backgroundImage"),'none')
        self.assertEqual(self.script("return getComputedStyle(document.querySelector('.edit-search-panel')).backgroundColor"),'rgb(255, 255, 255)')
        self.type('#entrySearch','NO SUCH WORKER')
        self.wait_for("!document.querySelector('#noResults').hidden")
        self.assertEqual(self.script("return document.querySelectorAll('.entry').length"),0)
        self.command(f'/element/{self.element("#entrySearch")}/clear',{})
        self.type('#entrySearch','RAM CITY')
        self.wait_for("document.querySelectorAll('.entry').length===1")
        self.command('/window/rect',{'width':390,'height':844})
        self.wait_for('document.documentElement.scrollWidth<=innerWidth')
        self.click('.edit-link')
        self.wait_for(f"location.pathname==='/edit/outworker/{self.worker.id}'")

    def test_outworker_setup_uses_login_style_and_saves_once(self):
        from modes import Outworker
        self.navigate('/add_outworver')
        self.assertIn('rgb(0, 0, 0)', self.script("return getComputedStyle(document.querySelector('.legacy-login .header-box')).backgroundColor"))
        self.assertEqual(self.script("return getComputedStyle(document.querySelector('.legacy-login .form-container')).backgroundColor"), 'rgb(255, 255, 255)')
        self.assertEqual(self.script("return getComputedStyle(document.querySelector('input[type=submit]')).backgroundColor"), 'rgb(35, 196, 131)')
        self.assertTrue(self.script("return !!document.querySelector('nav') && !!document.querySelector('.ui-waves')"))
        self.type('#name','BROWSER WORKER\ue004')
        self.active('#address')
        self.type('#address','CITY\ue004')
        self.active('#number')
        self.type('#number','9876543210')
        self.click('input[type=submit]')
        self.wait_for("document.querySelector('.notice')?.textContent.includes('successfully added')")
        db.session.expire_all()
        self.assertEqual(Outworker.query.filter_by(name='BROWSER WORKER').count(),1)
        self.outworker_qr_print.assert_called_once()
        self.command('/window/rect', {'width':390,'height':844})
        self.wait_for('document.documentElement.scrollWidth<=innerWidth')
        self.assertTrue(self.script("return document.documentElement.scrollWidth<=innerWidth"),
            self.script("return [...document.querySelectorAll('main,main *')].filter(e=>e.getBoundingClientRect().right>innerWidth).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right})).slice(0,12)"))

    def test_manual_alias_and_type_keyboard_flow(self):
        self.navigate("/manual_jobcard")
        self.type('#masterName','\ue007')
        self.active('#masterName')
        self.assertEqual(self.script("return document.querySelector('#masterName').value"),'')
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

    def test_manual_product_suggestions_group_names_and_aliases(self):
        from modes import Item_data, ItemAlias
        db.session.add(ItemAlias(item_id=self.product.id, alias='VIMAL SHORT'))
        for index in range(12):
            db.session.add(Item_data(name=f'FABRIC {index}', size=2, meters=1, enter_user='admin'))
        db.session.commit()
        self.navigate('/manual_jobcard')
        self.type('#masterName', '1\ue007')
        picker = '#manualRows tr:first-child .product-suggestions'
        product = '#manualRows tr:first-child .product'
        self.assertFalse(self.script(f"return document.querySelector('{product}').hasAttribute('list')"))
        self.assertEqual(self.script(f"return document.querySelectorAll('{picker} [role=option]').length"), 13)
        self.assertTrue(self.script(f"const list=document.querySelector('{picker}');return list.scrollHeight>list.clientHeight"))
        self.assert_five_visible_suggestions(picker)
        self.type(product, 'VIM')
        self.assertEqual(self.script(f"return document.querySelectorAll('{picker} [role=option]').length"), 1)
        for text in (self.product.name, 'VIM', 'VIMAL SHORT'):
            self.assertIn(text, self.script(f"return document.querySelector('{picker}').textContent"))
        self.type(product, '\ue007')
        self.active('#manualRows .pieces')
        self.assertEqual(self.script(f"return document.querySelector('{product}').value"), self.product.name)
        self.command(f'/element/{self.element(product)}/clear', {})
        self.type(product, 'FABRIC\ue015\ue007')
        self.active('#manualRows .pieces')
        self.assertEqual(self.script(f"return document.querySelector('{product}').value"), 'FABRIC 0')
        self.command(f'/element/{self.element(product)}/clear', {})
        self.type(product, 'VIMAL SHORT')
        self.click(picker + ' [role=option]')
        self.active('#manualRows .pieces')
        self.assertEqual(self.script(f"return document.querySelector('{product}').value"), self.product.name)
        self.command(f'/element/{self.element(product)}/clear', {})
        self.type(product, '20\ue007')
        self.active(product)
        self.assertIn('not an added product', self.script("return document.querySelector('#message').textContent"))
        self.type(product, '\ue00c')
        self.assertEqual(self.script(f"return document.querySelector('{product}').getAttribute('aria-expanded')"), 'false')

    def test_manual_worker_suggestions_are_unique_scrollable_and_keyboard_accessible(self):
        from modes import Outworker, OutworkerAlias
        worker=Outworker(name='RAVI',adders='BH GARMENTS',number=2,enter_user='admin')
        db.session.add(worker)
        db.session.flush()
        worker_id=worker.id
        db.session.add_all([OutworkerAlias(worker_id=worker_id,alias='RAV'),
                            OutworkerAlias(worker_id=worker_id,alias='RAVI MASTER')])
        for index in range(12):
            db.session.add(Outworker(name=f'WORKER {index}',adders='CITY',number=index+100,enter_user='admin'))
        db.session.commit()
        db.session.add(Outworker(id=200,name='PREFIX ONLY',adders='CITY',number=200,enter_user='admin'))
        db.session.commit()
        self.navigate('/manual_jobcard')
        self.wait_for("document.querySelector('#masterName').getAttribute('aria-expanded')==='true'")
        self.assertFalse(self.script("return document.querySelector('#masterName').hasAttribute('list')"))
        self.assertEqual(self.script("return document.querySelectorAll('#masterSuggestions [role=option]').length"),15)
        self.assertTrue(self.script("const list=document.querySelector('#masterSuggestions');return list.scrollHeight>list.clientHeight"))
        self.assert_five_visible_suggestions('#masterSuggestions')
        self.type('#masterName','20\ue007')
        self.active('#masterName')
        self.assertEqual(self.script("return document.querySelector('#masterName').value"),'20')
        self.command(f'/element/{self.element("#masterName")}/clear',{})
        self.type('#masterName',str(worker_id))
        self.wait_for("document.querySelectorAll('#masterSuggestions [role=option]').length===1")
        self.assertIn('RAVI',self.script("return document.querySelector('#masterSuggestions').textContent"))
        self.type('#masterName','\ue007')
        self.active('#manualRows .product')
        self.assertTrue(self.script(f"return document.querySelector('#masterName').value.startsWith('{worker_id}***RAVI')"))
        self.command(f'/element/{self.element("#masterName")}/clear',{})
        self.type('#masterName','RAV')
        self.wait_for("document.querySelectorAll('#masterSuggestions [role=option]').length===1")
        self.click(f'#masterSuggestions [data-worker-id="{worker_id}"]')
        self.active('#manualRows .product')
        self.command(f'/element/{self.element("#masterName")}/clear',{})
        self.type('#masterName','WORKER')
        self.wait_for("document.querySelectorAll('#masterSuggestions [role=option]').length===12")
        self.type('#masterName','\ue015\ue007')
        self.active('#manualRows .product')
        self.command(f'/element/{self.element("#masterName")}/clear',{})
        self.type('#masterName','NO SUCH WORKER\ue007')
        self.assertIn('valid master',self.script("return document.querySelector('#message').textContent"))
        self.active('#masterName')
        self.type('#masterName','\ue00c')
        self.assertEqual(self.script("return document.querySelector('#masterName').getAttribute('aria-expanded')"),'false')

    def test_lost_manual_save_response_retry_restores_printable_job(self):
        self.navigate('/manual_jobcard')
        self.script("""
            document.querySelector('#masterName').value='1';
            document.querySelector('#manualRows .product').value='VIM';
            document.querySelector('#manualRows .pieces').value='30';
            document.querySelector('#manualRows .count').value='4';
            const realFetch=window.fetch.bind(window);
            window.lostResponse=false;
            window.fetch=async (...args)=>{
                const response=await realFetch(...args);
                if(args[0]==='/submit-manual-jobcard' && !window.lostResponse){
                    window.lostResponse=true;
                    throw new TypeError('Simulated response lost after commit');
                }
                return response;
            };
        """)
        self.click('#submitManual')
        self.wait_for("document.querySelector('#message').textContent.includes('Network error')")
        self.assertFalse(self.script("return document.querySelector('#submitManual').disabled"))
        self.click('#submitManual')
        self.wait_for("document.querySelector('#result').textContent.includes('Job Card #')")
        self.assertIn('120 pieces', self.script("return document.querySelector('#result').textContent"))
        self.assertFalse(self.script("return !!document.querySelector('#result button')"))
        self.assertTrue(self.script("return document.querySelector('.saved-job-preview').open"))
        self.assertNotEqual(self.script("return getComputedStyle(document.querySelector('.saved-job-preview')).backgroundColor"), 'rgba(0, 0, 0, 0)')
        self.assertNotEqual(self.script("return getComputedStyle(document.querySelector('.saved-job-preview summary')).backgroundImage"), 'none')
        self.active('#masterName')
        self.assertEqual(self.script("return document.querySelector('#masterName').value"), '')
        self.assertEqual(self.script("return document.querySelectorAll('#manualRows tr').length"), 1)
        self.assertEqual(self.script("return document.querySelector('#manualRows .product').value"), '')
        self.assertFalse(self.script("return document.querySelector('#submitManual').disabled"))
        db.session.expire_all()
        from modes import Jobcard
        self.assertEqual(Jobcard.query.count(), 1)
        self.job_cade_print.assert_called_once()
        self.assertIn('jobcard_id=',self.script("return document.querySelector('#editSavedJob').getAttribute('href')"))
        self.click('.saved-job-preview summary')
        self.assertFalse(self.script("return document.querySelector('.saved-job-preview').open"))
        self.click('.saved-job-preview summary')
        self.assertTrue(self.script("return document.querySelector('.saved-job-preview').open"))
        self.script("document.querySelector('#masterName').value='1';document.querySelector('#manualRows .product').value='VIM';document.querySelector('#manualRows .pieces').value='5';document.querySelector('#manualRows .count').value='1'")
        self.click('#submitManual')
        self.wait_for("document.querySelector('#result').textContent.includes('5 pieces')")
        db.session.expire_all()
        self.assertEqual(Jobcard.query.count(), 2)
        self.assertEqual(self.job_cade_print.call_count, 2)
        self.active('#masterName')

    def test_manual_save_and_old_job_edit_shortcuts(self):
        card_id=add_manual_jobcard(self.manual_payload(pieces=10,count=1),self.admin,'old-to-edit')['jobData']['jobId']
        self.navigate('/manual_jobcard')
        self.type('#editJobNumber',str(card_id)+'\ue007')
        self.wait_for(f"location.pathname==='/edit/jobcard/{card_id}'")
        self.navigate('/manual_jobcard')
        self.script("document.querySelector('#masterName').value='1';document.querySelector('#manualRows .product').value='VIM';document.querySelector('#manualRows .pieces').value='36';document.querySelector('#manualRows .count').value='2'")
        self.click('#submitManual')
        self.wait_for("!!document.querySelector('#editSavedJob')")
        self.click('#editSavedJob')
        self.wait_for("location.pathname.startsWith('/edit/jobcard/') && !!document.querySelector('.edit-fields')")
        self.assertNotEqual(self.script('return location.pathname'),f'/edit/jobcard/{card_id}')

    def test_kept_product_value_preview_recovery_and_payroll(self):
        from kept_products import save_product_value
        from payroll_service import save_rate
        from modes import JobKeptProduct, OutworkerPayroll, OutworkerPayrollJob
        save_product_value(self.product.id, '120', 0, 'browser-value', self.admin)
        save_rate(self.product.id, '', '5.5', 'new', 'browser-rate', self.admin)
        card_id = add_manual_jobcard(self.manual_payload(pieces=50, count=1), self.admin, 'browser-job')['jobData']['jobId']
        in_move_entery(self.return_payload(card_id, 48), self.admin, 'browser-return')
        self.navigate(f'/job_retun?jobcard_id={card_id}')
        self.type('#kept-pieces > summary','\ue007')
        self.click('details.input-guide summary')
        self.type('.kept-product-form [name=pieces]', '2')
        self.wait_for("document.querySelector('.kept-recovery-preview').textContent.includes('240.00')")
        self.click('.kept-product-form button[type=submit]')
        self.wait_for("document.body.textContent.includes('2 kept pieces recorded')")
        db.session.expire_all()
        row = JobKeptProduct.query.one()
        self.assertEqual(row.amount_paise, 24000)
        self.navigate(f'/payroll?worker_id={self.worker.id}')
        self.assertIn('Kept: 2', self.script('return document.body.textContent'))
        self.click(f'input[name=job_ids][value="{card_id}"]')
        self.click(f'input[name=advance_ids][value="{row.advance_id}"]')
        self.click('#payrollSelectionForm button[type=submit]')
        self.wait_for("document.querySelector('#payroll-local-review').open")
        breakdown = self.script("return document.querySelector('#payrollLocalBreakdown').textContent")
        self.assertIn('paying 50 pieces', breakdown)
        self.assertIn('Kept 2', breakdown)
        self.click('#payrollLocalConfirm')
        self.wait_for("/\\/payroll\\/\\d+$/.test(location.pathname)")
        db.session.expire_all()
        payroll = OutworkerPayroll.query.one()
        self.assertEqual((payroll.gross_paise, payroll.deduction_paise, payroll.net_paise), (27500,24000,3500))
        self.assertEqual(OutworkerPayrollJob.query.one().pieces, 50)

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

    def test_admin_edits_given_return_and_kept_together(self):
        from kept_products import save_product_value, record_kept_product
        from modes import JobKeptProduct, OutworkerAdvance
        save_product_value(self.product.id,'120',0,'edit-value',self.admin)
        card_id=add_manual_jobcard(self.manual_payload(pieces=50,count=1),self.admin,'edit-kept-job')['jobData']['jobId']
        in_move_entery(self.return_payload(card_id,48),self.admin,'edit-kept-return')
        kept=record_kept_product(card_id,self.product.id,'lump',2,12000,2,'yes','','edit-keep',self.admin)
        context=jobcard_edit_context(card_id)
        self.navigate(f'/edit/jobcard/{card_id}')
        for selector,value in ((f'[name="line_{context["given"][0]["id"]}_pieces"]','60'),
                               (f'[name="line_{context["returns"][0]["id"]}_quantity"]','50'),
                               (f'[name="kept_{kept.id}_pieces"]','4'),
                               (f'[name="kept_{kept.id}_value"]','130')):
            self.command(f'/element/{self.element(selector)}/clear',{})
            self.type(selector,value)
        self.assertIn('520.00',self.script("return document.querySelector('[data-kept-recovery]').textContent"))
        self.type('[name="edit_reason"]','Correct all three sections together')
        self.click('input[type="submit"]')
        self.wait_for("[...document.querySelectorAll('.flash')].some(node=>node.textContent.includes('Saved.'))")
        db.session.expire_all()
        self.assertEqual(db.session.get(JobKeptProduct,kept.id).pieces,4)
        self.assertEqual(OutworkerAdvance.query.one().amount_paise,52000)
        self.assertEqual(get_jobcard_return_data(card_id)['items'][0]['issued'],6)

    def test_job_ledger_layout_history_and_print_restoration(self):
        from kept_products import save_product_value, record_kept_product
        save_product_value(self.product.id,'120',0,'ledger-value',self.admin)
        card_id=add_manual_jobcard(self.manual_payload(pieces=50,count=1),self.admin,'ledger-job')['jobData']['jobId']
        in_move_entery(self.return_payload(card_id,48),self.admin,'ledger-return')
        record_kept_product(card_id,self.product.id,'lump',2,12000,2,'yes','Retained by agreement','ledger-kept',self.admin)
        self.navigate(f'/jobcard/{card_id}/ledger')
        self.wait_for("document.querySelectorAll('.event').length===3")
        self.assertEqual(self.script("return document.querySelectorAll('.total').length"),4)
        legend_backgrounds=self.script("return [...document.querySelectorAll('.movement-legend>span')].map(node=>getComputedStyle(node).backgroundColor)")
        self.assertEqual(len(set(legend_backgrounds)),3)
        self.assertNotIn('rgba(0, 0, 0, 0)',legend_backgrounds)
        self.assertIn('2 pcs',self.script("return document.querySelector('.event.kept').textContent"))
        self.assertIn('240.00',self.script("return document.querySelector('.recovery-note').textContent"))
        self.assertTrue(self.script(f"return !!document.querySelector('a[href=\"/edit/jobcard/{card_id}\"]')"))
        self.click('.kept-history > summary')
        self.assertTrue(self.script("return document.querySelector('.kept-history').open"))
        self.assertIn('Retained by agreement',self.script("return document.querySelector('.kept-history').textContent"))
        self.wait_for("document.readyState==='complete'")
        previous=self.script("return [...document.querySelectorAll('.product-history')].map(node=>node.open)")
        self.script("window.dispatchEvent(new Event('beforeprint'))")
        self.assertTrue(self.script("return [...document.querySelectorAll('.product-history')].every(node=>node.open)"))
        self.script("window.dispatchEvent(new Event('afterprint'))")
        self.assertEqual(self.script("return [...document.querySelectorAll('.product-history')].map(node=>node.open)"),previous)
        self.assertTrue(self.script("return document.querySelector('.kept-history').open"))
        self.command('/window/rect',{'width':390,'height':844})
        self.assertTrue(self.script("return document.documentElement.scrollWidth<=innerWidth+1"))
        self.script("document.querySelector('a[href=\"#ledger-movements\"]').click()")
        self.assertIn('#ledger-movements',self.script('return location.hash'))
        self.login_as(self.operator)
        cookie=self.client.get_cookie(self.app.config['SESSION_COOKIE_NAME'])
        self.command('/cookie',{'cookie':{'name':cookie.key,'value':cookie.value,'path':'/','httpOnly':True}})
        self.navigate(f'/jobcard/{card_id}/ledger')
        self.wait_for("!!document.querySelector('.timeline')")
        self.assertFalse(self.script("return !!document.querySelector('.payment-panel')"))
        self.assertFalse(self.script(f"return !!document.querySelector('a[href=\"/edit/jobcard/{card_id}\"]')"))

    def test_all_outworker_jobs_payment_filter_and_direct_edit(self):
        from payroll_service import save_rate, payroll_preview, issue_payroll
        save_rate(self.product.id,'','5.5','new','all-jobs-rate',self.admin)
        unpaid=add_manual_jobcard(self.manual_payload(pieces=10,count=1),self.admin,'browse-unpaid')['jobData']['jobId']
        partial=add_manual_jobcard(self.manual_payload(pieces=10,count=1),self.admin,'browse-partial')['jobData']['jobId']
        in_move_entery(self.return_payload(partial,5),self.admin,'browse-return')
        preview=payroll_preview(self.worker.id,[partial],'0')
        issue_payroll(self.worker.id,[partial],'0',preview['version'],'Cash','','','browse-pay',self.admin)
        self.navigate('/outworker_report')
        self.click('a[href="/outworker/jobs"]')
        self.wait_for("!!document.querySelector('#all-jobs-worker')")
        self.type('#all-jobs-worker',str(self.worker.id))
        self.click('.ow-all-jobs-picker button')
        self.wait_for("document.querySelectorAll('.ow-job-entry').length===2")
        self.assertIn('Partially paid',self.script('return document.body.textContent'))
        self.assertIn('5 / 10 pieces paid',self.script('return document.body.textContent'))
        self.script("document.querySelector('#job-payment-filter').value='partial'")
        self.click('.ow-all-jobs-picker button')
        self.wait_for("document.querySelectorAll('.ow-job-entry').length===1")
        self.assertEqual(self.script("return document.querySelector('.ow-job-entry').dataset.jobId"),str(partial))
        self.command('/window/rect',{'width':390,'height':844})
        self.assertTrue(self.script("return document.documentElement.scrollWidth<=innerWidth+1"))
        self.navigate(f'/outworker/jobs?worker_id={self.worker.id}')
        self.wait_for("document.querySelectorAll('.ow-job-entry').length===2")
        self.click(f'a.ow-edit-job[href="/edit/jobcard/{unpaid}"]')
        self.wait_for(f"location.pathname==='/edit/jobcard/{unpaid}'")
        self.assertFalse(self.script("return document.querySelector('.edit-fields').disabled"))

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
            self.click('#payrollSelectionForm button[type="submit"]')
            self.wait_for("document.querySelector('#payroll-local-review').open")
            self.assertIn('paying 5 pieces', self.script("return document.querySelector('#payrollLocalBreakdown').textContent"))
            self.click('#payrollLocalConfirm')
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

    def test_return_save_stays_on_job_with_preview_and_no_blob_window(self):
        from modes import Jobmovement
        card_id = add_manual_jobcard(self.manual_payload(pieces=10,count=1), self.admin, 'receipt-job')['jobData']['jobId']
        self.navigate(f'/job_retun?jobcard_id={card_id}')
        self.script("window.open=()=>{throw new Error('Unexpected popup')};URL.createObjectURL=()=>{throw new Error('Unexpected blob')}")
        self.script("""
            window.returnAlerts=[];window.alert=message=>window.returnAlerts.push(message);
            const realFetch=window.fetch.bind(window);let loseResponse=true;
            window.fetch=async (...args)=>{
                const response=await realFetch(...args);
                if(args[0]==='/summit-retune' && loseResponse){loseResponse=false;throw new TypeError('Lost after commit');}
                return response;
            };
        """)
        self.type('.return-input', '3')
        self.click('.btn-submit')
        self.wait_for("window.returnAlerts.length===1")
        self.click('.btn-submit')
        self.wait_for("!!document.querySelector('#savedReturnPreview')")
        self.active('#savedReturnPreview')
        self.assertIn('3 pieces', self.script("return document.querySelector('#savedReturnPreview').textContent"))
        self.assertIn(f'/job_retun?jobcard_id={card_id}', self.script('return location.href'))
        self.assertEqual(self.script("return document.querySelector('.return-input').dataset.remaining"), '7')
        self.assertEqual(len(self.command('/window/handles')), 1)
        self.type('.return-input', '7')
        self.click('.btn-submit')
        self.wait_for("document.querySelector('#savedReturnPreview')?.textContent.includes('7 pieces')")
        self.assertFalse(self.script("return !!document.querySelector('.return-input')"))
        self.assertEqual(len(self.command('/window/handles')), 1)
        db.session.expire_all()
        self.assertEqual(Jobmovement.query.filter_by(flow_type='IN').count(), 2)
        self.assertEqual(self.job_return_print.call_count, 2)
        self.click('.saved-return-edit')
        self.wait_for(f"location.pathname==='/edit/jobcard/{card_id}'")

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
        self.script("window.open=()=>{throw new Error('Unexpected popup')};URL.createObjectURL=()=>{throw new Error('Unexpected blob')}")
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

    def test_worker_kept_save_stays_embedded_and_preserves_other_job_drafts(self):
        from kept_products import save_product_value
        from modes import JobKeptProduct
        save_product_value(self.product.id, '120', 0, 'inline-price', self.admin)
        ids=[add_manual_jobcard(self.manual_payload(pieces=10,count=1),self.admin,
             f'inline-{index}')['jobData']['jobId'] for index in range(2)]
        self.navigate(f'/returns/outworker?worker_id={self.worker.id}')
        def enter_job(index):
            self.command('/frame',{'id':None})
            self.script(f"document.querySelectorAll('.return-job-frame')[{index}].scrollIntoView()")
            element=self.element(f'[data-job-id="{ids[index]}"] iframe')
            self.command('/frame',{'id':{'element-6066-11e4-a52e-4f735466cecf':element}})
            self.wait_for("!!document.querySelector('.return-input')")
        enter_job(1)
        self.type('.return-input','7')
        enter_job(0)
        # Keyboard expansion is stable even when Firefox scrolls a nested frame
        # behind the host page's fixed navigation during pointer targeting.
        self.assertFalse(self.script("return document.querySelector('#kept-pieces').open"))
        self.type('#kept-pieces > summary','\ue007')
        self.wait_for("document.querySelector('#kept-pieces').open && frameElement.clientHeight >= document.querySelector('main').getBoundingClientRect().height")
        self.type('details.kept-item summary','\ue007')
        self.wait_for("document.querySelector('details.kept-item').open && frameElement.clientHeight >= document.querySelector('main').getBoundingClientRect().height")
        self.type('.kept-product-form [name=pieces]','2')
        self.type('#kept-pieces > summary','\ue007')
        self.assertFalse(self.script("return document.querySelector('#kept-pieces').open"))
        self.type('#kept-pieces > summary','\ue007')
        self.wait_for("document.querySelector('#kept-pieces').open && frameElement.clientHeight >= document.querySelector('main').getBoundingClientRect().height")
        self.assertEqual(self.script("return document.querySelector('.kept-product-form [name=pieces]').value"),'2')
        self.wait_for("document.querySelector('.kept-recovery-preview').textContent.includes('240.00')")
        # A kept save must not silently discard this job's unfinished return.
        self.type('.return-input','3')
        self.type('.kept-product-form button[type=submit]','\ue007')
        self.wait_for("document.querySelector('.kept-recovery-preview').textContent.includes('Save or clear')")
        self.script("document.querySelector('.return-input').value=''")
        self.type('.kept-product-form button[type=submit]','\ue007')
        self.wait_for("document.body.textContent.includes('2 kept pieces recorded')")
        self.assertIn('embedded=1',self.script('return location.search'))
        self.assertEqual(self.script("return document.querySelectorAll('[aria-label=\"Main navigation\"]').length"),0)
        self.command('/frame',{'id':None})
        self.wait_for("document.querySelector('#open-return-pieces').textContent==='18'")
        self.assertEqual(self.script("return document.querySelectorAll('[aria-label=\"Main navigation\"]').length"),1)
        self.assertIn('/returns/outworker',self.script('return location.pathname'))
        enter_job(1)
        self.assertEqual(self.script("return document.querySelector('.return-input').value"),'7')
        self.command('/frame',{'id':None})
        self.command('/window/rect', {'width':390, 'height':844})
        self.assertTrue(self.script("return document.documentElement.scrollWidth<=innerWidth+1"))
        db.session.expire_all()
        self.assertEqual(JobKeptProduct.query.one().amount_paise,24000)

    def test_dashboard_carried_balance_worker_drilldown_sort_and_mobile(self):
        from datetime import datetime
        from modes import Jobcard, Jobmovement
        card_id=add_manual_jobcard(self.manual_payload(pieces=178,count=1),self.admin,'balance-browser')['jobData']['jobId']
        in_move_entery(self.return_payload(card_id,149),self.admin,'balance-return')
        db.session.get(Jobcard,card_id).date=datetime(2026,11,8)
        for row in Jobmovement.query.filter_by(jobcard=str(card_id)):
            row.date=datetime(2026,11,8 if row.flow_type=='OUT' else 9)
        db.session.commit()
        query='date_from=2026-11-11&date_to=2026-11-17&kind=opening'
        self.navigate('/dashboard/movements?'+query)
        self.wait_for("!!document.querySelector('.movement-worker-card')")
        self.assertFalse(self.script("return document.querySelector('.movement-worker-card').open"))
        self.assertIn('29 left',self.script("return document.querySelector('.movement-worker-products').textContent"))
        self.click('.movement-worker-card > summary')
        self.wait_for("document.querySelector('.movement-worker-card').open")
        self.assertIn('3',self.script("return document.querySelector('.movement-age').textContent"))
        self.assertTrue(self.script(f"return !!document.querySelector('a[href=\"/edit/jobcard/{card_id}\"]')"))
        self.click('.movement-view-switch a:last-child')
        self.wait_for("location.search.includes('view=jobs')")
        self.assertFalse(self.script("return !!document.querySelector('.movement-worker-card')"))
        self.type('[name=product]','vimal')
        self.script("document.querySelector('[name=sort]').value='quantity_desc'")
        self.click('.movement-date-form button')
        self.wait_for("location.search.includes('sort=quantity_desc')")
        self.assertEqual(self.script("return document.querySelector('[name=product]').value"),'vimal')
        self.assertIn('29',self.script("return document.querySelector('.movement-job-table').textContent"))
        self.command('/window/rect',{'width':390,'height':844})
        self.assertTrue(self.script("return document.documentElement.scrollWidth<=innerWidth+1"))
        self.script("window.dispatchEvent(new Event('beforeprint'))")
        self.assertTrue(self.script("return document.querySelector('.movement-raw').open"))
        self.script("window.dispatchEvent(new Event('afterprint'))")
        self.assertFalse(self.script("return document.querySelector('.movement-raw').open"))

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
        self.wait_for("location.pathname==='/dashboard/movements' && document.querySelector('.ui-heading h1')?.textContent==='Outflow / given details'")
        self.assertIn('Outflow / given details',self.script('return document.body.textContent'))
        self.assertIn(f'#{card_id}',self.script('return document.body.textContent'))
