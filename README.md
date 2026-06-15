# UCF SARC Inventory Management System

## Overview
A lightweight, automated inventory tracking system designed for the UCF Student Academic Resource Center (SARC). This system replaces a manual Excel/Qualtrics workflow with an automated, secure SQLite database. 

It integrates physical hardware (barcode scanners and magstripe readers) to streamline the checkout/return process of department equipment (laptops, iPads, etc.), eliminating data-entry errors and providing an accurate chain-of-custody.

## Features
* **Automated Checkout/Return:** Toggle device status by scanning a physical barcode.
* **Hardware Integration:** Supports keyboard-wedge barcode scanners and USB Magstripe readers (for scanning UCF ID cards).
* **Secure Local Database:** Uses SQLite to ensure student data (FERPA) remains on-premises and is not exposed to third-party cloud services.
* **Data Integrity:** Prevents duplicate entries and ensures accurate timestamping for every transaction.

## Tech Stack & Hardware
* **Language:** Python 3
* **Database:** SQLite3
* **Hardware:** USB Barcode Scanner, USB Magnetic Stripe Reader (Optional)
* **Environment:** Windows / Local On-Premises Host

## Setup and Installation
1. Clone this repository to your local machine.
2. Ensure Python 3.x is installed.
3. Run the main script:
   ```bash
   python tracker.py
   ```
*(Note: Upon first run, the script will automatically generate the `inventory.db` file and build the required table.)*

## Roadmap / Future Architecture
- [x] Phase 1: Python terminal logic and SQLite database creation.
- [ ] Phase 2: Bulk import existing closet inventory via CSV script.
- [ ] Phase 3: Hardware Kiosk Setup (Acquire a dedicated checkout station).
- [ ] Phase 4: Local Web App (Flask/FastAPI) hosted on a static IP for internal UCF network access via Cisco VPN.
```
