import pandas as pd
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




###retun