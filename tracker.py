import sqlite3
import datetime
from qualtrics_api import verify_student
import re
import shutil
import os
import csv

def backup_to_cloud():
    user_profile = os.environ.get('USERPROFILE')
    base_dir = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - SARC", "Technology Assistant", "Equipment Tracking")
    
    # Our 3 "API Endpoints" for Power BI / Excel
    onedrive_live = os.path.join(base_dir, "Live_Data_Feeds", "SARC_Live_Inventory.csv")
    onedrive_bulk = os.path.join(base_dir, "Live_Data_Feeds", "SARC_Live_Bulk.csv")
    onedrive_history = os.path.join(base_dir, "Live_Data_Feeds", "SARC_History_Log.csv")
    
    onedrive_db = os.path.join(base_dir, "System_Backups", "inventory_backup.db")
    
    conn = connect_db()
    cursor = conn.cursor()
    
    try:
        # 1. Export Live Serialized View
        cursor.execute("SELECT * FROM vw_dashboard_live")
        with open(onedrive_live, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([d[0] for d in cursor.description])
            writer.writerows(cursor.fetchall())
            
        # 2. Export Live Bulk Table
        cursor.execute("SELECT item_name, quantity, category, notes, last_updated FROM bulk_assets")
        with open(onedrive_bulk, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([d[0] for d in cursor.description])
            writer.writerows(cursor.fetchall())
            
        # 3. Export History Ledger (Now with NAMES!)
        cursor.execute('''
            SELECT l.time_out AS Timestamp, 'CHECK-OUT' AS Action, l.barcode_id AS Target, l.ucf_id AS UCF_ID, u.name AS Name, l.duration AS Details
            FROM loans l
            LEFT JOIN users u ON l.ucf_id = u.ucf_id
            WHERE l.time_out IS NOT NULL
            UNION ALL
            SELECT l.time_in AS Timestamp, 'RETURN' AS Action, l.barcode_id AS Target, l.ucf_id AS UCF_ID, u.name AS Name, l.attached_bulk AS Details
            FROM loans l
            LEFT JOIN users u ON l.ucf_id = u.ucf_id
            WHERE l.time_in IS NOT NULL
            UNION ALL
            SELECT timestamp AS Timestamp, action_type AS Action, item_name AS Target, ucf_id AS UCF_ID, student_name AS Name, CAST(qty_change AS TEXT) AS Details
            FROM bulk_transactions
            ORDER BY Timestamp DESC
        ''')
        with open(onedrive_history, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Added 'Name' to the headers
            writer.writerow(['Timestamp', 'Action', 'Target', 'UCF_ID', 'Name', 'Details'])
            writer.writerows(cursor.fetchall())
            
        # 4. Backup the raw DB for Disaster Recovery
        shutil.copy2('inventory.db', onedrive_db)
        print("Data Pipeline Synced: Views and DB backed up to OneDrive.")
        
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
                return match.group(0)[-7:]
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
    
    if raw_swipe:
        parsed_id = parse_ucf_id(raw_swipe)
        if parsed_id:
            ucf_id = parsed_id
            status, fetched_name, pos, em = verify_student(ucf_id)
            if fetched_name and fetched_name != "Unknown":
                student_name = fetched_name
            else:
                student_name = input("Enter name for log: ").strip()

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_qty = (current_qty - qty_change) if is_checkout else (current_qty + qty_change)
    signed_qty_change = -qty_change if is_checkout else qty_change
    
    # Update bulk stock
    cursor.execute("UPDATE bulk_assets SET quantity = ?, last_updated = ? WHERE item_name = ?", (new_qty, current_time, selected_item))
    
    # Native SQL Logging for bulk actions
    cursor.execute('''
        INSERT INTO bulk_transactions (item_name, qty_change, action_type, ucf_id, student_name, timestamp) 
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (selected_item, signed_qty_change, action_str, ucf_id, student_name, current_time))
    
    conn.commit()
    conn.close()

    print(f"\nSUCCESS: {action_str} {qty_change}x {selected_item}. New stock: {new_qty}")
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
    
    # Query 'equipment' table instead of 'serialized_assets'
    cursor.execute("SELECT status, equipment_type, brand_model, notes, default_kit FROM equipment WHERE barcode_id = ?", (barcode,))
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
    if default_kit and default_kit.strip():
        kit_items = [item.strip() for item in default_kit.split('|')]
        print("\nAssociated Bundle Components Found:")
        
        for item in kit_items:
            cursor.execute("SELECT quantity FROM bulk_assets WHERE item_name = ?", (item,))
            bulk_result = cursor.fetchone()
            if bulk_result and bulk_result[0] > 0:
                choice = input(f"   Include {item}? (Press ENTER for Yes, 'N' for No): ").strip().upper()
                if choice != 'N':
                    cursor.execute("UPDATE bulk_assets SET quantity = quantity - 1 WHERE item_name = ?", (item,))
                    
                    # Log bulk component native transaction
                    cursor.execute("INSERT INTO bulk_transactions (item_name, qty_change, action_type, ucf_id, student_name, timestamp) VALUES (?, -1, ?, ?, ?, CURRENT_TIMESTAMP)", (item, "CHECK-OUT (BUNDLE)", ucf_id, student_name))
                    assigned_bulk.append(item)
            else:
                print(f"   WARNING: {item} is out of stock in bulk inventory!")

    new_note = input("\nAdd a note to this item? (Press ENTER to skip): ").strip()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final_notes = f"{notes} | [{datetime.datetime.now().strftime('%Y-%m-%d')}: {new_note}]" if new_note and notes and notes.strip() else (f"[{datetime.datetime.now().strftime('%Y-%m-%d')}: {new_note}]" if new_note else notes)
    attached_string = " | ".join(assigned_bulk) if assigned_bulk else None

    # Step 1: Manage User (Upsert)
    cursor.execute('''
        INSERT INTO users (ucf_id, name, position, email, last_updated)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(ucf_id) DO UPDATE SET 
        name=excluded.name, position=excluded.position, email=excluded.email, last_updated=excluded.last_updated
    ''', (ucf_id, student_name, position, email, current_time))
    
    # Step 2: Establish Active Loan (time_in is NULL, meaning it is checked out)
    cursor.execute('''
        INSERT INTO loans (barcode_id, ucf_id, time_out, duration, attached_bulk, action_out)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (barcode, ucf_id, current_time, duration, attached_string, action_type))
    
    # Step 3: Modify Asset Base Data
    cursor.execute("UPDATE equipment SET status = 'Checked Out', last_updated = ?, notes = ? WHERE barcode_id = ?", (current_time, final_notes, barcode))
    
    conn.commit()
    conn.close()
    
    print(f"SUCCESS: {eq_type} ({model}) checked out to {student_name} ({ucf_id}).")
    if assigned_bulk:
        print(f"   Attached Accessories: {', '.join(assigned_bulk)}")
        
    backup_to_cloud()

def return_item():
    barcode = input("\nScan Equipment Barcode to Return: ")
    
    conn = connect_db()
    cursor = conn.cursor()
    
    # 3NF Multi-table JOIN to find the specific active loan for this item
    cursor.execute('''
        SELECT e.status, e.equipment_type, l.transaction_id, l.ucf_id, u.name, e.notes, l.attached_bulk
        FROM equipment e
        LEFT JOIN loans l ON e.barcode_id = l.barcode_id AND l.time_in IS NULL
        LEFT JOIN users u ON l.ucf_id = u.ucf_id
        WHERE e.barcode_id = ?
    ''', (barcode,))
    result = cursor.fetchone()
    
    if result is None:
        print(f"ERROR: Barcode '{barcode}' not found in database.")
        conn.close()
        return
        
    current_status, eq_type, loan_id, prev_ucf, prev_name, notes, attached_bulk_items = result
    
    if current_status == 'Available' or loan_id is None:
        print(f"WARNING: {barcode} is already marked as Available in the closet.")
        conn.close()
        return

    if attached_bulk_items and attached_bulk_items.strip():
        returned_items = [item.strip() for item in attached_bulk_items.split('|')]
        print("\nVERIFY RETURN OF BUNDLED ACCESSORIES:")
        for item in returned_items:
            choice = input(f"   Did they return the {item}? (Press ENTER for Yes, 'N' for No): ").strip().upper()
            if choice != 'N':
                cursor.execute("UPDATE bulk_assets SET quantity = quantity + 1 WHERE item_name = ?", (item,))
                cursor.execute("INSERT INTO bulk_transactions (item_name, qty_change, action_type, ucf_id, student_name, timestamp) VALUES (?, 1, 'RETURN (BUNDLE)', ?, ?, CURRENT_TIMESTAMP)", (item, prev_ucf, prev_name))
            else:
                print(f"   EXCEPTION: {item} was NOT returned. Leaving unreplenished in bulk system.")
                cursor.execute("INSERT INTO bulk_transactions (item_name, qty_change, action_type, ucf_id, student_name, timestamp) VALUES (?, 0, 'LOST (BUNDLE)', ?, ?, CURRENT_TIMESTAMP)", (item, prev_ucf, prev_name))

    new_note = input("\nAdd a note to this item? (Press ENTER to skip): ").strip()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final_notes = f"{notes} | [{datetime.datetime.now().strftime('%Y-%m-%d')}: {new_note}]" if new_note and notes and notes.strip() else (f"[{datetime.datetime.now().strftime('%Y-%m-%d')}: {new_note}]" if new_note else notes)

    # Free Asset & Close the Loan Record (time_in is stamped)
    cursor.execute("UPDATE equipment SET status = 'Available', last_updated = ?, notes = ? WHERE barcode_id = ?", (current_time, final_notes, barcode))
    cursor.execute("UPDATE loans SET time_in = ?, action_in = 'RETURN' WHERE transaction_id = ?", (current_time, loan_id))
    
    conn.commit()
    conn.close()
    
    print(f"SUCCESS: {eq_type} returned successfully. (Previously held by {prev_name})")
    print("Instruct the student to scan the QR code to submit the Return Survey on their way out!")
    
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
