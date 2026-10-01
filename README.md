# SARC Equipment Inventory System

## Overview
The SARC Equipment Inventory System is an asset tracking and lifecycle management application built for the UCF Student Academic Resource Center. It replaces a legacy spreadsheet system with a SQLite database, automating the distribution, return, and auditing workflows of departmental technology (laptops, iPads, audio equipment, and peripherals).

Operating strictly within the university intranet to comply with IT regulations, the system combines physical USB hardware with asynchronous cloud API verification and a local-to-cloud automated data pipeline.

---

## Architecture & Data Pipeline

The system is built on an on-premises, decoupled architecture that isolates operational database writes from executive reporting views.

```
[Borrower Device] ➔ [Qualtrics Cloud]
                           │ (Survey Payload)
                           ▼
 [Kiosk Terminal] ➔ [Qualtrics API] (12-Hour Freshness Check)
        │                  │
        ├── [USB Swiper (Optional, can be typed)]   ➔ [RegEx Parser] ➔ Identity Verification
        └── [USB Scanner (Optional, can be typed)]  ➔ [Data Matrix Scan]     ➔ Relational State Transition
                                                                                │
                                                                                ▼
                                                                        [SQLite Engine]
                                                                        ├── equipment
                                                                        ├── users
                                                                        ├── loans (Active/History)
                                                                        └── bulk_assets
                                                                                │
                                                                                ▼ (SQL Views)
                                                                        [Automated Cloud Export]
                                                                        ├── SARC_Live_Inventory.csv
                                                                        ├── SARC_Live_Bulk.csv
                                                                        └── SARC_History_Log.csv
                                                                                │
                                                                                ▼
                                                                        [Power BI & Excel Dashboards]
```

### Key Architectural Decisions:
1. **Decoupled Reporting Layer:** Rather than exposing the active SQLite database directly in shared cloud environments (which causes file locking and corruption over syncing engines), the local backend generates structured, read-only analytical feeds via SQL Views. These feeds are then ingested by Power BI and Excel Power Query dashboards.
2. **Bidirectional State Sync:** To allow administrative maintenance on desktop workstations while checkouts run on a dedicated Kiosk laptop, the system uses timestamp-based differential synchronization (`sync_from_cloud()`) on initialization to prevent split-brain state conflicts.
3. **Data-Driven Hardware Bundling:** Accessories and chargers are linked dynamically via database records (`default_kit`) rather than hardcoded logic trees, prompting operators during transactions and automatically tracking attached accessories during return verification.

---

## Technical Features

* **Relational Schema Enforcement (3NF):** Completely decouples physical hardware attributes from user identities and transactional states, eliminating null-heavy tables and enforcing referential integrity across all loans.
* **Asynchronous Cloud API Validation:** Connects to the Qualtrics v3 API using compressed ZIP extractions in memory, enforcing a strict 12-hour validity window on digital signatures to prevent authorization replay attacks.
* **Hardware Wedge Stream Parsing:** Uses custom regular expressions to clean messy magnetic stripe inputs, dynamically isolating 7-digit student IDs from raw Track 1 card formats while preventing accidental barcode collisions.
* **Graceful Degradation & Overrides:** Includes an override mode that allows operators to bypass network dropouts, use cached or expired form metadata, and maintain operations during network outages.
* **Compliance & Auditing Suite:** Includes standalone analytical utilities (`audit_returns.py`, `audit_overdue.py`) that query the database engine to generate hit-lists of unreturned assets and missing liability signatures.
* **Live Administration Toolkit:** Features an isolated control panel (`admin_tools.py`) allowing administrators to ingest new serialized/bulk hardware, surplus decommissioned assets, or execute global primary key corrections without taking the live checkout kiosk offline.

---

## Relational Database Schema (3NF)

The database schema is normalized to Third Normal Form (3NF) to eliminate data redundancy and ensure transactional integrity.

### Table: `equipment`
Stores static hardware definitions, serials, and base operational availability.
* `barcode_id` (TEXT, PK): Unique departmental asset tag (e.g., `SARC-Laptop-01`)
* `equipment_type` (TEXT): Asset classification (Laptop, Tablet, Projector, etc.)
* `brand_model` (TEXT): Manufacturer specifications
* `service_tag` (TEXT): Hardware serial number / Dell Service Tag
* `default_kit` (TEXT): Pipe-delimited list of default bundled bulk accessories
* `notes` (TEXT): Permanent hardware notes and physical maintenance flags
* `status` (TEXT): Asset state (`Available`, `Checked Out`, `Unavailable`)
* `last_updated` (TEXT): ISO-8601 timestamp

### Table: `users`
Stores unique student, faculty, and staff identity records.
* `ucf_id` (TEXT, PK): Unique 7-digit institutional identifier
* `name` (TEXT): Full borrower name
* `position` (TEXT): Departmental role (Tutor, SI Leader, Staff, etc.)
* `email` (TEXT): Borrower email address
* `last_updated` (TEXT): ISO-8601 timestamp

### Table: `loans`
Manages both active states and historical checkout lifecycles via timestamp verification.
* `transaction_id` (INTEGER, PK, AUTOINCREMENT): Unique loan event ID
* `barcode_id` (TEXT, FK): References `equipment(barcode_id)`
* `ucf_id` (TEXT, FK): References `users(ucf_id)`
* `time_out` (TEXT): Timestamp when item departed the closet
* `time_in` (TEXT): Timestamp when returned (`NULL` indicates active checkout)
* `duration` (TEXT): Approved loan duration (e.g., `Fall 2026`)
* `attached_bulk` (TEXT): Specific bulk accessories loaned with this asset
* `action_out` (TEXT): Checkout classification (`CHECK-OUT`, `CHECK-OUT (OVERRIDE)`)
* `action_in` (TEXT): Return classification (`RETURN`, `RETURN (OVERRIDE)`)

### Table: `bulk_assets`
Maintains live quantity stock counts for unbarcoded commodities.
* `item_name` (TEXT, PK): Unique commodity description (e.g., `Dell 65W C-type Charger`)
* `quantity` (INTEGER): Active count on hand
* `category` (TEXT): Classification (Chargers, Cables, Peripherals, Adapters)
* `notes` (TEXT): Cabinet location or storage details
* `last_updated` (TEXT): ISO-8601 timestamp

### Table: `bulk_transactions`
Ledger tracking arithmetic increments/decrements for bulk stock.
* `transaction_id` (INTEGER, PK, AUTOINCREMENT)
* `item_name` (TEXT, FK): References `bulk_assets(item_name)`
* `qty_change` (INTEGER): Positive (return) or negative (distribution) value
* `action_type` (TEXT): Event description
* `ucf_id` (TEXT): Operator or recipient identifier
* `student_name` (TEXT): Recipient name
* `timestamp` (TEXT): ISO-8601 timestamp

### Table: `admin_logs`
Immutable audit log tracking all administrative interventions.
* `log_id` (INTEGER, PK, AUTOINCREMENT)
* `timestamp` (TEXT): Time of administrative action
* `operator` (TEXT): Windows username executing the action
* `action` (TEXT): Action type (`INGEST_ASSET`, `SURPLUS_ASSET`, `FIX_TYPO_ID`)
* `target_barcode` (TEXT): Modified entity
* `details` (TEXT): Specific values altered or before/after changes

---

## SQL Reporting Views

* **`vw_dashboard_live`:** Joins `equipment`, active `loans` (`time_in IS NULL`), and `users` to present a unified real-time dashboard of all serialized assets, current holders, and outstanding accessories.
* **`vw_loan_history`:** Joins closed `loans` (`time_in IS NOT NULL`), `equipment`, and `users` to supply a complete, chronological record of equipment returns.

---

## Configuration & Environment Variables

Environment variables are isolated in a local `.env` file to prevent credential exposure in version control:

```text
QUALTRICS_API_TOKEN=your_token_here
DATA_CENTER=ca1.qualtrics.com
SURVEY_REQUEST=SV_xxx
SURVEY_CHECKOUT=SV_xxx
SURVEY_RETURN=SV_xxx
```

---

## Setup & Deployment

### 1. Environment Configuration
Ensure Python 3.10+ and Git are installed. Clone the repository and install dependencies locally:

```cmd
git clone https://github.com/TheFish1236/SARC-Inventory-System.git
cd SARC-Inventory-System
python -m pip install --user -r requirements.txt
```

### 2. Live Operations
* **Launch Kiosk:** Run `run_kiosk.bat` or execute `python tracker.py`.
* **Launch Administrative Tools:** Execute `python admin_tools.py` to access hardware ingestion, asset surplusing, or identity corrections.
* **Run Audits:** Execute `python audit_returns.py` or `python audit_overdue.py` to parse compliance exceptions directly from the database engine.

---

## Project Status

The SARC Equipment Inventory System has completed its active development lifecycle and is currently in stable production, supporting live operations starting Fall 2026.

*   **Production Deployment:** Successfully provisioned across dedicated on-premises hardware.
*   **Architectural Hardening:** Evaluated and successfully migrated from an initial flat-file CSV model to a fully normalized (3NF) relational architecture.
*   **Interface Selection:** Implemented an enterprise ETL reporting pipeline utilizing Power BI and Excel Power Query over local SharePoint endpoints, bypassing any form of hosting to eliminate an attack surface and comply with strict university firewall policies.