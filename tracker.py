import sqlite3
import datetime
from qualtrics_api import verify_student
import re
import csv
import shutil
import os

def log_transaction(action, barcode, equipment_type, ucf_id, student_name):
    user_profile = os.environ.get('USERPROFILE')
    log_path = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - Technology Assistant", "Archived Tech Assistant Files", "Equipment Tracking", "SARC_History_Log.csv")
    
    file_exists = os.path.isfile(log_path)
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with open(log_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Timestamp', 'Action', 'Barcode ID', 'Equipment Type', 'UCF ID', 'Name'])
            writer.writerow([current_time, action, barcode, equipment_type, ucf_id, student_name])

    except PermissionError:
        print("Warning: History Log is open in Excel, could not append transaction.")

def backup_to_cloud():
    user_profile = os.environ.get('USERPROFILE')
    onedrive_csv = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - Technology Assistant", "Archived Tech Assistant Files", "Equipment Tracking", "SARC_Live_Inventory.csv")
    onedrive_db = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - Technology Assistant", "Archived Tech Assistant Files", "Equipment Tracking", "inventory_backup.db")
    
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT barcode_id, equipment_type, brand_model, status, current_ucf_id, current_name, last_updated, notes FROM serialized_assets")
    rows = cursor.fetchall()
    
    try:
        # 1. Back up the CSV for the Boss
        with open(onedrive_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Barcode ID', 'Type', 'Model', 'Status', 'UCF ID', 'Name', 'Last Updated', 'Notes'])
            writer.writerows(rows)
            
        # 2. Back up the raw DB
        shutil.copy2('inventory.db', onedrive_db)
        
        print("Live backups (CSV and DB) synced to OneDrive.")
        
    except PermissionError:
        print("\nWARNING: Could not update OneDrive. Someone has the file open!")
        print("Local database updated successfully. Cloud will catch up on the next scan.")
        
    except Exception as e:
        print(f"\nWARNING: Cloud sync failed: {e}")
        
    finally:
        conn.close()


def parse_ucf_id(raw_input):
    raw_input = raw_input.strip() 
    
    # 1. Did you manually type it?
    if raw_input.isdigit() and len(raw_input) == 7:
        return raw_input
        
    # 2. Was it a GOOD card swipe? (Track 1 always has '^')
    if '^' in raw_input:
        parts = raw_input.split('^')
        if len(parts) >= 3: # Make sure there are at least 3 parts
            # Look for the numbers right at the start of parts[2]
            match = re.search(r'^\d+', parts[2])
            if match:
                long_num = match.group(0)
                return long_num[-7:]
                
    # 3. Was it a BAD card swipe?
    if '^' not in raw_input:
        print("Bad swipe! Please try again.")
        return None
                
    return raw_input

def connect_db():
    return sqlite3.connect('inventory.db')

def checkout_item():
    raw_swipe = input("\nSwipe Card (or type 7-digit UCF ID): ")

    if raw_swipe.upper().startswith("SARC-"):
        print("You scanned an equipment barcode. Please swipe the UCF ID card first.")
        return
    
    ucf_id = parse_ucf_id(raw_swipe)
    if ucf_id is None:
        return
    
    # 1. API Magic: Check Qualtrics
    print(f"Verifying UCFID: {ucf_id} with Qualtrics...")
    
    # Unpack the two variables returned by the API
    is_verified, student_name = verify_student(ucf_id)
    action_type = "CHECK-OUT"
    
    if not is_verified:
        print("Agreement not found in Qualtrics (or system offline).")
        force = input("OVERRIDE: Do you want to FORCE check-out anyway? (Y/N): ")
        if force.strip().upper() == 'Y':
            print("Forcing Checkout...")
            # Ask for the name since we don't have the form!
            student_name = input("Enter Student First and Last Name: ").strip()
            action_type = "CHECK-OUT (OVERRIDE)"
        else:
            print("Checkout aborted.")
            return

    # 2. Scanner Magic: Assign the item
    barcode = input("Scan Equipment Barcode: ")
    
    conn = connect_db()
    cursor = conn.cursor()
    
    # Check if the item exists (Notice we added 'notes' to the SELECT statement!)
    cursor.execute("SELECT status, equipment_type, brand_model, notes FROM serialized_assets WHERE barcode_id = ?", (barcode,))
    result = cursor.fetchone()
    
    if result is None:
        print(f"ERROR: Barcode '{barcode}' not found in database.")
        return
        
    current_status, eq_type, model, notes = result
    
    if current_status != 'Available':
        print(f"WARNING: {barcode} cannot be checked out. Current status: {current_status}")
        return
        
    # --- NOTES WARNING (For Study Union / Restrictions) ---
    if notes and notes.strip():
        print(f"\nALERT ON ITEM: {notes}")
        confirm = input("Are you sure you want to proceed with this checkout? (Y/N): ")
        if confirm.strip().upper() != 'Y':
            print("Checkout aborted by user.")
            return
        
    # 3. Database Magic: Update the record
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        UPDATE serialized_assets 
        SET status = 'Checked Out', current_ucf_id = ?, current_name = ?, last_updated = ? 
        WHERE barcode_id = ?
    ''', (ucf_id, student_name, current_time, barcode))
    
    conn.commit()
    conn.close()
    print(f"SUCCESS: {eq_type} ({model}) checked out to {student_name} ({ucf_id}).")
    log_transaction("CHECK-OUT", barcode, eq_type, ucf_id, student_name)
    backup_to_cloud()


def return_item():
    barcode = input("\nScan Equipment Barcode to Return: ")
    
    conn = connect_db()
    cursor = conn.cursor()
    
    # 1. Look up the item
    cursor.execute("SELECT status, equipment_type, current_ucf_id, current_name FROM serialized_assets WHERE barcode_id = ?", (barcode,))
    result = cursor.fetchone()
    
    if result is None:
        print(f"ERROR: Barcode '{barcode}' not found in database.")
        return
        
    current_status, eq_type, previous_owner, previous_owner_name = result
    
    if current_status == 'Available':
        print(f"WARNING: {barcode} is already marked as Available in the closet.")
        return
        
    # 2. Update the database (Instant Return)
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        UPDATE serialized_assets 
        SET status = 'Available', current_ucf_id = NULL, current_name = NULL, last_updated = ? 
        WHERE barcode_id = ?
    ''', (current_time, barcode))
    
    conn.commit()
    conn.close()
    
    print(f"SUCCESS: {eq_type} returned successfully. (Previously held by {previous_owner_name})")
    print("Instruct the student to scan the QR code to submit the Return Survey on their way out!")
    
    # 3. Log the event and backup
    log_transaction("RETURN", barcode, eq_type, previous_owner, previous_owner_name)
    backup_to_cloud()

def main():
    print("\nSARC INVENTORY MANAGEMENT SYSTEM")
    
    while True:
        print("\nMain Menu:")
        print("1. Check-Out Equipment")
        print("2. Return Equipment")
        print("3. Exit")
        
        choice = input("\nSelect an option (1-3): ")
        
        if choice == '1':
            checkout_item()
        elif choice == '2':
            return_item()
        elif choice == '3':
            print("Shutting down tracker. Goodbye!")
            break
        else:
            print("Invalid choice. Please type 1, 2, or 3.")

if __name__ == "__main__":
    main()