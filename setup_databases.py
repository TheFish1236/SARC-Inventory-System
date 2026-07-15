import sqlite3
import csv
import datetime
import shutil
import os

def setup_database():
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()

    print("Building database tables with upgraded schema...")

    cursor.execute('DROP TABLE IF EXISTS serialized_assets')
    cursor.execute('''
        CREATE TABLE serialized_assets (
            barcode_id TEXT PRIMARY KEY,
            equipment_type TEXT,
            brand_model TEXT,
            service_tag TEXT,
            status TEXT,
            notes TEXT,
            current_ucf_id TEXT,
            current_name TEXT,
            current_position TEXT,
            current_email TEXT,
            current_duration TEXT,
            last_updated TEXT
        )
    ''')

    cursor.execute('DROP TABLE IF EXISTS bulk_assets')
    cursor.execute('''
        CREATE TABLE bulk_assets (
            item_name TEXT PRIMARY KEY,
            quantity INTEGER,
            category TEXT,
            notes TEXT,
            last_updated TEXT
        )
    ''')

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("Importing serialized_assets.csv...")
    with open(os.path.join('source_data', 'serialized_assets.csv'), 'r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            cursor.execute('''
                INSERT INTO serialized_assets 
                (barcode_id, equipment_type, brand_model, service_tag, status, notes, 
                 current_ucf_id, current_name, current_position, current_email, current_duration, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?)
            ''', (row['barcode_id'], row['equipment_type'], row['brand_model'], row['service_tag'], row['status'], row['notes'], current_time)
            )

    print("Importing bulk_assets.csv...")
    with open(os.path.join('source_data', 'bulk_assets.csv'), 'r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            cursor.execute('''
                INSERT INTO bulk_assets 
                (item_name, quantity, category, notes, last_updated)
                VALUES (?, ?, ?, ?, ?)
            ''', (row['item_name'], row['quantity'], row['category'], row['notes'], current_time)
            )

    conn.commit()
    conn.close()

    print("Pushing fresh database and source CSVs to OneDrive...")
    user_profile = os.environ.get('USERPROFILE')
    
    onedrive_dir = os.path.join(user_profile, "OneDrive - University of Central Florida", "UCFTeam-SARC_GRP - Technology Assistant", "Equipment Tracking", "System_Backups")
    files_to_backup = {
        'inventory.db': 'inventory_backup.db',
        os.path.join('source_data', 'serialized_assets.csv'): 'serialized_assets.csv',
        os.path.join('source_data', 'bulk_assets.csv'): 'bulk_assets.csv'
    }
    
    for local_file, dest_name in files_to_backup.items():
        try:
            if os.path.exists(local_file):
                shutil.copy2(local_file, os.path.join(onedrive_dir, dest_name))
                print(f"  -> Synced {dest_name}")
            else:
                print(f"  -> Skipped {local_file} (File not found locally)")
        except Exception as e:
            print(f"Could not sync {local_file} to cloud: {e}")
            
    print("Cloud synced successfully!")

if __name__ == "__main__":
    setup_database()