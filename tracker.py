import sqlite3
import datetime

# 1. Connect to the database (This creates 'inventory.db' in your folder if it doesn't exist)
conn = sqlite3.connect('inventory.db')
cursor = conn.cursor()

# 2. Create your table (Using basic SQL)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS devices (
        barcode_id TEXT PRIMARY KEY,    /* Your sticker: SARC-Laptop-1 */
        equipment_type TEXT,            /* Laptop, iPad, etc. */
        brand_model TEXT,               /* Dell Latitude, iPad Pro */
        service_tag TEXT,               /* The manufacturer serial number */
        status TEXT,                    /* Available / Checked Out */
        current_ucf_id TEXT,            /* Who currently holds it? (NULL if in closet) */
        last_updated TEXT
    )
''')

# 3. Add a test laptop to your database (You'll eventually loop this to add all 30)
cursor.execute('''
    INSERT OR IGNORE INTO devices (barcode_id, device_type, status, last_updated)
    VALUES ('SARC-Laptop-1;', 'Laptop', 'Available', 'Never')
''')
conn.commit()

# 4. The Scanner Loop (The core logic!)
print("--- Inventory Scanner System Active ---")
print("Scan an item (or type 'exit' to quit):")

while True:
    # The scanner will type the barcode and hit enter automatically!
    scanned_input = input("> ") 
    
    if scanned_input.lower() == 'exit':
        break
        
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Look up the current status of the scanned item
    cursor.execute("SELECT status FROM devices WHERE barcode_id = ?", (scanned_input,))
    result = cursor.fetchone() # This grabs the row from the database
    
    if result is None:
        print(f"ERROR: {scanned_input} is not in the system.")
        continue # Skip the rest of the loop and wait for the next scan
        
    current_status = result[0] # fetchone() returns a tuple like ('Available',), so we grab the first item
    
    # 2. Your If-Statement logic!
    if current_status == 'Available':
        # It's in the closet, so we are checking it OUT
        new_status = 'Checked Out'
        print(f"Checking OUT: {scanned_input}")
        
        # Ask who is taking it!
        ucf_id = input("Enter Employee UCF ID: ")
        
        cursor.execute('''
            UPDATE devices 
            SET status = ?, current_ucf_id = ?, last_updated = ? 
            WHERE barcode_id = ?
        ''', (new_status, ucf_id, current_time, scanned_input))

    else:
        # It's checked out, so we are checking it back IN
        new_status = 'Available'
        print(f"Checking IN: {scanned_input}")
        
        # Clear out the user ID since it's back in the closet
        cursor.execute('''
            UPDATE devices 
            SET status = ?, current_ucf_id = NULL, last_updated = ? 
            WHERE barcode_id = ?
        ''', (new_status, current_time, scanned_input))
    
    conn.commit()

conn.close()