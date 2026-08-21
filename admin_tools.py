import sqlite3
import csv
import datetime
import shutil
import os

def connect_db():
    return sqlite3.connect('inventory.db')

def log_admin_action(action, barcode, details):
    operator = os.environ.get('USERNAME', 'Unknown_Admin')
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO admin_logs (timestamp, operator, action, target_barcode, details)
            VALUES (?, ?, ?, ?, ?)
        ''', (current_time, operator, action, barcode, details))
        conn.commit()
    except Exception as e:
        print(f"Warning: Could not write to admin_logs table: {e}")
    finally:
        conn.close()

def backup_to_cloud():
    user_profile = os.environ.get('USERPROFILE')
    base_dir = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - SARC", "Technology Assistant", "Equipment Tracking")
    
    # 4 Data Endpoints
    onedrive_live = os.path.join(base_dir, "Live_Data_Feeds", "SARC_Live_Inventory.csv")
    onedrive_bulk = os.path.join(base_dir, "Live_Data_Feeds", "SARC_Live_Bulk.csv")
    onedrive_history = os.path.join(base_dir, "Live_Data_Feeds", "SARC_History_Log.csv")
    onedrive_admin = os.path.join(base_dir, "Live_Data_Feeds", "SARC_Admin_Log.csv")
    
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
            
        # 3. Export History Ledger 
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
            writer.writerow(['Timestamp', 'Action', 'Target', 'UCF_ID', 'Name', 'Details'])
            writer.writerows(cursor.fetchall())

        # 4. Export Admin Logs
        cursor.execute("SELECT timestamp, operator, action, target_barcode, details FROM admin_logs ORDER BY timestamp DESC")
        with open(onedrive_admin, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Operator', 'Action', 'Target Barcode', 'Details'])
            writer.writerows(cursor.fetchall())
            
        # 5. Backup the raw DB
        shutil.copy2('inventory.db', onedrive_db)
        print("Data Pipeline Synced: Views and DB backed up to OneDrive.")
        
    except Exception as e:
        print(f"\nWARNING: Cloud sync failed: {e}")
    finally:
        conn.close()

def sync_from_cloud():
    user_profile = os.environ.get('USERPROFILE')
    onedrive_db = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - SARC", "Technology Assistant", "Equipment Tracking", "System_Backups", "inventory_backup.db")
    local_db = 'inventory.db'

    print(" Checking for cloud database updates...")
    
    if not os.path.exists(onedrive_db):
        print(" No cloud backup found in OneDrive. Proceeding with local only.")
        return

    try:
        cloud_time = os.path.getmtime(onedrive_db)
        local_time = os.path.getmtime(local_db) if os.path.exists(local_db) else 0

        # If the OneDrive file was modified more recently than the local file
        if cloud_time > local_time:
            print("\n ALERT: A newer database version exists in the cloud!")
            choice = input("Do you want to PULL the latest database from OneDrive? (Y/N): ").strip().upper()
            if choice == 'Y':
                shutil.copy2(onedrive_db, local_db)
                print(" SUCCESS: Local database updated from cloud.")
            else:
                print(" WARNING: You are proceeding with an OUTDATED local database. Overwrites may occur.")
        else:
            print(" Local database is up to date.")
            
    except Exception as e:
        print(f" OFFLINE WARNING: Could not sync from cloud. Proceed with caution. ({e})")

def add_new_asset():
    print("\n--- INGEST NEW SERIALIZED ASSET ---")
    barcode_id = input("Enter Barcode ID (e.g., SARC-DocCam-23): ").strip()
    equipment_type = input("Enter Equipment Type (e.g., Document Camera): ").strip()
    brand_model = input("Enter Brand/Model (e.g., Elmo OX-1): ").strip()
    service_tag = input("Enter Serial / Service Tag: ").strip()
    notes = input("Enter Notes (or press ENTER to skip): ").strip()
    default_kit = input("Enter Default Kit (or press ENTER to skip): ").strip()

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = connect_db()
    cursor = conn.cursor()

    try:
        # Changed from serialized_assets to equipment
        cursor.execute('''
            INSERT INTO equipment 
            (barcode_id, equipment_type, brand_model, service_tag, default_kit, notes, status, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, 'Available', ?)
        ''', (barcode_id, equipment_type, brand_model, service_tag, default_kit, notes, current_time))
        
        conn.commit()
        print(f"SUCCESS: Added {barcode_id} to live database as Available.")
    except sqlite3.IntegrityError:
        print(f"ERROR: {barcode_id} already exists in the database.")
        conn.close()
        return
    finally:
        conn.close()

    log_admin_action("INGEST_ASSET", barcode_id, f"Added {brand_model} | SN: {service_tag} | Kit: {default_kit}")
    backup_to_cloud()

def add_new_bulk_asset():
    print("\n--- INGEST NEW BULK ASSET ---")
    item_name = input("Enter Item Name (e.g., HDMI to USB Adapter): ").strip()
    try:
        quantity = int(input("Enter Quantity: "))
    except ValueError:
        print("Invalid quantity. Must be a number.")
        return
        
    category = input("Enter Category (e.g., Adapters, Cables, Peripherals): ").strip()
    notes = input("Enter Notes (e.g., Location: Front Desk) (or press ENTER to skip): ").strip()

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO bulk_assets (item_name, quantity, category, notes, last_updated)
            VALUES (?, ?, ?, ?, ?)
        ''', (item_name, quantity, category, notes, current_time))
        conn.commit()
        print(f"SUCCESS: Added {quantity}x {item_name} to live database.")
    except sqlite3.IntegrityError:
        print(f"ERROR: {item_name} already exists. Use the Tracker Bulk Menu to add stock.")
        conn.close()
        return
    finally:
        conn.close()

    log_admin_action("INGEST_BULK", "N/A", f"Added {quantity}x {item_name} in {category}")
    backup_to_cloud()

def delete_or_surplus_asset():
    print("\n--- DELETE / SURPLUS ASSET ---")
    barcode_id = input("Enter Barcode ID to modify (e.g., SARC-Laptop-08): ").strip()
    
    conn = connect_db()
    cursor = conn.cursor()
    
    # Changed from serialized_assets to equipment
    cursor.execute("SELECT brand_model, status FROM equipment WHERE barcode_id = ?", (barcode_id,))
    result = cursor.fetchone()
    
    if not result:
        print(f"ERROR: {barcode_id} not found in database.")
        conn.close()
        return
        
    print(f"Found: {barcode_id} ({result[0]}) | Current Status: {result[1]}")
    print("1. Mark as Unavailable / Surplused (Recommended)")
    print("2. Hard Delete from Database (Accidental entries only)")
    choice = input("Select option (1-2): ").strip()
    
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if choice == '1':
        reason = input("Enter reason for surplus/unavailability: ").strip()
        cursor.execute("UPDATE equipment SET status = 'Unavailable', notes = ?, last_updated = ? WHERE barcode_id = ?", (f"Surplused: {reason}", current_time, barcode_id))
        conn.commit()
        print(f"SUCCESS: {barcode_id} marked as Unavailable.")
        log_admin_action("SURPLUS_ASSET", barcode_id, f"Status set to Unavailable. Reason: {reason}")
    elif choice == '2':
        confirm = input(f"ARE YOU SURE you want to permanently delete {barcode_id}? This will orphan history logs! (Y/N): ").strip().upper()
        if confirm == 'Y':
            cursor.execute("DELETE FROM equipment WHERE barcode_id = ?", (barcode_id,))
            conn.commit()
            print(f"SUCCESS: Permanently deleted {barcode_id} from database.")
            log_admin_action("HARD_DELETE", barcode_id, "Permanently removed record from database.")
        else:
            print("Deletion canceled.")
            
    conn.close()
    backup_to_cloud()

def swap_or_update_tags():
    print("\n--- SWAP OR UPDATE ASSET TAGS ---")
    barcode_id = input("Enter Barcode ID to update (e.g., SARC-Laptop-06): ").strip()
    
    conn = connect_db()
    cursor = conn.cursor()
    
    # Changed from serialized_assets to equipment
    cursor.execute("SELECT brand_model, service_tag, default_kit FROM equipment WHERE barcode_id = ?", (barcode_id,))
    result = cursor.fetchone()
    
    if not result:
        print(f"ERROR: {barcode_id} not found in database.")
        conn.close()
        return
        
    old_tag = result[1]
    old_kit = result[2]
    
    print(f"Current Record for {barcode_id}:")
    print(f"  Model: {result[0]}")
    print(f"  Service Tag: {old_tag}")
    print(f"  Default Kit: {old_kit}")
    
    new_tag = input("\nEnter new Service Tag (Press ENTER to keep current): ").strip()
    new_kit = input("Enter new Default Kit (Press ENTER to keep current): ").strip()
    
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    details = []
    
    if new_tag:
        cursor.execute("UPDATE equipment SET service_tag = ?, last_updated = ? WHERE barcode_id = ?", (new_tag, current_time, barcode_id))
        details.append(f"SN changed: '{old_tag}' -> '{new_tag}'")
    if new_kit:
        cursor.execute("UPDATE equipment SET default_kit = ?, last_updated = ? WHERE barcode_id = ?", (new_kit, current_time, barcode_id))
        details.append(f"Kit changed: '{old_kit}' -> '{new_kit}'")
        
    conn.commit()
    conn.close()
    
    if details:
        print(f"SUCCESS: Updated record for {barcode_id}.")
        log_admin_action("UPDATE_TAGS", barcode_id, " | ".join(details))
        backup_to_cloud()
    else:
        print("No changes entered.")

def correct_user_ucf_id():
    print("\n--- CORRECT USER UCF ID (GLOBAL REPLACE) ---")
    old_ucf_id = input("Enter the WRONG 7-digit UCF ID currently in the system: ").strip()
    
    conn = connect_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT name, position, email, last_updated FROM users WHERE ucf_id = ?", (old_ucf_id,))
    user_data = cursor.fetchone()
    
    if not user_data:
        print(f"ERROR: UCF ID '{old_ucf_id}' not found in the users table.")
        conn.close()
        return
        
    student_name = user_data[0]
    print(f"\nFound User: {student_name} (ID: {old_ucf_id})")
    
    new_ucf_id = input("Enter the CORRECT 7-digit UCF ID: ").strip()
    
    if len(new_ucf_id) != 7 or not new_ucf_id.isdigit():
        print("ERROR: Invalid UCF ID format. Must be 7 digits.")
        conn.close()
        return
        
    if old_ucf_id == new_ucf_id:
        print("ERROR: The new ID is the same as the old ID.")
        conn.close()
        return
        
    cursor.execute('''
        INSERT INTO users (ucf_id, name, position, email, last_updated)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(ucf_id) DO UPDATE SET 
        name=excluded.name, position=excluded.position, email=excluded.email, last_updated=excluded.last_updated
    ''', (new_ucf_id, user_data[0], user_data[1], user_data[2], user_data[3]))
        
    cursor.execute("UPDATE loans SET ucf_id = ? WHERE ucf_id = ?", (new_ucf_id, old_ucf_id))
    loans_updated = cursor.rowcount
    
    cursor.execute("UPDATE bulk_transactions SET ucf_id = ? WHERE ucf_id = ?", (new_ucf_id, old_ucf_id))
    bulk_updated = cursor.rowcount
    
    cursor.execute("DELETE FROM users WHERE ucf_id = ?", (old_ucf_id,))
    
    conn.commit()
    conn.close()
    
    print(f"\nSUCCESS: Transferred all records from {old_ucf_id} to {new_ucf_id}.")
    print(f" -> Updated {loans_updated} serialized loan records.")
    print(f" -> Updated {bulk_updated} bulk transaction records.")
    
    log_admin_action("FIX_TYPO_ID", "GLOBAL", f"Changed UCF ID from {old_ucf_id} to {new_ucf_id} across {loans_updated} loans and {bulk_updated} bulk items")
    backup_to_cloud()

def main():
    sync_from_cloud()
    while True:
        print("\n=== SARC DATABASE ADMIN CONTROL PANEL ===")
        print("1. Ingest New Serialized Asset")
        print("2. Ingest New Bulk Asset")
        print("3. Surplus or Delete Asset")
        print("4. Update Service Tag or Default Kit")
        print("5. Correct User UCF ID (Global Replace)")
        print("6. Sync Changes from Cloud")
        print("7. Backup Changes to Cloud")
        print("8. Exit")
        
        choice = input("\nSelect option (1-8): ").strip()
        
        if choice == '1':
            add_new_asset()
        elif choice == '2':
            add_new_bulk_asset()
        elif choice == '3':
            delete_or_surplus_asset()
        elif choice == '4':
            swap_or_update_tags()
        elif choice == '5':
            correct_user_ucf_id()
        elif choice == '6':
            sync_from_cloud()
        elif choice == '7':
            backup_to_cloud()
        elif choice == '8':
            print("Exiting Admin Control Panel.")
            break
        else:
            print("Invalid option.")

if __name__ == "__main__":
    main()