import sqlite3
import csv
import datetime

def setup_database():
    # 1. Connect to SQLite (This creates inventory.db if it doesn't exist)
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()

    print("Building database tables...")

    # 2. Create the Serialized Assets Table
    # We use DROP TABLE IF EXISTS so you can re-run this script safely if you ever make a mistake in your CSV!
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
            last_updated TEXT
        )
    ''')

    # 3. Create the Bulk Assets Table
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

    # 4. Import Serialized Assets
    print("Importing serialized_assets.csv...")
    with open('serialized_assets.csv', 'r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            cursor.execute('''
                INSERT INTO serialized_assets 
                (barcode_id, equipment_type, brand_model, service_tag, status, notes, current_ucf_id, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
            ''', (row['barcode_id'], row['equipment_type'], row['brand_model'], row['service_tag'], row['status'], row['notes'], current_time)
            )

    # 5. Import Bulk Assets
    print("Importing bulk_assets.csv...")
    with open('bulk_assets.csv', 'r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            cursor.execute('''
                INSERT INTO bulk_assets 
                (item_name, quantity, category, notes, last_updated)
                VALUES (?, ?, ?, ?, ?)
            ''', (row['item_name'], row['quantity'], row['category'], row['notes'], current_time)
            )

    # 6. Save and Close
    conn.commit()
    conn.close()
    print("Database successfully built")

if __name__ == "__main__":
    setup_database()