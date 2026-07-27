# SARC Equipment Inventory System

## Overview
The SARC Equipment Inventory System is a lightweight, on-premises asset management application designed for the UCF Student Academic Resource Center (SARC). It replaces a manual, spreadsheet-based system with a relational database and automates the checkout and return workflows of departmental technology (laptops, iPads, and accessories). 

The system operates entirely within the university network boundary, integrating USB hardware wedges (magnetic stripe card readers and barcode scanners) with local database storage and asynchronous cloud API validation to maintain FERPA compliance and an audit trail.

---

## System Architecture & Data Flow

The application is structured around a local-first, data-driven architecture. 

```
[Student Device] ➔ [Qualtrics Cloud]
                          │ (asynchronous survey submission)
                          ▼
[Kiosk Laptop]   ➔ [Qualtrics API] (12-hour freshness check)
   │ (hardware)           │
   ├── [USB Swiper] ➔ [ID Parsing] ➔ DB Verification (True/False)
   └── [USB Scanner] ➔ [Barcode]   ➔ SQLite State Update
                                         │
                                         ├── ➔ [Local inventory.db]
                                         ├── ➔ [SARC_History_Log.csv] (Ledger)
                                         └── ➔ [OneDrive Sync Folder] (Boss View)
```

1. **Transaction Authorization:** The student submits a digital liability agreement via Qualtrics on their personal device.
2. **Identity Verification:** The operator swipes the student's ID card. The local script parses the raw Track 1 magnetic stripe data to isolate the 7-digit UCF ID. 
3. **API Polling:** The system polls the Qualtrics API, retrieves the JSON survey payload, parses the timestamps, and verifies if a matching, completed agreement exists from the last 12 hours.
4. **Asset Matching & Bundling:** Once verified, the operator scans the physical asset's 2D Data Matrix barcode. The system reads the database for any pre-configured accessory bundles (e.g., charging bricks, cables) and prompts the operator to dynamically include or exclude those items.
5. **State & Ledger Synchronization:** The local SQLite database updates the asset status. Simultaneously, the event is appended to a local CSV history ledger, and the entire database is copied to a shared SharePoint/OneDrive folder for remote administrator reporting.

---

## Technical Features

* **Asynchronous API Integration:** Pulls compressed ZIP files of survey responses from Qualtrics in memory, extracts the raw JSON payloads, and parses them using multi-field criteria (finished states, custom question IDs, and ISO-8601 timestamps).
* **Fault-Tolerant Input Parsing:** Parses raw keyboard-wedge inputs. Isolates 7-digit IDs from raw Track 1 financial-card format, handles backward swipes, and rejects accidental equipment scans during the ID prompt using string prefix matching.
* **Graceful Degradation (Offline Mode):** If a network dropout occurs during API polling, the script catches the connection error and prompts the operator to trigger a manual administrative override, ensuring business operations are never blocked by infrastructure failures.
* **Conflict-Free Cloud Syncing:** Designed with write-locked exception handling. If an administrator has the synced OneDrive reporting files open in desktop Excel, the local transaction proceeds normally, caches the data in SQLite, and deferentially syncs to the cloud on the next successful write.
* **Declarative Database Rebuilds:** Built with separate schema provisioning and transactional state tracking. Relies on structured source CSV files to construct and populate the relational tables dynamically, ensuring clean migrations when physical inventory changes.

---

## Tech Stack & Environment
* **Language:** Python 3 (libraries: `sqlite3`, `requests`, `python-dotenv`, `csv`, `shutil`)
* **Database:** SQLite3
* **Hardware:** USB 2D Barcode Scanner, USB Magnetic Stripe Card Reader (Track 1 compatible)
* **Environment:** Windows (Local On-Premises Host)

---

## Database Schema

### Table: `serialized_assets`
Stores the static hardware definitions and active transaction states of uniquely serialized equipment.

| Column | Type | Description |
| :--- | :--- | :--- |
| `barcode_id` | TEXT (PK) | Primary Key (e.g., SARC-Laptop-01, SARC-iPad-05) |
| `equipment_type` | TEXT | Category of asset (Laptop, Tablet, Projector) |
| `brand_model` | TEXT | Specific manufacturer model (Dell Latitude 7420, iPad Air 4th Gen) |
| `service_tag` | TEXT | Manufacturer serial number |
| `status` | TEXT | Asset state (Available, Checked Out, In Repair, Unavailable) |
| `notes` | TEXT | Append-only history of physical notes and maintenance flags |
| `default_kit` | TEXT | Target bulk accessories bundled with this asset |
| `attached_bulk_items` | TEXT | Bulk items currently checked out with this specific asset |
| `current_ucf_id` | TEXT | UCF ID of the borrowing student (NULL if available) |
| `current_name` | TEXT | Name of the borrowing student (NULL if available) |
| `current_position` | TEXT | Role of the borrower (Tutor, SI Leader, Staff) |
| `current_email` | TEXT | UCF Email of the borrower |
| `current_duration` | TEXT | Intended loan length (e.g., Fall 2026) |
| `last_updated` | TEXT | Timestamp of the most recent transaction |

### Table: `bulk_assets`
Stores stock levels of interchangeable commodities (peripherals, chargers, adapters).

| Column | Type | Description |
| :--- | :--- | :--- |
| `item_name` | TEXT (PK) | Primary Key (e.g., Dell 65W C-type Charger, USB Mouse) |
| `quantity` | INTEGER | Active stock count currently in the storage closet |
| `category` | TEXT | Category grouping (Charger, Peripherals, Cables, Power) |
| `notes` | TEXT | Storage location or administrative details |
| `last_updated` | TEXT | Timestamp of the most recent stock level adjustment |

---

## Configuration & Environment Variables

The application requires a `.env` file in the root directory to store sensitive API credentials and specific survey IDs. This file is ignored by Git to prevent credential exposure.

```text
QUALTRICS_API_TOKEN=your_qualtrics_api_token_here
DATA_CENTER=ca1.qualtrics.com
SURVEY_REQUEST=SV_your_request_survey_id_here
SURVEY_CHECKOUT=SV_your_checkout_survey_id_here
SURVEY_RETURN=SV_your_return_survey_id_here
```

---

## Directory Structure

```text
SARC_Inventory_App/
│   .env                    # Ignored by Git (API credentials)
│   .gitignore              # Specifies untracked files
│   README.md               # System documentation
│   run_kiosk.bat           # Desktop batch execution shortcut
│   tracker.py              # Main kiosk transaction loop
│   qualtrics_api.py        # Asynchronous Qualtrics API integrations
│   setup_databases.py      # Database provisioning script
│   inventory.db            # Live local SQLite database
│   get_QID.py              # Development utility for mapping survey schema
│
└── source_data/            # Static baseline provisioning files
    ├── serialized_assets.csv
    └── bulk_assets.csv
```

---

## Setup and Installation

### 1. Provisioning the Local Environment
Ensure Python 3.x is installed on the host machine. Create your virtual environment and install the required dependencies:

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/Scripts/activate

# Install required external libraries
pip install requests python-dotenv
```

### 2. Initializing the Database
Ensure your baseline files (`serialized_assets.csv` and `bulk_assets.csv`) are configured inside the `source_data/` folder. Run the setup script to build the relational tables, import the baselines, and push the initial backups to OneDrive:

```bash
python setup_databases.py
```

### 3. Running the Kiosk
Launch the main application interface:

```bash
python tracker.py
```
*(Alternatively, execute `run_kiosk.bat` directly or through a shortcut on the Windows desktop to launch the system quickly in a dedicated kiosk CLI).*

---

## Roadmap

- [x] Phase 1: Python terminal logic and SQLite schema definition.
- [x] Phase 2: Bulk CSV import pipeline and data-driven schema migrations.
- [x] Phase 3: Hardware integration (USB Barcode Scanner & USB Magstripe Reader parsing).
- [ ] Phase 4: Local Web Application (Flask) hosted internally to replace the CLI with a multi-user browser interface.
- [ ] Phase 5: Automated weekly reporting scripts (generating unreturned asset lists and automated student email reminders).
