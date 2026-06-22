import os
import time
import requests
import zipfile
import io
import json
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("QUALTRICS_API_TOKEN")
data_center = os.getenv("DATA_CENTER")
survey_id = os.getenv("SURVEY_CHECKOUT")

headers = {
    "x-api-token": api_key,
    "Content-Type": "application/json"
}

def get_survey_data():
    print("\nPackaging data from Qualtrics...")
    
    # Step 1: Request Export
    export_url = f"https://{data_center}/API/v3/surveys/{survey_id}/export-responses"
    payload = {"format": "json"}
    
    response = requests.post(export_url, json=payload, headers=headers)
    progress_id = response.json()['result']['progressId']

    # Step 2: Wait for Qualtrics to build the file
    progress_url = f"https://{data_center}/API/v3/surveys/{survey_id}/export-responses/{progress_id}"
    while True:
        status_res = requests.get(progress_url, headers=headers).json()
        status = status_res['result']['status']
        if status == "complete":
            file_id = status_res['result']['fileId']
            break
        elif status == "failed":
            print("Qualtrics export failed.")
            return None
        time.sleep(1) # wait 1 second and check again

    # Step 3: Download and Extract the ZIP file in memory
    print("Downloading and parsing responses...")
    download_url = f"https://{data_center}/API/v3/surveys/{survey_id}/export-responses/{file_id}/file"
    file_res = requests.get(download_url, headers=headers)
    
    # Unzip the file
    zip_file = zipfile.ZipFile(io.BytesIO(file_res.content))
    json_filename = zip_file.namelist()[0]
    
    # Load the raw JSON data
    survey_data = json.loads(zip_file.read(json_filename))
    return survey_data['responses']

def verify_student(target_ucf_id):
    responses = get_survey_data()
    if not responses:
        return False
    
    print(f"\nSearching for completed agreements by UCF ID: {target_ucf_id}...")
    
    # Loop through all responses
    for response in responses:
        values = response['values']
        
        # Check if the UCF ID matches
        if str(values.get('QID1_3')) == str(target_ucf_id):
            
            # Make sure they actually hit submit (1 = Finished, 0 = Abandoned)
            if values.get('finished') == 1:
                first_name = values.get('QID1_1', 'Unknown')
                last_name = values.get('QID1_2', 'Unknown')
                
                print(f"SUCCESS: {first_name} {last_name}'s agreement is signed and fully verified.")
                print("   Ready to scan equipment.")
                return True
            else:
                print(f"WARNING: Found {target_ucf_id}, but they closed the browser before finishing!")
                return False
                
    print(f"ERROR: UCF ID {target_ucf_id} has NOT filled out the Check-Out form.")
    return False

if __name__ == "__main__":
    test_id = input("Swipe Card (or type UCF ID): ")
    verify_student(test_id)