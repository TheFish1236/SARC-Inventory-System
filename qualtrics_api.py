import os
import time
import requests
import zipfile
import io
import json
from dotenv import load_dotenv
from requests.exceptions import ConnectionError
from datetime import datetime, timedelta, timezone

load_dotenv()

api_key = os.getenv("QUALTRICS_API_TOKEN")
data_center = os.getenv("DATA_CENTER")

# Load both Survey IDs!
checkout_id = os.getenv("SURVEY_CHECKOUT")
return_id = os.getenv("SURVEY_RETURN")

headers = {
    "x-api-token": api_key,
    "Content-Type": "application/json"
}

def get_survey_data(target_survey_id):
    print("\nPackaging data from Qualtrics...")
    export_url = f"https://{data_center}/API/v3/surveys/{target_survey_id}/export-responses"
    payload = {"format": "json"}
    
    response = requests.post(export_url, json=payload, headers=headers)
    progress_id = response.json()['result']['progressId']

    progress_url = f"https://{data_center}/API/v3/surveys/{target_survey_id}/export-responses/{progress_id}"
    while True:
        status_res = requests.get(progress_url, headers=headers).json()
        status = status_res['result']['status']
        if status == "complete":
            file_id = status_res['result']['fileId']
            break
        elif status == "failed":
            print("Qualtrics export failed.")
            return None
        time.sleep(1)

    print("Downloading and parsing responses...")
    download_url = f"https://{data_center}/API/v3/surveys/{target_survey_id}/export-responses/{file_id}/file"
    file_res = requests.get(download_url, headers=headers)
    
    zip_file = zipfile.ZipFile(io.BytesIO(file_res.content))
    json_filename = zip_file.namelist()[0]
    
    survey_data = json.loads(zip_file.read(json_filename))
    return survey_data['responses']

def verify_student(target_ucf_id):
    try:
        responses = get_survey_data(checkout_id)
    except ConnectionError:
        print("\nCRITICAL: No Internet Connection Detected!")
        return False
        
    if not responses:
        return False
    
    print(f"\nSearching for completed CHECK-OUT agreements by UCF ID: {target_ucf_id}...")
    for response in responses:
        values = response['values']
        
        # Match UCF ID (with .zfill(7) protection)
        if str(values.get('QID1_3')).zfill(7) == str(target_ucf_id).zfill(7):
            if values.get('finished') == 1:
                end_date_str = values.get('endDate')

                if end_date_str:
                    try:
                        # Clean the ISO timestamp for Python
                        clean_date = end_date_str.replace('Z', '+00:00')
                        submit_time = datetime.fromisoformat(clean_date)
                        now = datetime.now(timezone.utc)
                        
                        # If the submission is older than 12 hours, reject it!
                        if now - submit_time > timedelta(hours=12):
                            print(f"ERROR: Agreement found, but it is EXPIRED (submitted {end_date_str}).")
                            return False
                    except Exception as e:
                        print(f"Warning: Could not verify timestamp: {e}")
                
                first_name = values.get('QID1_1', 'Unknown')
                last_name = values.get('QID1_2', 'Unknown')
                full_name = f"{first_name} {last_name}".strip()
                print(f"SUCCESS: {full_name}'s agreement is signed and fully verified.")
                return True, full_name
            
            else:
                print(f"WARNING: Found {target_ucf_id}, but they didn't hit submit!")
                return False, None
                
    return False, None

def verify_return(target_ucf_id):
    try:
        responses = get_survey_data(return_id)
    except ConnectionError:
        print("\nCRITICAL: No Internet Connection Detected!")
        return False
        
    if not responses:
        return False
    
    print(f"\nSearching for completed RETURN surveys by UCF ID: {target_ucf_id}...")
    for response in responses:
        values = response['values']
        if str(values.get('QID1_3')).zfill(7) == str(target_ucf_id).zfill(7):
            if values.get('finished') == 1:
                return True
            else:
                print(f"WARNING: Found {target_ucf_id}, but they didn't hit submit!")
                return False
    return False