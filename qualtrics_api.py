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
checkout_id = os.getenv("SURVEY_CHECKOUT")

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
        return "OFFLINE", None, None, None
        
    if not responses:
        return "NOT_FOUND", None, None, None
    
    best_match_values = None
    is_fresh = False
    
    print(f"\nSearching for completed CHECK-OUT agreements by UCF ID: {target_ucf_id}...")
    for response in responses:
        values = response['values']
        
        # Match UCF ID (with .zfill(7) protection)
        if str(values.get('QID1_3')).zfill(7) == str(target_ucf_id).zfill(7):
            if values.get('finished') == 1:
                # Keep track of this as a match
                best_match_values = values
                end_date_str = values.get('endDate')

                if end_date_str:
                    try:
                        clean_date = end_date_str.replace('Z', '+00:00')
                        submit_time = datetime.fromisoformat(clean_date)
                        now = datetime.now(timezone.utc)
                        
                        # If we find a fresh submission, we immediately use it and stop searching
                        if now - submit_time <= timedelta(hours=12):
                            is_fresh = True
                            break
                        
                    except Exception as e:
                        print(f"Warning: Could not verify timestamp: {e}")
                
    if best_match_values:
        first_name = best_match_values.get('QID1_1', 'Unknown')
        last_name = best_match_values.get('QID1_2', 'Unknown')
        full_name = f"{first_name} {last_name}".strip()
        email = best_match_values.get('QID1_5', 'Unknown')

        raw_position = str(values.get('QID26', 'Unknown'))
        position_text = values.get('QID26_5_TEXT', '').strip()
        if position_text:
            position = position_text
        elif raw_position == '2':
            position = 'Tutor'
        elif raw_position == '3':
            position = 'SI Leader'
        elif raw_position == '5':
            position = 'Other'
        else:
            position = raw_position
        
        
        if is_fresh:
            print(f"SUCCESS: {full_name} ({position}) agreement verified.")
            return "VERIFIED", full_name, position, email
        else:
            return "EXPIRED", full_name, position, email

    return "NOT_FOUND", None, None, None