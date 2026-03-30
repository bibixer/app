import pandas as pd
import re
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
    pd_data.to_csv(f"to_print/outworker/{data.id}.csv",index=False)
    return 101




###### bunle OR

def buldel_qr_print(data):
        for d in data:
            pd_data = pd.DataFrame([d])
            pd_data.to_csv(f"to_print/bundle/{d['id']}.csv", index=False)
        return 101



######## jobCARD
def job_cade_print(data):
    build_custom_csvs_pandas(data)


def clean_text(text):
        return re.sub(r'[^a-zA-Z0-9]+', '_', str(text)).strip("_")

def build_custom_csvs_pandas(data):
        job = data["jobData"]

        job_id = job["jobId"]
        party = clean_text(job["party"])
        username = clean_text(job["username"])
        date = clean_text(job["date"])

        df = pd.DataFrame(job["items"])

        # 🔹 STEP 1: GROUP BY PRODUCT + TYPE ONLY
        grouped = (
            df.groupby(["name_of_prduct", "type"])
            .agg(
                qty_counts=("qty", lambda x: x.value_counts().to_dict()),
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
                    "Total": total
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
                "name": f'{job["party"]} given by {job["username"]}',
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
            filename = f"{job_id}_{party}_{username}_{date}_page_{page_index}.csv"
            csv_string = out_df.to_csv(f"to_print/jobcard/{filename}",index=False)



            outputs.append({
                "filename": filename,
                "csv": csv_string
            })

        return outputs



###retun