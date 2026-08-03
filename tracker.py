import sqlite3
import datetime
from qualtrics_api import verify_student
import re
import csv
import shutil
import os

def log_transaction(action, barcode, equipment_type, ucf_id, student_name, position, email, duration):
    user_profile = os.environ.get('USERPROFILE')
    log_path = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - Technology Assistant", "Equipment Tracking", "Live_Data_Feeds", "SARC_History_Log.csv")
    
    file_exists = os.path.isfile(log_path)
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with open(log_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Timestamp', 'Action', 'Barcode ID', 'Equipment Type', 'UCF ID', 'Name', 'Position', 'Email', 'Duration'])
            writer.writerow([current_time, action, barcode, equipment_type, ucf_id, student_name, position, email, duration])

    except PermissionError:
        print("Warning: History Log is open in Excel, could not append transaction.")

def backup_to_cloud():
    user_profile = os.environ.get('USERPROFILE')
    onedrive_csv = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - Technology Assistant", "Equipment Tracking", "Live_Data_Feeds", "SARC_Live_Inventory.csv")
    
    # --- NEW 3RD DATA STREAM: BULK INVENTORY ---
    onedrive_bulk_csv = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - Technology Assistant", "Equipment Tracking", "Live_Data_Feeds", "SARC_Live_Bulk.csv")
    
    onedrive_db = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - Technology Assistant", "Equipment Tracking", "System_Backups", "inventory_backup.db")
    
    conn = connect_db()
    cursor = conn.cursor()
    
    try:
        # 1. Back up the Serialized CSV
        cursor.execute("SELECT barcode_id, equipment_type, brand_model, status, current_ucf_id, current_name, current_position, current_email, current_duration, last_updated, notes, attached_bulk_items FROM serialized_assets")
        rows = cursor.fetchall()
        with open(onedrive_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Barcode ID', 'Type', 'Model', 'Status', 'UCF ID', 'Name', 'Position', 'Email', 'Duration', 'Last Updated', 'Notes', 'Attached Bulk Items'])
            writer.writerows(rows)
            
        # 2. Back up the Bulk CSV
        cursor.execute("SELECT item_name, quantity, category, notes, last_updated FROM bulk_assets")
        bulk_rows = cursor.fetchall()
        with open(onedrive_bulk_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Item Name', 'Quantity', 'Category', 'Notes', 'Last Updated'])
            writer.writerows(bulk_rows)
            
        # 3. Back up the raw DB
        shutil.copy2('inventory.db', onedrive_db)
        print("Live backups (Serialized, Bulk, and DB) synced to OneDrive.")
        
    except PermissionError:
        print("\nWARNING: Could not update OneDrive. Someone has the file open!")
        print("Local database updated successfully. Cloud will catch up on the next scan.")
        
    except Exception as e:
        print(f"\nWARNING: Cloud sync failed: {e}")
        
    finally:
        conn.close()

def parse_ucf_id(raw_input):
    raw_input = raw_input.strip() 
    if raw_input.isdigit() and len(raw_input) == 7:
        return raw_input
    if '^' in raw_input:
        parts = raw_input.split('^')
        if len(parts) >= 3:
            match = re.search(r'^\d+', parts[2])
            if match:
                long_num = match.group(0)
                return long_num[-7:]
    if '^' not in raw_input:
        print("Bad swipe! Please try again.")
        return None
    return raw_input

def connect_db():
    return sqlite3.connect('inventory.db')

def handle_bulk_inventory():
    print("\n--- BULK INVENTORY MENU ---")
    print("1. Check-Out Bulk Item")
    print("2. Return Bulk Item")
    print("3. Cancel")
    
    action_choice = input("Select action (1-3): ").strip()
    if action_choice == '3':
        return
        
    is_checkout = (action_choice == '1')
    action_str = "CHECK-OUT (BULK)" if is_checkout else "RETURN (BULK)"

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT category FROM bulk_assets ORDER BY category")
    categories = [row[0] for row in cursor.fetchall()]

    if not categories:
        print("No bulk categories found in database.")
        conn.close()
        return

    print("\nCategories:")
    for i, cat in enumerate(categories, 1):
        print(f"{i}. {cat}")
        
    try:
        cat_idx = int(input("\nSelect category number: ")) - 1
        selected_category = categories[cat_idx]
    except (ValueError, IndexError):
        print("Invalid selection.")
        conn.close()
        return

    cursor.execute("SELECT item_name, quantity FROM bulk_assets WHERE category = ? ORDER BY item_name", (selected_category,))
    items = cursor.fetchall()

    print(f"\nItems in {selected_category}:")
    for i, (name, qty) in enumerate(items, 1):
        print(f"{i}. {name} ({qty} currently in stock)")
        
    try:
        item_idx = int(input("\nSelect item number: ")) - 1
        selected_item, current_qty = items[item_idx]
    except (ValueError, IndexError):
        print("Invalid selection.")
        conn.close()
        return

    try:
        qty_change = int(input(f"How many '{selected_item}'? (Default 1): ") or 1)
    except ValueError:
        print("Invalid quantity.")
        conn.close()
        return

    if is_checkout and qty_change > current_qty:
        print(f"WARNING: You only have {current_qty} in stock. Cannot check out {qty_change}.")
        conn.close()
        return

    print("\nWho is taking/returning this?")
    raw_swipe = input("Swipe Card (or type 7-digit UCF ID, or press ENTER for Staff): ").strip()
    
    ucf_id = "Staff"
    student_name = "Internal/Ad-Hoc"
    position = "Staff"
    email = "Staff"
    duration = "N/A"
    
    if raw_swipe:
        parsed_id = parse_ucf_id(raw_swipe)
        if parsed_id:
            ucf_id = parsed_id
            status, fetched_name, pos, em = verify_student(ucf_id)
            if fetched_name != "Unknown" and fetched_name is not None:
                student_name = fetched_name
                position = pos
                email = em
                duration = "Fall 2026"
            else:
                student_name = input("Enter name for log: ").strip()

    new_qty = (current_qty - qty_change) if is_checkout else (current_qty + qty_change)
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("UPDATE bulk_assets SET quantity = ?, last_updated = ? WHERE item_name = ?", (new_qty, current_time, selected_item))
    conn.commit()
    conn.close()

    print(f"\nSUCCESS: {action_str} {qty_change}x {selected_item}. New stock: {new_qty}")
    log_transaction(action_str, "N/A", selected_item, ucf_id, student_name, position, email, duration)
    backup_to_cloud()

def checkout_item():
    raw_swipe = input("\nSwipe Card (or type 7-digit UCF ID): ")

    if raw_swipe.upper().startswith("SARC-"):
        print("You scanned an equipment barcode. Please swipe the UCF ID card first.")
        return
    
    ucf_id = parse_ucf_id(raw_swipe)
    if ucf_id is None:
        return
    
    is_verified = False
    student_name = "Unknown"
    position = "Unknown"
    email = "Unknown"
    duration = "Fall 2026"
    action_type = "CHECK-OUT"
    
    while not is_verified:
        print(f"Verifying UCFID: {ucf_id} with Qualtrics...")
        status, student_name, position, email = verify_student(ucf_id)
        
        if status == "VERIFIED":
            break
            
        elif status == "EXPIRED":
            print(f"Agreement found for {student_name}, but it is EXPIRED (submitted >12 hours ago).")
            force = input("ADMIN OVERRIDE: Do you want to FORCE check-out anyway using this existing data? (Y/N): ")
            if force.strip().upper() == 'Y':
                print("Forcing Checkout with existing Qualtrics data...")
                action_type = "CHECK-OUT (OVERRIDE - EXPIRED FORM)"
                break
            else:
                print("Checkout aborted.")
                return
                
        elif status in ("NOT_FOUND", "OFFLINE"):
            if status == "NOT_FOUND":
                print("Agreement not found in Qualtrics.")
            else:
                print("System offline. Cannot verify agreement.")
                
            retry = input("Press ENTER to check again, type 'O' for OVERRIDE, or 'X' to cancel: ").strip().upper()
            
            if retry == 'O':
                print("Forcing Checkout...")
                student_name = input("Enter Student First and Last Name: ").strip()
                position = input("Enter Position: ").strip()
                email = input("Enter UCF Email: ").strip()
                action_type = "CHECK-OUT (OVERRIDE - NO FORM)"
                break
            elif retry == 'X':
                print("Checkout aborted.")
                return

    barcode = input("Scan Equipment Barcode: ")
    
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status, equipment_type, brand_model, notes, default_kit FROM serialized_assets WHERE barcode_id = ?", (barcode,))
    result = cursor.fetchone()
    
    if result is None:
        print(f"ERROR: Barcode '{barcode}' not found in database.")
        conn.close()
        return
        
    current_status, eq_type, model, notes, default_kit = result
    
    if current_status != 'Available':
        print(f"WARNING: {barcode} cannot be checked out. Current status: {current_status}")
        conn.close()
        return
        
    if notes and notes.strip():
        print(f"\nALERT ON ITEM: {notes}")
        confirm = input("Are you sure you want to proceed with this checkout? (Y/N): ")
        if confirm.strip().upper() != 'Y':
            print("Checkout aborted by user.")
            conn.close()
            return

    assigned_bulk = []
    if default_kit is not None and default_kit.strip():
        kit_items = [item.strip() for item in default_kit.split('|')]
        print("\nAssociated Bundle Components Found:")
        
        for item in kit_items:
            # Check if we actually have any in stock
            cursor.execute("SELECT quantity FROM bulk_assets WHERE item_name = ?", (item,))
            bulk_result = cursor.fetchone()
            
            if bulk_result:
                in_stock = bulk_result[0]
                if in_stock > 0:
                    choice = input(f"   Include {item}? (Press ENTER for Yes, 'N' for No): ").strip().upper()
                    if choice != 'N':
                        # Decrement bulk inventory
                        cursor.execute("UPDATE bulk_assets SET quantity = quantity - 1 WHERE item_name = ?", (item,))
                        assigned_bulk.append(item)
                else:
                    print(f"   WARNING: {item} is out of stock in bulk inventory!")
            else:
                # NEW: Explicit warning if the item name in default_kit doesn't match bulk_assets.csv
                print(f"   DATABASE ERROR: Bundle item '{item}' not found in bulk inventory. Check for typos.")

    new_note = input("\nAdd a note to this item? (Press ENTER to skip): ").strip()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if new_note:
        timestamp_date = datetime.datetime.now().strftime("%Y-%m-%d")
        formatted_note = f"[{timestamp_date}: {new_note}]"
        final_notes = f"{notes} | {formatted_note}" if notes and notes.strip() else formatted_note
    else:
        final_notes = notes

    attached_string = " | ".join(assigned_bulk) if assigned_bulk else None

    cursor.execute('''
        UPDATE serialized_assets 
        SET status = 'Checked Out', current_ucf_id = ?, current_name = ?, 
            current_position = ?, current_email = ?, current_duration = ?, 
            last_updated = ?, notes = ?, attached_bulk_items = ? 
        WHERE barcode_id = ?
    ''', (ucf_id, student_name, position, email, duration, current_time, final_notes, attached_string, barcode))
    
    conn.commit()
    conn.close()
    
    print(f"SUCCESS: {eq_type} ({model}) checked out to {student_name} ({ucf_id}).")
    log_transaction(action_type, barcode, eq_type, ucf_id, student_name, position, email, duration)
    
    # --- NEW: Explicitly log each bundled item individually ---
    if assigned_bulk:
        print(f"   Attached Accessories: {', '.join(assigned_bulk)}")
        for item in assigned_bulk:
            log_transaction("CHECK-OUT (BUNDLE)", "N/A", item, ucf_id, student_name, position, email, duration)
            
    backup_to_cloud()


def return_item():
    barcode = input("\nScan Equipment Barcode to Return: ")
    
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT status, equipment_type, current_ucf_id, current_name, 
               current_position, current_email, current_duration, notes, attached_bulk_items 
        FROM serialized_assets 
        WHERE barcode_id = ?
    ''', (barcode,))
    result = cursor.fetchone()
    
    if result is None:
        print(f"ERROR: Barcode '{barcode}' not found in database.")
        conn.close()
        return
        
    current_status, eq_type, prev_ucf, prev_name, prev_pos, prev_email, prev_dur, notes, attached_bulk_items = result
    
    if current_status == 'Available':
        print(f"WARNING: {barcode} is already marked as Available in the closet.")
        conn.close()
        return
        
    # Variables to track what was returned/lost for logging
    returned_items_to_log = []
    lost_items_to_log = []

    if attached_bulk_items and attached_bulk_items.strip():
        returned_items = [item.strip() for item in attached_bulk_items.split('|')]
        print("\nVERIFY RETURN OF BUNDLED ACCESSORIES:")
        
        for item in returned_items:
            choice = input(f"   Did they return the {item}? (Press ENTER for Yes, 'N' for No): ").strip().upper()
            if choice != 'N':
                cursor.execute("UPDATE bulk_assets SET quantity = quantity + 1 WHERE item_name = ?", (item,))
                returned_items_to_log.append(item)
            else:
                print(f"   EXCEPTION: {item} was NOT returned. Leaving unreplenished in bulk system.")
                lost_items_to_log.append(item)

    new_note = input("\nAdd a note to this item? (Press ENTER to skip): ").strip()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if new_note:
        timestamp_date = datetime.datetime.now().strftime("%Y-%m-%d")
        formatted_note = f"[{timestamp_date}: {new_note}]"
        final_notes = f"{notes} | {formatted_note}" if notes and notes.strip() else formatted_note
    else:
        final_notes = notes

    cursor.execute('''
        UPDATE serialized_assets 
        SET status = 'Available', current_ucf_id = NULL, current_name = NULL, 
            current_position = NULL, current_email = NULL, current_duration = NULL, 
            last_updated = ?, notes = ?, attached_bulk_items = NULL 
        WHERE barcode_id = ?
    ''', (current_time, final_notes, barcode))
    
    conn.commit()
    conn.close()
    
    print(f"SUCCESS: {eq_type} returned successfully. (Previously held by {prev_name})")
    print("Instruct the student to scan the QR code to submit the Return Survey on their way out!")
    
    # Log the main serialized item
    log_transaction("RETURN", barcode, eq_type, prev_ucf, prev_name, prev_pos, prev_email, prev_dur)
    
    # --- NEW: Explicitly log each bundled item return/loss ---
    for item in returned_items_to_log:
        log_transaction("RETURN (BUNDLE)", "N/A", item, prev_ucf, prev_name, prev_pos, prev_email, prev_dur)
        
    for item in lost_items_to_log:
        # We log "LOST (BUNDLE)" so the boss knows they still owe it!
        log_transaction("LOST (BUNDLE)", "N/A", item, prev_ucf, prev_name, prev_pos, prev_email, prev_dur)

    backup_to_cloud()

def main():
    print("\nSARC INVENTORY MANAGEMENT SYSTEM")
    
    while True:
        print("\nMain Menu:")
        print("1. Check-Out Equipment")
        print("2. Return Equipment")
        print("3. Bulk Inventory Menu")
        print("4. Exit")
        print("5. Backup & Exit")
        
        choice = input("\nSelect an option (1-5): ")
        
        if choice == '1':
            checkout_item()
        elif choice == '2':
            return_item()
        elif choice == '3':
            handle_bulk_inventory()
        elif choice == '4':
            print("Shutting down tracker. Goodbye!")
            break
        elif choice == '5':
            backup_to_cloud()
            print("Shutting down tracker. Goodbye!")
            break
        else:
            print("Invalid choice. Please type 1, 2, 3, 4, or 5.")

if __name__ == "__main__":
    main()