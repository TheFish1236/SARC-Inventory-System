import sqlite3
from datetime import datetime

def get_active_loans():
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()
    
    # Fetch all loans where time_in is NULL (meaning they still have it)
    cursor.execute('''
        SELECT u.name, u.ucf_id, u.email, e.equipment_type, e.barcode_id, l.time_out
        FROM loans l
        JOIN users u ON l.ucf_id = u.ucf_id
        JOIN equipment e ON l.barcode_id = e.barcode_id
        WHERE l.time_in IS NULL AND l.ucf_id != 'Staff'
        ORDER BY l.time_out ASC
    ''')
    active_loans = cursor.fetchall()
    conn.close()
    return active_loans

def audit_overdue():
    print("\n--- INITIATING OVERDUE EQUIPMENT AUDIT ---")
    active_loans = get_active_loans()
    
    if not active_loans:
        print(" Good news: No active student loans found.")
        return

    print(f" Found {len(active_loans)} total active checkouts.")
    
    deadline_input = input("Enter a deadline date (YYYY-MM-DD) to find overdue items, or press ENTER to list ALL active checkouts: ").strip()
    
    hit_list = []
    
    if deadline_input:
        try:
            deadline_date = datetime.strptime(deadline_input, "%Y-%m-%d")
            print(f"\n Searching for items checked out BEFORE {deadline_input}...")
            
            for loan in active_loans:
                time_out_str = loan[5].split(" ")[0] # Grab just the YYYY-MM-DD part
                time_out_date = datetime.strptime(time_out_str, "%Y-%m-%d")
                
                # If they checked it out before the deadline, they are on the hit list
                if time_out_date < deadline_date:
                    hit_list.append(loan)
        except ValueError:
            print(" ERROR: Invalid date format. Please use YYYY-MM-DD.")
            return
    else:
        # If they just pressed Enter, the hit list is EVERYONE
        hit_list = active_loans

    # Print the Results
    if not hit_list:
        print(" No overdue items found for that date.")
    else:
        print("\n  ACTIVE LOANS REPORT:\n")
        print(f"{'NAME':<20} | {'UCF ID':<10} | {'EMAIL':<25} | {'ITEM':<15} | {'BARCODE':<15} | {'CHECKOUT DATE'}")
        print("-" * 110)
        
        for record in hit_list:
            name, ucf_id, email, eq_type, barcode, time_out = record
            short_date = time_out.split(" ")[0]
            
            # Truncate long names or emails so they don't break the table formatting
            print(f"{name[:18]:<20} | {ucf_id:<10} | {email[:23]:<25} | {eq_type[:13]:<15} | {barcode:<15} | {short_date}")
            
        print(f"\nTotal Records: {len(hit_list)}")
        print(" Next Step: Copy this list and email the users to return their equipment.")

if __name__ == "__main__":
    audit_overdue()