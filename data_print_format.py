import csv
from io import StringIO
import pandas as pd
import re
from pathlib import Path
import os
import tempfile
from flask import current_app, has_app_context

PRINT_ROOT = Path(__file__).resolve().parent / "to_print"


def _output_path(kind, filename):
    configured = current_app.config.get('LABEL_PRINT_ROOT') if has_app_context() else None
    directory = Path(configured or PRINT_ROOT) / kind
    directory.mkdir(parents=True, exist_ok=True)
    return directory / filename
##### OUTWORKER OR

# need date in this format {
#     ID:101
# NAME:RAVI
#ADDRESS:DHAMTERI
# QR:DATA
# }
def outworker_qr_print(data):
    pd_data = pd.DataFrame([{
        "id":data.id,
        "name":data.name,
        "address":data.adders,
        "qr_code":f"{data.id}***{data.name}--{data.adders}/-"
    }])
    _write_label_csv(f"{data.id}.csv", pd_data.to_csv(index=False), kind='outworker')
    return 101




###### bunle OR

def buldel_qr_print(data):
        for d in data:
            pd_data = pd.DataFrame([d])
            pd_data.to_csv(_output_path("bundle", f"{d['id']}.csv"), index=False)
        return 101



######## jobCARD
def job_cade_print(data):
    return build_custom_csvs_pandas(data)


def _write_label_csv(filename, csv_string, kind='jobcard'):
    """Publish complete files so the label watcher never reads a partial CSV."""
    target = _output_path(kind, filename)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                         prefix='.', suffix='.tmp', dir=target.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(csv_string)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_payroll_bill_csv(payroll, preview, repayments, remaining_advance):
    """Build a stable CSV from the payment snapshot."""
    def money(paise):
        if paise is None:
            return ''
        sign = '-' if paise < 0 else ''
        rupees, cents = divmod(abs(paise), 100)
        return f'{sign}{rupees}.{cents:02d}'

    def text(value):
        value = str(value or '')
        # Keep user-entered text from being evaluated as a formula in a spreadsheet.
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')) else value

    output = StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=[
        'record_type', 'payroll_id', 'saved_at', 'worker_id', 'outworker', 'recorded_by',
        'method', 'reference', 'note', 'jobs', 'jobcard_id', 'job_issued_date',
        'product_id', 'product', 'bundle_type', 'pieces', 'given', 'returned', 'kept',
        'previously_paid', 'awaiting_return', 'rate_per_piece', 'rate_source',
        'advance_id', 'recovery_id', 'amount', 'gross_payroll', 'advance_deduction',
        'final_payment', 'advance_received_back', 'cash_to_take', 'advance_carried_forward',
    ])
    writer.writeheader()
    common = dict(payroll_id=payroll.id, saved_at=payroll.paid_at.isoformat(sep=' ', timespec='seconds'),
                  worker_id=payroll.worker_id, outworker=text(payroll.worker_name),
                  recorded_by=text(payroll.recorded_by), method=payroll.method,
                  reference=text(payroll.reference), note=text(payroll.note))

    def row(record_type, **fields):
        writer.writerow(dict(record_type=record_type, **common, **fields))

    received = sum(receipt['amount_paise'] for receipt in repayments)
    row('payroll', jobs=len(preview['jobs']), pieces=preview['pieces'],
        gross_payroll=money(payroll.gross_paise), advance_deduction=money(payroll.deduction_paise),
        final_payment=money(payroll.net_paise), advance_received_back=money(received),
        cash_to_take=money(received - payroll.net_paise) if received else '',
        advance_carried_forward=money(remaining_advance))
    for job in preview['jobs']:
        job_fields = dict(jobcard_id=job['id'], job_issued_date=job['date'].isoformat() if job.get('date') else '')
        row('job', **job_fields, pieces=job['pieces'], given=job.get('given'), returned=job.get('returned'),
            kept=job.get('kept'), previously_paid=job.get('already_paid'), awaiting_return=job.get('pending_return'),
            amount=money(job['gross_paise']))
        for line in job['lines']:
            balances = [line.get(key) for key in ('given', 'returned', 'kept')]
            pending = balances[0] - balances[1] - balances[2] if all(isinstance(qty, int) for qty in balances) else None
            row('product', **job_fields, product_id=line.get('product_id'), product=text(line.get('product')),
                bundle_type=text(line.get('type')), pieces=line.get('pieces'), given=line.get('given'),
                returned=line.get('returned'), kept=line.get('kept'), previously_paid=line.get('already_paid'),
                awaiting_return=pending, rate_per_piece=line.get('rate'), rate_source=line.get('rate_source'),
                amount=money(line.get('amount_paise')))
    if payroll.deduction_paise:
        for recovery in preview['advance_recoveries']:
            row('advance_deduction', advance_id=recovery['advance_id'], amount=money(recovery['amount_paise']))
    for receipt in repayments:
        row('advance_repayment', advance_id=receipt['advance_id'],
            recovery_id=receipt['id'], amount=money(receipt['amount_paise']))
    return output.getvalue()


def payroll_bill_csv(payroll_id, content):
    _write_label_csv(f'payroll_{payroll_id}.csv', content, kind='payroll')


def existing_payroll_bill_csv(payroll_id):
    try:
        with _output_path('payroll', f'payroll_{payroll_id}.csv').open(encoding='utf-8', newline='') as source:
            return source.read()
    except FileNotFoundError:
        return None


def clean_text(text):
        return re.sub(r'[^a-zA-Z0-9]+', '_', str(text)).strip("_")

def job_return_print(data):
    """Use the existing label column order, in a separate return print queue."""
    job = data['jobData']
    items = []
    for item in job['items']:
        rows = item.get('calculation_rows') if item.get('entry_method') == 'calculator' else None
        for row in rows or [{'pieces': item['returned'], 'count': 1}]:
            items.append({'item_id': item['item_id'], 'name_of_prduct': item['name_of_product'],
                          'type': item['type'], 'qty': row['pieces'] * row['count'],
                          'pieces_per_bundle': row['pieces'], 'bundle_count': row['count']})
    return build_custom_csvs_pandas({'jobData': {
        **job, 'jobId': job['jobcard_id'], 'items': items,
    }}, kind='job+retun', filename_prefix=f"return_{job['return_id']}_", movement_label='received by')


def build_custom_csvs_pandas(data, kind='jobcard', filename_prefix='', movement_label='given by'):
        job = data["jobData"]

        job_id = job["jobId"]
        party = clean_text(job["party"])
        username = clean_text(job["username"])
        date = clean_text(job["date"])

        df = pd.DataFrame(job["items"])
        # Manual rows represent several bundles in one line; scanned rows represent one.
        if "pieces_per_bundle" not in df:
            df["pieces_per_bundle"] = df["qty"]
        else:
            df["pieces_per_bundle"] = df["pieces_per_bundle"].fillna(df["qty"])
        if "bundle_count" not in df:
            df["bundle_count"] = 1
        else:
            df["bundle_count"] = df["bundle_count"].fillna(1)
        df["pieces_per_bundle"] = df["pieces_per_bundle"].astype(int)
        df["bundle_count"] = df["bundle_count"].astype(int)

        # 🔹 STEP 1: GROUP BY PRODUCT + TYPE ONLY
        grouped = (
            df.groupby(["name_of_prduct", "type"])
            .agg(
                qty_counts=("pieces_per_bundle", lambda x: df.loc[x.index].groupby("pieces_per_bundle")["bundle_count"].sum().to_dict()),
                ids=("item_id", lambda x: list(x))
            )
            .reset_index()
        )

        final_products = []

        # 🔹 STEP 2: BUILD PATTERN LIKE 36x4 28x4
        for _, row in grouped.iterrows():
            name = row["name_of_prduct"]
            typ = row["type"]
            qty_counts = row["qty_counts"]  # {36:4, 28:4, 80:6}
            ids = row["ids"]

            # 🔥 build pattern array
            pattern_arr = [f"{qty}x{count}" for qty, count in qty_counts.items()]
            quantity_pairs = list(qty_counts.items())

            # total (optional)
            total = sum(qty * count for qty, count in qty_counts.items())

            # 🔹 STEP 3: SPLIT INTO BLOCKS (MAX 10 ENTRIES)
            for i in range(0, len(pattern_arr), 10):
                chunk = pattern_arr[i:i + 10]

                line1 = "    ".join(chunk[:4])
                line2 = "    ".join(chunk[4:10])

                final_products.append({
                    "Product": name,
                    "Type": typ,
                    "Line1": line1,
                    "Line2": line2,
                    "Total": sum(qty * count for qty, count in quantity_pairs[i:i + 10])
                })

        final_df = pd.DataFrame(final_products)

        # 🔹 STEP 4: 2 PRODUCTS PER PAGE
        pages = [
            final_df.iloc[i:i + 2]
            for i in range(0, len(final_df), 2)
        ]

        outputs = []

        for page_index, page_df in enumerate(pages, start=1):

            base = {
                "job_number": job_id,
                "date": job["date"],
                "name": f'{job["party"]} {movement_label} {job["username"]}',
                "page": page_index,
            }

            row = base.copy()

            for idx, (_, r) in enumerate(page_df.iterrows(), start=1):
                serial_no = (page_index - 1) * 2 + idx

                row.update({
                    f"No_{idx}": serial_no,
                    f"Product_{idx}": r["Product"],
                    f"Type_{idx}": r["Type"],
                    f"Pattern_{idx}_line1": r["Line1"],
                    f"Pattern_{idx}_line2": r["Line2"],
                    f"Total_{idx}": r["Total"],
                })

            if len(page_df) == 1:
                row.update({
                    "No_2": "",
                    "Product_2": "",
                    "Type_2": "",
                    "Pattern_2_line1": "",
                    "Pattern_2_line2": "",
                    "Total_2": "",
                })

            out_df = pd.DataFrame([row])
            filename = f"{filename_prefix}{job_id}_{party}_{username}_{date}_page_{page_index}.csv"
            csv_string = out_df.to_csv(index=False)
            _write_label_csv(filename, csv_string, kind)



            outputs.append({
                "filename": filename,
                "csv": csv_string
            })

        return outputs



###retun
