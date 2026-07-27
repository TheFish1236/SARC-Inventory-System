import sqlite3
import csv
import datetime
import os
import shutil

def connect_db():
    return sqlite3.connect('inventory.db')

def log_admin_action(action, barcode, details):
    user_profile = os.environ.get('USERPROFILE')
    operator = os.environ.get('USERNAME', 'Unknown_Admin')
    
    log_path = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - Technology Assistant", "Equipment Tracking", "Live_Data_Feeds", "SARC_Admin_Log.csv")
    
    file_exists = os.path.isfile(log_path)
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with open(log_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Timestamp', 'Operator', 'Action', 'Target Barcode', 'Details'])
            writer.writerow([current_time, operator, action, barcode, details])
    except PermissionError:
        print("Warning: Admin Log is open in Excel, could not append transaction.")
    except Exception as e:
        print(f"Warning: Could not write to Admin Log: {e}")

def backup_to_cloud():
    user_profile = os.environ.get('USERPROFILE')
    onedrive_csv = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - Technology Assistant", "Equipment Tracking", "Live_Data_Feeds", "SARC_Live_Inventory.csv")
    onedrive_bulk_csv = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - Technology Assistant", "Equipment Tracking", "Live_Data_Feeds", "SARC_Live_Bulk.csv")
    onedrive_db = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - Technology Assistant", "Equipment Tracking", "System_Backups", "inventory_backup.db")
    
    conn = connect_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT barcode_id, equipment_type, brand_model, status, current_ucf_id, current_name, current_position, current_email, current_duration, last_updated, notes, attached_bulk_items FROM serialized_assets")
        rows = cursor.fetchall()
        with open(onedrive_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Barcode ID', 'Type', 'Model', 'Status', 'UCF ID', 'Name', 'Position', 'Email', 'Duration', 'Last Updated', 'Notes', 'Attached Bulk Items'])
            writer.writerows(rows)
            
        cursor.execute("SELECT item_name, quantity, category, notes, last_updated FROM bulk_assets")
        bulk_rows = cursor.fetchall()
        with open(onedrive_bulk_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Item Name', 'Quantity', 'Category', 'Notes', 'Last Updated'])
            writer.writerows(bulk_rows)
            
        shutil.copy2('inventory.db', onedrive_db)
        print("Live cloud backups synced to OneDrive.")
    except Exception as e:
        print(f"Cloud sync warning: {e}")
    finally:
        conn.close()

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
        cursor.execute('''
            INSERT INTO serialized_assets 
            (barcode_id, equipment_type, brand_model, service_tag, status, notes, default_kit, 
             attached_bulk_items, current_ucf_id, current_name, current_position, current_email, current_duration, last_updated)
            VALUES (?, ?, ?, ?, 'Available', ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, ?)
        ''', (barcode_id, equipment_type, brand_model, service_tag, notes, default_kit, current_time))
        
        conn.commit()
        print(f"SUCCESS: Added {barcode_id} to live database as Available.")
    except sqlite3.IntegrityError:
        print(f"ERROR: {barcode_id} already exists in the database.")
        conn.close()
        return
    finally:
        conn.close()

    source_csv_path = os.path.join('source_data', 'serialized_assets.csv')
    try:
        needs_newline = False
        if os.path.exists(source_csv_path):
            with open(source_csv_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if content and not content.endswith('\n'):
                    needs_newline = True

        with open(source_csv_path, 'a', newline='', encoding='utf-8') as f:
            if needs_newline:
                f.write('\n')
            writer = csv.writer(f)
            writer.writerow([barcode_id, equipment_type, brand_model, service_tag, 'Available', notes, default_kit, ''])
        print(f"Appended {barcode_id} to source_data/serialized_assets.csv")
    except Exception as e:
        print(f"Warning: Could not update source CSV: {e}")

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

    source_csv_path = os.path.join('source_data', 'bulk_assets.csv')
    try:
        needs_newline = False
        if os.path.exists(source_csv_path):
            with open(source_csv_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if content and not content.endswith('\n'):
                    needs_newline = True

        with open(source_csv_path, 'a', newline='', encoding='utf-8') as f:
            if needs_newline:
                f.write('\n')
            writer = csv.writer(f)
            writer.writerow([item_name, quantity, category, notes])
        print(f"Appended {item_name} to source_data/bulk_assets.csv")
    except Exception as e:
        print(f"Warning: Could not update source CSV: {e}")

    log_admin_action("INGEST_BULK", "N/A", f"Added {quantity}x {item_name} in {category}")
    backup_to_cloud()

def delete_or_surplus_asset():
    print("\n--- DELETE / SURPLUS ASSET ---")
    barcode_id = input("Enter Barcode ID to modify (e.g., SARC-Laptop-08): ").strip()
    
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT brand_model, status FROM serialized_assets WHERE barcode_id = ?", (barcode_id,))
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
        cursor.execute("UPDATE serialized_assets SET status = 'Unavailable', notes = ?, last_updated = ? WHERE barcode_id = ?", (f"Surplused: {reason}", current_time, barcode_id))
        conn.commit()
        print(f"SUCCESS: {barcode_id} marked as Unavailable.")
        log_admin_action("SURPLUS_ASSET", barcode_id, f"Status set to Unavailable. Reason: {reason}")
    elif choice == '2':
        confirm = input(f"ARE YOU SURE you want to permanently delete {barcode_id}? (Y/N): ").strip().upper()
        if confirm == 'Y':
            cursor.execute("DELETE FROM serialized_assets WHERE barcode_id = ?", (barcode_id,))
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
    cursor.execute("SELECT brand_model, service_tag, default_kit FROM serialized_assets WHERE barcode_id = ?", (barcode_id,))
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
        cursor.execute("UPDATE serialized_assets SET service_tag = ?, last_updated = ? WHERE barcode_id = ?", (new_tag, current_time, barcode_id))
        details.append(f"SN changed: '{old_tag}' -> '{new_tag}'")
    if new_kit:
        cursor.execute("UPDATE serialized_assets SET default_kit = ?, last_updated = ? WHERE barcode_id = ?", (new_kit, current_time, barcode_id))
        details.append(f"Kit changed: '{old_kit}' -> '{new_kit}'")
        
    conn.commit()
    conn.close()
    
    if details:
        print(f"SUCCESS: Updated record for {barcode_id}.")
        log_admin_action("UPDATE_TAGS", barcode_id, " | ".join(details))
        backup_to_cloud()
    else:
        print("No changes entered.")

def main():
    while True:
        print("\n=== SARC DATABASE ADMIN CONTROL PANEL ===")
        print("1. Ingest New Serialized Asset")
        print("2. Ingest New Bulk Asset")
        print("3. Surplus or Delete Asset")
        print("4. Update Service Tag or Default Kit")
        print("5. Exit")
        
        choice = input("\nSelect option (1-5): ").strip()
        
        if choice == '1':
            add_new_asset()
        elif choice == '2':
            add_new_bulk_asset()
        elif choice == '3':
            delete_or_surplus_asset()
        elif choice == '4':
            swap_or_update_tags()
        elif choice == '5':
            print("Exiting Admin Control Panel.")
            break
        else:
            print("Invalid option.")

if __name__ == "__main__":
    main()