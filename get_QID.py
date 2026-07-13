import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("QUALTRICS_API_TOKEN")
data_center = os.getenv("DATA_CENTER")

request_id = os.getenv("SURVEY_REQUEST")
checkout_id = os.getenv("SURVEY_CHECKOUT")
return_id = os.getenv("SURVEY_RETURN")

survey = input("pick survey: (return_id/checkout_id/request_id): ")

url = f"https://{data_center}/API/v3/survey-definitions/{survey}"
headers = {"x-api-token": api_key}

def clean_text(html_text):
    # This Regex magic strips away all HTML tags
    text = re.sub('<[^<]+>', '', html_text)
    # This removes weird line breaks and spaces
    return " ".join(text.split())

print("Fetching Survey Blueprint...\n")
response = requests.get(url, headers=headers)

if response.status_code == 200:
    data = response.json()
    questions = data['result']['Questions']
    
    for qid, q_info in questions.items():
        text = clean_text(q_info['QuestionText'])
        print(f"\n{qid} -> {text}")
        
        if 'Choices' in q_info:
            for choice_id, choice_info in q_info['Choices'].items():
                choice_text = clean_text(choice_info.get('Display', ''))
                print(f"    *** Sub-field: {qid}_{choice_id} -> {choice_text}")
else:
    print(f"Failed: {response.status_code}")
    print(response.text)