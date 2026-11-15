# LifeLink — runnable local full-stack demo

This project connects the public donor website and the blood-bank/hospital portal to
one Python backend and one SQLite database.

## 1. Requirements
- Python 3.10 or newer
- Internet connection only for the first installation of the Python packages

## 2. Start on Windows
Open PowerShell in this `lifelink_fullstack` folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m uvicorn app:app --reload
```

If PowerShell blocks activation, run this once in the same PowerShell window:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Then open:
- Public donor website: http://127.0.0.1:8000/
- Institution portal: http://127.0.0.1:8000/institution
- API documentation: http://127.0.0.1:8000/docs

## 3. Demo institution login
- Email: `admin@lifelink.test`
- Password: `LifeLink123!`

Change the demo password before using this beyond a local classroom demonstration.
The database file `lifelink.db` is created automatically beside `app.py`.

## 4. What works
- A donor can submit a blood-donor application on the public site.
- The application is saved in SQLite and appears in the institution portal.
- The institution can mark an application reviewed, approved, or declined.
- An institution can add, update, publish, hide, and delete inventory entries.
- Published inventory is visible on the public website.
- A blood request can be submitted and saved in the database.

## 5. Important limitations
This is a local learning/demo application, not a production medical service.
It does not send real SMS, WhatsApp, email, or push notifications. It does not
verify donors, hospitals, blood units, or medical eligibility. The login uses a
simple in-memory demo session and must be replaced with production authentication,
HTTPS, role-based access, rate limiting, audit logs, secure secrets, and backups.
Do not enter real patient or donor sensitive information. Public pages do not show
donor phone numbers or exact home addresses.

The database is local to the computer running the server. To let users access it
from different devices, deploy the backend and database to a secure hosted service.
