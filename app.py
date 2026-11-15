from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, EmailStr, ConfigDict

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "lifelink.db"

app = FastAPI(title="LifeLink API", version="1.0.0",
              description="Local learning demo for blood donor applications and blood inventory.")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Demo account. Replace with proper user management before deployment.
DEMO_EMAIL = "admin@lifelink.test"
DEMO_PASSWORD = "LifeLink123!"
SESSIONS: dict[str, dict] = {}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS institutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            city TEXT NOT NULL,
            address TEXT DEFAULT '',
            phone TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS donor_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT DEFAULT '',
            blood_group TEXT NOT NULL,
            city TEXT NOT NULL,
            area TEXT DEFAULT '',
            donation_centre TEXT NOT NULL,
            preferred_date TEXT DEFAULT '',
            preferred_time TEXT DEFAULT '',
            availability TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            institution_id INTEGER NOT NULL,
            blood_group TEXT NOT NULL,
            component TEXT NOT NULL,
            units INTEGER NOT NULL CHECK(units >= 0),
            note TEXT DEFAULT '',
            is_published INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(institution_id) REFERENCES institutions(id)
        );
        CREATE TABLE IF NOT EXISTS blood_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            component TEXT NOT NULL,
            units INTEGER NOT NULL,
            city TEXT NOT NULL,
            hospital TEXT DEFAULT '',
            details TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        """)
        existing = con.execute("SELECT id FROM institutions WHERE email=?", (DEMO_EMAIL,)).fetchone()
        if not existing:
            con.execute(
                "INSERT INTO institutions(name,email,city,address,phone) VALUES(?,?,?,?,?)",
                ("LifeLink Demo Blood Bank", DEMO_EMAIL, "Guntur", "Demo address — replace with your institution", "0000000000")
            )
        inst_id = con.execute("SELECT id FROM institutions WHERE email=?", (DEMO_EMAIL,)).fetchone()["id"]
        count = con.execute("SELECT COUNT(*) AS n FROM inventory WHERE institution_id=?", (inst_id,)).fetchone()["n"]
        if count == 0:
            now = datetime.now().isoformat(timespec="minutes")
            sample = [
                ("A+", "Whole Blood", 8), ("B+", "Whole Blood", 5),
                ("O+", "Whole Blood", 12), ("AB+", "Plasma", 3),
                ("O-", "RBC", 2)
            ]
            con.executemany(
                """INSERT INTO inventory(institution_id,blood_group,component,units,note,is_published,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                [(inst_id, bg, comp, units, "Sample/demo stock — verify before relying on it", 1, now)
                 for bg, comp, units in sample]
            )


init_db()


class DonorApplication(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=7, max_length=20)
    email: str = Field(default="", max_length=120)
    blood_group: str
    city: str = Field(min_length=2, max_length=80)
    area: str = Field(default="", max_length=100)
    donation_centre: str = Field(min_length=2, max_length=150)
    preferred_date: str = ""
    preferred_time: str = ""
    availability: str = ""
    notes: str = Field(default="", max_length=500)


class BloodRequest(BaseModel):
    requester_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=7, max_length=20)
    blood_group: str
    component: str = "Whole Blood"
    units: int = Field(ge=1, le=20)
    city: str = Field(min_length=2, max_length=80)
    hospital: str = Field(default="", max_length=150)
    details: str = Field(default="", max_length=500)


class LoginInput(BaseModel):
    email: str
    password: str


class InventoryInput(BaseModel):
    blood_group: str
    component: str
    units: int = Field(ge=0, le=10000)
    note: str = Field(default="", max_length=300)
    is_published: bool = True


class StatusInput(BaseModel):
    status: str


def require_institution(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Please log in.")
    token = authorization.split(" ", 1)[1]
    session = SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    return session


@app.get("/")
def donor_site():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/institution")
def institution_site():
    return FileResponse(STATIC_DIR / "institution.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "database": "SQLite", "message": "LifeLink backend is running"}


@app.post("/api/donors")
def create_donor(payload: DonorApplication):
    allowed = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
    if payload.blood_group not in allowed:
        raise HTTPException(status_code=400, detail="Choose a valid blood group.")
    now = datetime.now().isoformat(timespec="seconds")
    with db() as con:
        cur = con.execute("""
            INSERT INTO donor_applications
            (full_name,phone,email,blood_group,city,area,donation_centre,preferred_date,
             preferred_time,availability,notes,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """, (payload.full_name, payload.phone, payload.email, payload.blood_group,
              payload.city, payload.area, payload.donation_centre, payload.preferred_date,
              payload.preferred_time, payload.availability, payload.notes, now))
        application_id = cur.lastrowid
    return {"message": "Application submitted. The selected institution can now review it.",
            "application_id": application_id}


@app.get("/api/inventory")
def public_inventory(blood_group: Optional[str] = None, city: Optional[str] = None):
    sql = """
      SELECT i.id, i.blood_group, i.component, i.units, i.updated_at,
             b.name AS institution_name, b.city, b.address
      FROM inventory i JOIN institutions b ON b.id=i.institution_id
      WHERE i.is_published=1 AND i.units > 0
    """
    params = []
    if blood_group:
        sql += " AND i.blood_group=?"
        params.append(blood_group)
    if city:
        sql += " AND lower(b.city)=lower(?)"
        params.append(city)
    sql += " ORDER BY b.city, i.blood_group, i.component"
    with db() as con:
        rows = con.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/blood-requests")
def create_blood_request(payload: BloodRequest):
    allowed = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
    if payload.blood_group not in allowed:
        raise HTTPException(status_code=400, detail="Choose a valid blood group.")
    with db() as con:
        cur = con.execute("""
          INSERT INTO blood_requests(requester_name,phone,blood_group,component,units,city,hospital,details,created_at)
          VALUES(?,?,?,?,?,?,?,?,?)
        """, (payload.requester_name, payload.phone, payload.blood_group, payload.component,
              payload.units, payload.city, payload.hospital, payload.details,
              datetime.now().isoformat(timespec="seconds")))
        rid = cur.lastrowid
    return {"message": "Blood request saved. This demo does not automatically contact blood banks or donors.",
            "request_id": rid}


@app.post("/api/institution/login")
def login(payload: LoginInput):
    if payload.email.lower() != DEMO_EMAIL or payload.password != DEMO_PASSWORD:
        raise HTTPException(status_code=401, detail="Incorrect demo email or password.")
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {"institution_id": 1, "email": DEMO_EMAIL}
    with db() as con:
        institution = con.execute("SELECT * FROM institutions WHERE email=?", (DEMO_EMAIL,)).fetchone()
    return {"token": token, "institution": dict(institution)}


@app.get("/api/institution/me")
def institution_me(session=Depends(require_institution)):
    with db() as con:
        row = con.execute("SELECT * FROM institutions WHERE id=?", (session["institution_id"],)).fetchone()
    return dict(row)


@app.get("/api/institution/dashboard")
def dashboard(session=Depends(require_institution)):
    iid = session["institution_id"]
    with db() as con:
        pending = con.execute("SELECT COUNT(*) n FROM donor_applications WHERE status='Pending'").fetchone()["n"]
        approved = con.execute("SELECT COUNT(*) n FROM donor_applications WHERE status='Approved'").fetchone()["n"]
        stock = con.execute("SELECT COALESCE(SUM(units),0) n FROM inventory WHERE institution_id=? AND is_published=1", (iid,)).fetchone()["n"]
        groups = con.execute("SELECT COUNT(DISTINCT blood_group) n FROM inventory WHERE institution_id=? AND is_published=1", (iid,)).fetchone()["n"]
    return {"pending_applications": pending, "approved_applications": approved,
            "published_units": stock, "blood_groups_listed": groups}


@app.get("/api/institution/applications")
def applications(session=Depends(require_institution)):
    with db() as con:
        rows = con.execute("SELECT * FROM donor_applications ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


@app.patch("/api/institution/applications/{application_id}")
def update_application(application_id: int, payload: StatusInput, session=Depends(require_institution)):
    if payload.status not in {"Pending", "Reviewed", "Approved", "Declined"}:
        raise HTTPException(status_code=400, detail="Invalid application status.")
    with db() as con:
        cur = con.execute("UPDATE donor_applications SET status=? WHERE id=?",
                          (payload.status, application_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Application not found.")
    return {"message": f"Application marked {payload.status}."}


@app.get("/api/institution/inventory")
def institution_inventory(session=Depends(require_institution)):
    with db() as con:
        rows = con.execute("SELECT * FROM inventory WHERE institution_id=? ORDER BY id DESC",
                           (session["institution_id"],)).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/institution/inventory")
def add_inventory(payload: InventoryInput, session=Depends(require_institution)):
    allowed = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
    components = {"Whole Blood", "RBC", "Platelets", "Plasma"}
    if payload.blood_group not in allowed or payload.component not in components:
        raise HTTPException(status_code=400, detail="Invalid blood group or component.")
    with db() as con:
        cur = con.execute("""
          INSERT INTO inventory(institution_id,blood_group,component,units,note,is_published,updated_at)
          VALUES(?,?,?,?,?,?,?)
        """, (session["institution_id"], payload.blood_group, payload.component, payload.units,
              payload.note, int(payload.is_published), datetime.now().isoformat(timespec="minutes")))
        new_id = cur.lastrowid
    return {"id": new_id, "message": "Inventory entry added."}


@app.put("/api/institution/inventory/{item_id}")
def edit_inventory(item_id: int, payload: InventoryInput, session=Depends(require_institution)):
    with db() as con:
        cur = con.execute("""
          UPDATE inventory SET blood_group=?,component=?,units=?,note=?,is_published=?,updated_at=?
          WHERE id=? AND institution_id=?
        """, (payload.blood_group, payload.component, payload.units, payload.note,
              int(payload.is_published), datetime.now().isoformat(timespec="minutes"),
              item_id, session["institution_id"]))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Inventory entry not found.")
    return {"message": "Inventory entry updated."}


@app.delete("/api/institution/inventory/{item_id}")
def delete_inventory(item_id: int, session=Depends(require_institution)):
    with db() as con:
        cur = con.execute("DELETE FROM inventory WHERE id=? AND institution_id=?",
                          (item_id, session["institution_id"]))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Inventory entry not found.")
    return {"message": "Inventory entry deleted."}


@app.post("/api/institution/logout")
def logout(authorization: Optional[str] = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        SESSIONS.pop(authorization.split(" ", 1)[1], None)
    return {"message": "Logged out."}
