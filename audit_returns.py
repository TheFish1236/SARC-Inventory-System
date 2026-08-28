import sqlite3
import os
from qualtrics_api import get_survey_data

def get_db_returns():
    # Fetches all returned items from the local SQLite database.
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()
    
    # We want the User's ID, Name, Email, and what they returned
    cursor.execute('''
        SELECT l.ucf_id, u.name, u.email, e.equipment_type, l.time_in
        FROM loans l
        JOIN users u ON l.ucf_id = u.ucf_id
        JOIN equipment e ON l.barcode_id = e.barcode_id
        WHERE l.time_in IS NOT NULL
        ORDER BY l.time_in DESC
    ''')
    returns = cursor.fetchall()
    conn.close()
    return returns

def audit_missing_paperwork():
    print("\n--- INITIATING QUALTRICS RETURN AUDIT ---")
    
    # 1. Get the raw survey responses (Just ONE API Call!)
    return_survey_id = os.getenv("SURVEY_RETURN")
    responses = get_survey_data(return_survey_id)
    
    if responses is None:
        print(" ERROR: Could not fetch Qualtrics data. Aborting audit.")
        return
        
    print(" Qualtrics data downloaded successfully.")
    print(" Cross-referencing database records...\n")
    
    # 2. Extract every UCF ID that submitted a valid return form
    # Using a Python 'set' makes looking up IDs instant (O(1) time complexity!)
    signed_ucf_ids = set()
    for response in responses:
        values = response['values']
        if values.get('finished') == 1:
            ucf_id_raw = str(values.get('QID1_3', '')).zfill(7)
            signed_ucf_ids.add(ucf_id_raw)
            
    # 3. Pull our local database returns
    db_returns = get_db_returns()
    
    missing_paperwork = []
    
    # 4. The Audit Loop
    for record in db_returns:
        ucf_id, name, email, eq_type, time_in = record
        
        # If their ID is NOT in the Qualtrics set, they are busted.
        if str(ucf_id).zfill(7) not in signed_ucf_ids:
            # We ignore "Staff" overrides from our Ad-Hoc menu
            if ucf_id != "Staff":
                missing_paperwork.append(record)
                
    # 5. Print the Hit List
    if not missing_paperwork:
        print(" AUDIT PASSED: Every returned item has a matching Qualtrics signature!")
    else:
        print(" AUDIT FAILED: The following users skipped the Return Survey:\n")
        print(f"{'NAME':<20} | {'UCF ID':<10} | {'ITEM RETURNED':<15} | {'RETURN DATE'}")
        print("-" * 70)
        for record in missing_paperwork:
            ucf_id, name, email, eq_type, time_in = record
            # Slices the timestamp to just show the Date
            short_date = time_in.split(" ")[0] 
            print(f"{name:<20} | {ucf_id:<10} | {eq_type:<15} | {short_date}")
            
        print("\n Next Step: Email these users and request they complete the Return Survey.")

if __name__ == "__main__":
    audit_missing_paperwork()