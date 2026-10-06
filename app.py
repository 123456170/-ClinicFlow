# ClinicFlow: single-file Streamlit appointment and intake demo
# Runs immediately with seeded SQLite demo data.
# Gemini is optional; no API key required.

import os
import json
import random
import sqlite3
from datetime import date, datetime, time, timedelta
from html import escape
from typing import Literal, Optional

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pydantic import BaseModel, Field

try:
    import plotly.express as px
    HAS_PLOTLY = True
except Exception:
    HAS_PLOTLY = False

st.set_page_config(
    page_title="ClinicFlow",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_NAME = "ClinicFlow"
DEPARTMENTS = ["General Medicine", "Cardiology", "Orthopedics"]
STAFF_PASSWORD = os.getenv("CLINICFLOW_STAFF_PASSWORD", "clinic-demo")
GEMINI_MODEL = "gemini-2.0-flash"

RED_FLAGS = [
    "chest pain",
    "chest tightness",
    "difficulty breathing",
    "shortness of breath",
    "severe bleeding",
    "unconscious",
    "stroke",
    "face drooping",
    "slurred speech",
    "seizure",
    "anaphylaxis",
    "suicidal",
    "overdose",
]

CARDIO_WORDS = [
    "chest",
    "heart",
    "palpitation",
    "blood pressure",
    "bp",
    "cardiac",
    "breathless",
    "swelling in legs",
]

ORTHO_WORDS = [
    "back pain",
    "joint",
    "knee",
    "shoulder",
    "bone",
    "fracture",
    "sprain",
    "muscle",
    "orthopedic",
    "accident",
    "fall",
    "lifted",
    "ankle",
]

SOON_WORDS = [
    "fever",
    "vomiting",
    "dehydration",
    "persistent",
    "worsening",
    "severe",
    "infection",
    "rash",
    "four days",
    "two days",
    "three days",
]

REASONS = {
    "General Medicine": [
        "Persistent cough and mild fever for four days",
        "General fatigue and headache",
        "Medication refill for chronic condition",
        "Sore throat and runny nose",
        "Mild abdominal discomfort",
    ],
    "Cardiology": [
        "Chest tightness and shortness of breath",
        "Palpitations during exercise",
        "High blood pressure follow-up",
        "Swelling in legs and breathlessness",
        "Dizziness when standing",
    ],
    "Orthopedics": [
        "Knee pain after a fall",
        "Lower back pain after lifting",
        "Shoulder stiffness and reduced movement",
        "Ankle sprain while running",
        "Bone pain after accident",
    ],
}


class TriageResult(BaseModel):
    department: str
    urgency: Literal["routine", "soon", "urgent"]
    summary: str
    follow_up_questions: list[str] = Field(default_factory=list)


# ----------------------------
# Database layer
# ----------------------------

@st.cache_resource(show_spinner=False)
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    seed_demo(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS departments (
            name TEXT PRIMARY KEY,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            dob TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            department TEXT NOT NULL,
            slot_start TEXT NOT NULL,
            slot_end TEXT NOT NULL,
            urgency TEXT NOT NULL,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'scheduled',
            FOREIGN KEY(patient_id) REFERENCES patients(id)
        );

        CREATE TABLE IF NOT EXISTS intake_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER,
            summary TEXT,
            raw_text TEXT,
            FOREIGN KEY(appointment_id) REFERENCES appointments(id)
        );
        """
    )
    conn.commit()


def fetch_df(conn: sqlite3.Connection, query: str, params: tuple = ()) -> pd.DataFrame:
    cur = conn.execute(query, params)
    cols = [d[0] for d in cur.description]
    rows = [tuple(r) for r in cur.fetchall()]
    return pd.DataFrame(rows, columns=cols)


def seed_demo(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM patients")
    if cur.fetchone()[0] > 0:
        return

    rng = random.Random(20261006)

    cur.executemany(
        "INSERT OR IGNORE INTO departments (name, description) VALUES (?, ?)",
        [
            ("General Medicine", "Primary care and general complaints"),
            ("Cardiology", "Heart, blood pressure, and circulation concerns"),
            ("Orthopedics", "Bones, joints, muscles, and injury follow-up"),
        ],
    )

    patients = [
        ("Amina Yusuf", "+1 555 0101", "1990-05-14"),
        ("Jordan Lee", "+1 555 0102", "1984-11-02"),
        ("Priya Nair", "+1 555 0103", "1995-03-21"),
        ("Daniel Okafor", "+1 555 0104", "1978-07-30"),
        ("Sofia Martinez", "+1 555 0105", "2000-01-18"),
        ("Ethan Brooks", "+1 555 0106", "1969-09-09"),
        ("Lily Chen", "+1 555 0107", "1992-12-05"),
        ("Omar Haddad", "+1 555 0108", "1987-06-17"),
        ("Grace Adeyemi", "+1 555 0109", "1998-02-28"),
        ("Noah Schmidt", "+1 555 0110", "1975-10-11"),
        ("Maya Patel", "+1 555 0111", "1993-04-04"),
        ("Lucas Silva", "+1 555 0112", "1981-08-23"),
        ("Emma Wilson", "+1 555 0113", "2001-05-06"),
        ("Yusuf Demir", "+1 555 0114", "1989-01-31"),
        ("Chloe Dubois", "+1 555 0115", "1996-07-19"),
        ("Samuel Green", "+1 555 0116", "1972-03-12"),
        ("Isla Thompson", "+1 555 0117", "1999-11-27"),
        ("Ravi Kumar", "+1 555 0118", "1986-09-15"),
        ("Zara Ahmed", "+1 555 0119", "1994-10-03"),
        ("Felix Wagner", "+1 555 0120", "1980-02-14"),
        ("Nina Petrova", "+1 555 0121", "1997-06-25"),
        ("Tomas Novak", "+1 555 0122", "1976-12-09"),
        ("Leila Mansour", "+1 555 0123", "1991-08-08"),
        ("Jack Miller", "+1 555 0124", "2002-04-16"),
    ]

    patient_ids = []
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for name, phone, dob in patients:
        cur.execute(
            "INSERT INTO patients (name, phone, dob, created_at) VALUES (?, ?, ?, ?)",
            (name, phone, dob, now_iso),
        )
        patient_ids.append(cur.lastrowid)

    today = date.today()
    now = datetime.now()
    used = set()
    appt_count = 0

    def add_appt(department: str, slot_start: datetime, urgency: str, reason: str, status: str) -> None:
        nonlocal appt_count
        slot_end = slot_start + timedelta(hours=1)
        patient_id = rng.choice(patient_ids)
        cur.execute(
            """
            INSERT INTO appointments
                (patient_id, department, slot_start, slot_end, urgency, reason, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id,
                department,
                slot_start.strftime("%Y-%m-%d %H:%M:%S"),
                slot_end.strftime("%Y-%m-%d %H:%M:%S"),
                urgency,
                reason,
                status,
            ),
        )
        used.add((department, slot_start.date(), slot_start.hour))
        appt_count += 1

    forced = [
        (0, 9, "routine", "Persistent cough and mild fever for four days", "scheduled"),
        (1, 9, "urgent", "Chest tightness and shortness of breath", "scheduled"),
        (2, 10, "soon", "Knee pain after a fall, difficulty walking", "scheduled"),
        (0, 10, "soon", "Fever and sore throat for two days", "completed"),
        (1, 11, "routine", "Follow-up for blood pressure monitoring", "scheduled"),
        (2, 11, "urgent", "Severe back pain after accident", "no_show"),
        (0, 13, "routine", "Medication refill and general check", "cancelled"),
        (1, 14, "soon", "Palpitations during exercise", "scheduled"),
    ]

    for dept_idx, hour, urgency, reason, status in forced:
        department = DEPARTMENTS[dept_idx]
        slot = datetime.combine(today, time(hour, 0))
        if (department, today, hour) not in used:
            add_appt(department, slot, urgency, reason, status)

    attempts = 0
    while appt_count < 40 and attempts < 3000:
        attempts += 1
        day_offset = rng.choice([-2, -1, 0, 1, 2, 3, 4])
        d = today + timedelta(days=day_offset)
        hour = rng.randint(9, 16)
        department = rng.choice(DEPARTMENTS)

        if (department, d, hour) in used:
            continue

        slot_start = datetime.combine(d, time(hour, 0))

        if d < today:
            status = rng.choices(
                ["completed", "no_show", "cancelled"],
                weights=[0.75, 0.15, 0.10],
            )[0]
        elif d == today:
            if slot_start < now:
                status = rng.choices(
                    ["completed", "no_show", "cancelled"],
                    weights=[0.80, 0.15, 0.05],
                )[0]
            else:
                status = rng.choices(["scheduled", "cancelled"], weights=[0.92, 0.08])[0]
        else:
            status = rng.choices(["scheduled", "cancelled"], weights=[0.94, 0.06])[0]

        urgency = rng.choices(["routine", "soon", "urgent"], weights=[0.60, 0.30, 0.10])[0]
        reason = rng.choice(REASONS[department])

        if any(flag in reason.lower() for flag in RED_FLAGS):
            urgency = "urgent"

        add_appt(department, slot_start, urgency, reason, status)

    note_rows = cur.execute("SELECT id, reason FROM appointments ORDER BY id LIMIT 15").fetchall()
    for row in note_rows:
        aid, reason = row[0], row[1]
        summary = f"Demo intake summary: {str(reason)[:90]}"
        cur.execute(
            "INSERT INTO intake_notes (appointment_id, summary, raw_text) VALUES (?, ?, ?)",
            (aid, summary, reason),
        )

    conn.commit()


def create_patient(conn: sqlite3.Connection, name: str, phone: str, dob: str) -> int:
    cur = conn.execute(
        "INSERT INTO patients (name, phone, dob, created_at) VALUES (?, ?, ?, ?)",
        (name.strip(), phone.strip(), dob, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    return int(cur.lastrowid)


def ensure_patient(conn: sqlite3.Connection, name: str, phone: str, dob: str) -> int:
    row = conn.execute(
        "SELECT id FROM patients WHERE phone = ? OR name = ? LIMIT 1",
        (phone.strip(), name.strip()),
    ).fetchone()
    if row:
        return int(row[0])
    return create_patient(conn, name, phone, dob)


def search_patient(conn: sqlite3.Connection, query: str) -> pd.DataFrame:
    q = f"%{query.strip()}%"
    return fetch_df(
        conn,
        """
        SELECT id, name, phone, dob, created_at
        FROM patients
        WHERE name LIKE ? OR phone LIKE ?
        ORDER BY name
        """,
        (q, q),
    )


def list_by_day(conn: sqlite3.Connection, day: date) -> pd.DataFrame:
    return fetch_df(
        conn,
        """
        SELECT
            a.id,
            a.patient_id,
            p.name,
            p.phone,
            a.department,
            a.slot_start,
            a.slot_end,
            a.urgency,
            a.reason,
            a.status
        FROM appointments a
        JOIN patients p ON p.id = a.patient_id
        WHERE date(a.slot_start) = ?
        ORDER BY a.slot_start
        """,
        (day.isoformat(),),
    )


def appointments_between(conn: sqlite3.Connection, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    return fetch_df(
        conn,
        """
        SELECT
            a.id,
            a.patient_id,
            p.name,
            p.phone,
            a.department,
            a.slot_start,
            a.slot_end,
            a.urgency,
            a.reason,
            a.status
        FROM appointments a
        JOIN patients p ON p.id = a.patient_id
        WHERE a.slot_start >= ? AND a.slot_start < ?
        ORDER BY a.slot_start
        """,
        (
            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )


def is_slot_free(conn: sqlite3.Connection, department: str, start: datetime, end: datetime) -> bool:
    count = conn.execute(
        """
        SELECT COUNT(*)
        FROM appointments
        WHERE department = ?
          AND status = 'scheduled'
          AND slot_start < ?
          AND slot_end > ?
        """,
        (
            department,
            start.strftime("%Y-%m-%d %H:%M:%S"),
            end.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    ).fetchone()[0]
    return int(count) == 0


def book_slot(
    conn: sqlite3.Connection,
    patient_id: int,
    department: str,
    slot_start: str,
    slot_end: str,
    urgency: str,
    reason: str,
) -> tuple[bool, str | int]:
    if department not in DEPARTMENTS:
        return False, "Unknown department."

    try:
        start_dt = datetime.fromisoformat(slot_start.replace(" ", "T"))
        end_dt = datetime.fromisoformat(slot_end.replace(" ", "T"))
    except Exception:
        return False, "Invalid slot time."

    if start_dt >= end_dt:
        return False, "Slot end must be after slot start."

    if start_dt < datetime.now():
        return False, "Cannot book a slot in the past."

    conflict = conn.execute(
        """
        SELECT COUNT(*)
        FROM appointments
        WHERE status = 'scheduled'
          AND (
                (department = ? AND slot_start < ? AND slot_end > ?)
             OR (patient_id = ? AND slot_start < ? AND slot_end > ?)
          )
        """,
        (
            department,
            slot_start,
            slot_end,
            patient_id,
            slot_start,
            slot_end,
        ),
    ).fetchone()[0]

    if int(conflict) > 0:
        return False, "Double booking rejected: slot or patient already has an appointment."

    cur = conn.execute(
        """
        INSERT INTO appointments
            (patient_id, department, slot_start, slot_end, urgency, reason, status)
        VALUES (?, ?, ?, ?, ?, ?, 'scheduled')
        """,
        (patient_id, department, slot_start, slot_end, urgency, reason),
    )
    conn.commit()
    return True, int(cur.lastrowid)


def set_status(conn: sqlite3.Connection, appointment_id: int, status: str) -> bool:
    if status not in {"scheduled", "completed", "cancelled", "no_show"}:
        return False
    cur = conn.execute(
        "UPDATE appointments SET status = ? WHERE id = ?",
        (status, appointment_id),
    )
    conn.commit()
    return cur.rowcount > 0


def cancel_appointment(conn: sqlite3.Connection, appointment_id: int) -> bool:
    return set_status(conn, appointment_id, "cancelled")


def available_slots(
    conn: sqlite3.Connection,
    department: str,
    days: int = 14,
    limit: int = 6,
) -> list[tuple[datetime, datetime]]:
    slots = []
    now = datetime.now()

    for day_offset in range(days):
        d = date.today() + timedelta(days=day_offset)
        for hour in range(9, 17):
            start = datetime.combine(d, time(hour, 0))
            if start <= now:
                continue
            end = start + timedelta(hours=1)
            if is_slot_free(conn, department, start, end):
                slots.append((start, end))
                if len(slots) >= limit:
                    return slots
    return slots


# ----------------------------
# AI triage layer
# ----------------------------

SYSTEM_INSTRUCTION = """
You are ClinicFlow administrative triage assistant.
Your job is routing only. Never diagnose. Never provide treatment advice.
If red-flag emergency symptoms are mentioned, instruct the patient to call emergency services immediately.
Return strict JSON only with these keys:
- department: one of General Medicine, Cardiology, Orthopedics
- urgency: one of routine, soon, urgent
- summary: short administrative routing summary
- follow_up_questions: array of exactly 3 short patient-friendly questions
""".strip()


def _clean_text(value: str, limit: int = 240) -> str:
    return " ".join(str(value).split())[:limit]


def local_triage(reason_text: str) -> TriageResult:
    text = _clean_text(reason_text)
    lower = text.lower()

    red_flag = any(flag in lower for flag in RED_FLAGS)

    if any(word in lower for word in CARDIO_WORDS):
        department = "Cardiology"
    elif any(word in lower for word in ORTHO_WORDS):
        department = "Orthopedics"
    else:
        department = "General Medicine"

    if red_flag:
        urgency = "urgent"
    elif any(word in lower for word in SOON_WORDS):
        urgency = "soon"
    else:
        urgency = "routine"

    if department == "Cardiology":
        first_q = "Do you have a history of heart disease or high blood pressure?"
    elif department == "Orthopedics":
        first_q = "Which body part is affected, and was there an injury?"
    else:
        first_q = "Do you have fever, cough, or fatigue?"

    follow_up_questions = [
        first_q,
        "How many days have you had this problem?",
        "On a scale of 0 to 10, how severe is it right now?",
    ]

    summary = (
        f"Administrative routing only. Reported concern: {text or 'No detail provided'}. "
        f"Suggested department: {department}. Urgency: {urgency}."
    )

    if red_flag:
        summary += (
            " Red-flag symptoms were mentioned. Call emergency services now. "
            "This app is for scheduling and routing only, not diagnosis."
        )

    return TriageResult(
        department=department,
        urgency=urgency,
        summary=summary,
        follow_up_questions=follow_up_questions,
    )


def gemini_triage(reason_text: str) -> Optional[TriageResult]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types
    except Exception:
        return None

    prompt = f"Patient reason: {_clean_text(reason_text, 500)}\nReturn JSON only."

    try:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.1,
        )

        last_error: Optional[Exception] = None
        for _ in range(3):
            try:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[prompt],
                    config=config,
                )
                raw = getattr(response, "text", "") or ""
                raw = raw.strip()

                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]

                data = json.loads(raw)
                result = TriageResult.model_validate(data)

                if result.department not in DEPARTMENTS:
                    result.department = "General Medicine"

                if not result.follow_up_questions:
                    result.follow_up_questions = local_triage(reason_text).follow_up_questions

                result.follow_up_questions = [str(q).strip() for q in result.follow_up_questions][:3]
                result.summary = _clean_text(result.summary, 500)
                return result
            except Exception as exc:
                last_error = exc
                continue

        return None
    except Exception:
        return None


def triage(reason_text: str) -> TriageResult:
    ai_result = gemini_triage(reason_text)
    if ai_result is not None:
        return ai_result
    return local_triage(reason_text)


def local_reminder(first_name: str, department: str, slot_start: str, urgency: str) -> str:
    try:
        dt = datetime.fromisoformat(slot_start.replace(" ", "T"))
        day = dt.strftime("%A, %d %B %Y")
        clock = dt.strftime("%H:%M")
    except Exception:
        day = slot_start
        clock = ""

    urgent_line = ""
    if urgency == "urgent":
        urgent_line = "\nIf your symptoms are severe or worsening, call emergency services immediately."

    return (
        f"Hello {first_name},\n\n"
        f"This is a friendly reminder from {APP_NAME} for your {department} appointment "
        f"on {day}{(' at ' + clock) if clock else ''}.\n\n"
        "Please arrive 10 minutes early and bring your ID and any relevant documents.\n"
        "If you need to reschedule, contact the clinic using the number on your confirmation."
        f"{urgent_line}\n\n"
        "Warm regards,\n"
        f"{APP_NAME} Team"
    )


def gemini_reminder(first_name: str, department: str, slot_start: str, urgency: str) -> Optional[str]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai
    except Exception:
        return None

    prompt = (
        "Write a short, warm, patient-friendly appointment reminder. "
        "Do not diagnose or give medical advice. "
        "Include clinic contact guidance and arrival time. "
        "If urgency is urgent, add a clear emergency-services sentence. "
        f"First name: {first_name}. Department: {department}. "
        f"Slot: {slot_start}. Urgency: {urgency}."
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        text = (getattr(response, "text", "") or "").strip()
        return text or None
    except Exception:
        return None


def generate_reminder(first_name: str, department: str, slot_start: str, urgency: str) -> str:
    ai_text = gemini_reminder(first_name, department, slot_start, urgency)
    if ai_text:
        return ai_text
    return local_reminder(first_name, department, slot_start, urgency)


# ----------------------------
# UI helpers
# ----------------------------

CSS = """
<style>
.cf-slot {
    border: 1px solid #d0d7de;
    border-radius: 12px;
    padding: 14px;
    margin-bottom: 10px;
    background: #f6f8fa;
}
.cf-event {
    border-radius: 10px;
    padding: 8px;
    margin: 6px 0;
    color: white;
    font-size: 0.84rem;
    line-height: 1.25;
}
.cf-empty {
    border-top: 1px dashed #d0d7de;
    padding: 6px 0;
    color: #8c959f;
    font-size: 0.76rem;
}
.cf-confirmation {
    border: 1px solid #1f2937;
    border-radius: 14px;
    padding: 22px;
    background: white;
    color: #111827;
}
.cf-confirmation h2 {
    margin-top: 0;
}
@media print {
    .stSidebar,
    .stButton,
    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"] {
        display: none !important;
    }
    .cf-confirmation {
        border: 1px solid black;
    }
}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def urgency_color(urgency: str) -> str:
    return {
        "routine": "#2e7d32",
        "soon": "#ed6c02",
        "urgent": "#d32f2f",
    }.get(urgency, "#455a64")


def status_color(status: str) -> str:
    return {
        "scheduled": "#1976d2",
        "completed": "#388e3c",
        "cancelled": "#9e9e9e",
        "no_show": "#616161",
    }.get(status, "#455a64")


def reset_intake() -> None:
    for key in [
        "intake_stage",
        "intake_chat",
        "intake_answers",
        "triage",
        "patient_id",
        "patient_name",
        "patient_phone",
        "patient_dob",
        "intake_reason",
        "booking_confirmation",
    ]:
        st.session_state.pop(key, None)


def render_confirmation() -> None:
    conf = st.session_state.booking_confirmation

    st.success("Appointment confirmed")

    components.html(
        """
        <button
          onclick="window.print()"
          style="padding:8px 14px;border-radius:8px;border:1px solid #1f2937;background:#111827;color:white;cursor:pointer;">
          Print confirmation
        </button>
        """,
        height=50,
    )

    st.markdown(
        f"""
        <div class="cf-confirmation">
          <h2>{APP_NAME} appointment confirmation</h2>
          <p><strong>Appointment ID:</strong> {escape(str(conf['appointment_id']))}</p>
          <p><strong>Patient:</strong> {escape(str(conf['patient_name']))}</p>
          <p><strong>Phone:</strong> {escape(str(conf['phone']))}</p>
          <p><strong>Department:</strong> {escape(str(conf['department']))}</p>
          <p><strong>Date:</strong> {escape(str(conf['date']))}</p>
          <p><strong>Time:</strong> {escape(str(conf['time']))}</p>
          <p><strong>Urgency:</strong> {escape(str(conf['urgency']).title())}</p>
          <p><strong>Reason:</strong> {escape(str(conf['reason']))}</p>
          <p><strong>Routing summary:</strong> {escape(str(conf['summary']))}</p>
          <hr>
          <p>Please arrive 10 minutes early. Bring ID and any relevant documents.</p>
          <p>This confirmation is administrative only and is not a medical diagnosis.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    plain = (
        f"{APP_NAME} appointment confirmation\n"
        f"Appointment ID: {conf['appointment_id']}\n"
        f"Patient: {conf['patient_name']}\n"
        f"Phone: {conf['phone']}\n"
        f"Department: {conf['department']}\n"
        f"Date: {conf['date']}\n"
        f"Time: {conf['time']}\n"
        f"Urgency: {conf['urgency']}\n"
        f"Reason: {conf['reason']}\n"
        f"Summary: {conf['summary']}\n"
    )

    st.download_button(
        "Download confirmation",
        data=plain,
        file_name=f"clinicflow_confirmation_{conf['appointment_id']}.txt",
        mime="text/plain",
    )

    if st.button("Start another intake"):
        reset_intake()
        st.rerun()


# ----------------------------
# Pages
# ----------------------------

def render_intake(conn: sqlite3.Connection) -> None:
    st.header("1. Patient intake")

    if st.session_state.get("booking_confirmation"):
        render_confirmation()
        return

    stage = st.session_state.get("intake_stage", "details")

    if stage == "details":
        st.caption("Demo mode: fields are prefilled so you can start immediately.")

        with st.form("intake_details"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Full name", value="Jordan Lee")
                phone = st.text_input("Phone", value="+1 555 0102")
            with col2:
                dob = st.date_input("Date of birth", value=date(1984, 11, 2), max_value=date.today())
                reason = st.text_area(
                    "Reason for visit",
                    value="I have had chest tightness and shortness of breath for two days.",
                    height=110,
                )

            submitted = st.form_submit_button("Start smart triage", type="primary")

        if submitted:
            errors = []
            if not name.strip():
                errors.append("Name is required.")
            digits = "".join(ch for ch in phone if ch.isdigit())
            if len(digits) < 7:
                errors.append("Enter a valid phone number.")
            if dob > date.today():
                errors.append("Date of birth cannot be in the future.")
            if len(reason.strip()) < 10:
                errors.append("Please describe the reason in at least 10 characters.")

            if errors:
                for err in errors:
                    st.error(err)
            else:
                with st.spinner("Routing your request..."):
                    patient_id = ensure_patient(conn, name, phone, dob.isoformat())
                    result = triage(reason)

                st.session_state.patient_id = patient_id
                st.session_state.patient_name = name.strip()
                st.session_state.patient_phone = phone.strip()
                st.session_state.patient_dob = dob.isoformat()
                st.session_state.intake_reason = reason.strip()
                st.session_state.triage = result.model_dump()
                st.session_state.intake_chat = [{"role": "user", "text": reason.strip()}]
                st.session_state.intake_answers = []
                st.session_state.intake_stage = "questions"
                st.toast("Triage ready. Answer the follow-up questions.")
                st.rerun

    elif stage == "questions":
        tri = st.session_state.get("triage")
        if not tri:
            reset_intake()
            st.rerun
            return

        chat = st.session_state.setdefault("intake_chat", [])
        answers = st.session_state.setdefault("intake_answers", [])
        questions = tri.get("follow_up_questions", [])

        st.subheader("Chat-style follow-up")
        st.info(tri.get("summary", ""))

        for msg in chat:
            with st.chat_message(msg["role"]):
                st.markdown(msg["text"])

        if not questions or len(answers) >= len(questions):
            st.session_state.intake_stage = "slots"
            st.rerun
            return

        current_q = questions[len(answers)]
        with st.chat_message("assistant"):
            st.markdown(f"**Follow-up {len(answers) + 1} of {len(questions)}**\n\n{current_q}")

        answer = st.chat_input("Type your answer and press Enter")
        if answer and answer.strip():
            chat.append({"role": "user", "text": answer.strip()})
            answers.append(answer.strip())
            st.session_state.intake_chat = chat
            st.session_state.intake_answers = answers
            st.rerun

    elif stage == "slots":
        tri = st.session_state.get("triage")
        if not tri:
            reset_intake()
            st.rerun
            return

        st.subheader("Suggested department and available slots")

        c1, c2, c3 = st.columns(3)
        c1.metric("Department", tri["department"])
        c2.metric("Urgency", tri["urgency"].title())
        c3.metric("Status", "Ready to book")

        st.info(tri["summary"])

        with st.expander("Review intake answers"):
            questions = tri.get("follow_up_questions", [])
            answers = st.session_state.get("intake_answers", [])
            for q, a in zip(questions, answers):
                st.markdown(f"**Q:** {q}\n\n**A:** {a}")

        slots = available_slots(conn, tri["department"], days=14, limit=6)

        if not slots:
            st.warning("No available slots in the next two weeks. Please call the clinic.")
            return

        cols = st.columns(3)
        for idx, (start, end) in enumerate(slots):
            with cols[idx % 3]:
                st.markdown(
                    f"""
                    <div class="cf-slot">
                      <strong>{escape(start.strftime('%a %d %b'))}</strong><br>
                      {escape(start.strftime('%H:%M'))}–{escape(end.strftime('%H:%M'))}<br>
                      <small>{escape(tri['department'])}</small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if st.button("Book this slot", key=f"book_{idx}", type="primary"):
                    ok, msg = book_slot(
                        conn,
                        st.session_state.patient_id,
                        tri["department"],
                        start.strftime("%Y-%m-%d %H:%M:%S"),
                        end.strftime("%Y-%m-%d %H:%M:%S"),
                        tri["urgency"],
                        st.session_state.intake_reason,
                    )

                    if ok:
                        st.session_state.booking_confirmation = {
                            "appointment_id": msg,
                            "patient_name": st.session_state.patient_name,
                            "phone": st.session_state.patient_phone,
                            "department": tri["department"],
                            "date": start.strftime("%A, %d %B %Y"),
                            "time": f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}",
                            "urgency": tri["urgency"],
                            "reason": st.session_state.intake_reason,
                            "summary": tri["summary"],
                        }
                        st.toast("Appointment booked successfully.")
                        st.rerun
                    else:
                        st.error(str(msg))


def render_schedule(conn: sqlite3.Connection) -> None:
    st.header("2. Weekly schedule")

    default_week_start = date.today() - timedelta(days=date.today().weekday())
    selected_date = st.date_input("Week of", value=default_week_start)

    week_start = datetime.combine(selected_date, time(0, 0))
    week_end = week_start + timedelta(days=7)

    df = appointments_between(conn, week_start, week_end)

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        dept_filter = st.multiselect("Departments", DEPARTMENTS, default=DEPARTMENTS)
    with filter_col2:
        status_filter = st.multiselect(
            "Statuses",
            ["scheduled", "completed", "cancelled", "no_show"],
            default=["scheduled", "completed", "no_show", "cancelled"],
        )

    df = df[df["department"].isin(dept_filter) & df["status"].isin(status_filter)].copy()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total appointments", len(df))
    m2.metric("Scheduled", int((df["status"] == "scheduled").sum()) if not df.empty else 0)
    m3.metric("Urgent", int((df["urgency"] == "urgent").sum()) if not df.empty else 0)
    m4.metric("Cancelled", int((df["status"] == "cancelled").sum()) if not df.empty else 0)

    if df.empty:
        st.info("No appointments match the current filters.")
        return

    df["slot_dt"] = pd.to_datetime(df["slot_start"])

    st.divider()
    days = [week_start + timedelta(days=i) for i in range(7)]
    cols = st.columns(7, gap="small")

    for col, day in zip(cols, days):
        col.markdown(
            f"#### {escape(day.strftime('%a'))}<br>{escape(day.strftime('%d %b'))}",
            unsafe_allow_html=True,
        )

        for hour in range(9, 17):
            slot = day + timedelta(hours=hour)
            events = df[df["slot_dt"] == slot]

            if events.empty:
                col.markdown(
                    f"<div class='cf-empty'>{escape(slot.strftime('%H:%M'))}</div>",
                    unsafe_allow_html=True,
                )
            else:
                for _, event in events.iterrows():
                    if event["status"] == "scheduled":
                        color = urgency_color(event["urgency"])
                    else:
                        color = status_color(event["status"])

                    col.markdown(
                        f"""
                        <div class='cf-event' style='background:{color}'>
                          <strong>{escape(str(event['name']))}</strong><br>
                          {escape(str(event['department']))}<br>
                          <small>{escape(str(event['urgency']))} · {escape(str(event['status']))}</small>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )


def render_dashboard(conn: sqlite3.Connection) -> None:
    st.header("3. Staff dashboard")

    today = date.today()
    today_df = list_by_day(conn, today)

    urgency_order = {"urgent": 0, "soon": 1, "routine": 2}
    if not today_df.empty:
        today_df["urgency_rank"] = today_df["urgency"].map(urgency_order).fillna(3)
        today_df = today_df.sort_values(["urgency_rank", "slot_start"]).drop(columns=["urgency_rank"])

    st.subheader("Today's queue")
    if today_df.empty:
        st.info("No appointments recorded for today.")
    else:
        st.dataframe(
            today_df[["id", "slot_start", "name", "department", "urgency", "status", "reason"]],
            use_container_width=True,
            hide_index=True,
        )

        with st.form("appointment_action"):
            aid = st.selectbox("Select appointment ID", today_df["id"].tolist())
            c1, c2, c3 = st.columns(3)
            complete = c1.form_submit_button("Mark completed")
            cancel = c2.form_submit_button("Cancel")
            no_show = c3.form_submit_button("No-show")

        if complete:
            if set_status(conn, int(aid), "completed"):
                st.success("Appointment marked completed.")
                st.rerun
            else:
                st.error("Could not update appointment.")

        if cancel:
            if cancel_appointment(conn, int(aid)):
                st.success("Appointment cancelled.")
                st.rerun
            else:
                st.error("Could not cancel appointment.")

        if no_show:
            if set_status(conn, int(aid), "no_show"):
                st.success("Appointment marked no-show.")
                st.rerun
            else:
                st.error("Could not update appointment.")

    st.divider()
    st.subheader("KPIs and charts")

    week_start_date = today - timedelta(days=today.weekday())
    week_start = datetime.combine(week_start_date, time(0, 0))
    week_end = week_start + timedelta(days=7)
    week_df = appointments_between(conn, week_start, week_end)

    if week_df.empty:
        st.info("No appointment data for the current week.")
        return

    completed_count = int((week_df["status"] == "completed").sum())
    no_show_count = int((week_df["status"] == "no_show").sum())
    denominator = completed_count + no_show_count
    no_show_rate = (no_show_count / denominator * 100) if denominator else 0.0

    wait_df = week_df[week_df["status"].isin(["completed", "no_show"])].copy()
    if not wait_df.empty:
        wait_df["simulated_wait"] = (wait_df["id"] % 35) + 5
        avg_wait = float(wait_df["simulated_wait"].mean())
    else:
        avg_wait = 0.0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Weekly bookings", len(week_df))
    k2.metric("No-show rate", f"{no_show_rate:.1f}%")
    k3.metric("Avg simulated wait", f"{avg_wait:.1f} min")
    k4.metric("Urgent cases", int((week_df["urgency"] == "urgent").sum()))

    dept_counts = week_df["department"].value_counts().reset_index()
    dept_counts.columns = ["department", "bookings"]

    urgency_counts = week_df["urgency"].value_counts().reset_index()
    urgency_counts.columns = ["urgency", "count"]

    week_df["day"] = pd.to_datetime(week_df["slot_start"]).dt.date
    trend = week_df.groupby("day").size().reset_index(name="bookings")

    c1, c2 = st.columns(2)
    with c1:
        if HAS_PLOTLY:
            fig = px.bar(dept_counts, x="department", y="bookings", title="Bookings per department")
            fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown("**Bookings per department**")
            st.bar_chart(dept_counts.set_index("department")["bookings"])

    with c2:
        if HAS_PLOTLY:
            fig = px.pie(urgency_counts, names="urgency", values="count", title="Urgency mix")
            fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown("**Urgency mix**")
            st.bar_chart(urgency_counts.set_index("urgency")["count"])

    if HAS_PLOTLY:
        fig = px.line(trend, x="day", y="bookings", title="Daily bookings this week")
        fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("**Daily bookings this week**")
        st.line_chart(trend.set_index("day")["bookings"])

    st.divider()
    st.subheader("CSV export")

    csv = week_df.drop(columns=["day"], errors="ignore").to_csv(index=False)
    st.download_button(
        "Download weekly appointments CSV",
        data=csv,
        file_name=f"clinicflow_week_{week_start_date.isoformat()}.csv",
        mime="text/csv",
    )

    st.divider()
    st.subheader("Patient reminder generator")

    upcoming_df = appointments_between(conn, datetime.now(), datetime.now() + timedelta(days=7))
    upcoming_df = upcoming_df[upcoming_df["status"] == "scheduled"].copy()

    if upcoming_df.empty and not today_df.empty:
        upcoming_df = today_df[today_df["status"] == "scheduled"].copy()

    if upcoming_df.empty:
        st.info("No scheduled appointments available for reminders.")
        return

    options = [
        (int(row["id"]), f"#{int(row['id'])} · {row['name']} · {row['department']} · {row['slot_start']}")
        for _, row in upcoming_df.iterrows()
    ]

    selected = st.selectbox(
        "Select scheduled appointment",
        options,
        format_func=lambda item: item[1],
    )

    selected_id = selected[0]
    row = upcoming_df[upcoming_df["id"] == selected_id].iloc[0]

    if st.button("Generate reminder message"):
        first_name = str(row["name"]).split()[0]
        with st.spinner("Generating reminder..."):
            text = generate_reminder(
                first_name=first_name,
                department=str(row["department"]),
                slot_start=str(row["slot_start"]),
                urgency=str(row["urgency"]),
            )
        st.session_state.reminder_text = text

    if st.session_state.get("reminder_text"):
        st.text_area("Reminder message", st.session_state.reminder_text, height=220)
        st.download_button(
            "Download reminder txt",
            data=st.session_state.reminder_text,
            file_name=f"clinicflow_reminder_{selected_id}.txt",
            mime="text/plain",
        )


# ----------------------------
# Router
# ----------------------------

def main() -> None:
    inject_css()
    conn = get_conn()

    st.sidebar.title("🏥 ClinicFlow")
    st.sidebar.caption("Appointment and intake demo")

    role = st.sidebar.radio("Role", ["Patient", "Staff"], horizontal=True)

    if role == "Staff":
        if not st.session_state.get("staff_auth"):
            st.sidebar.markdown("#### Staff access")
            pwd = st.sidebar.text_input("Staff password", type="password")
            if st.sidebar.button("Unlock"):
                if pwd == STAFF_PASSWORD:
                    st.session_state.staff_auth = True
                    st.sidebar.success("Unlocked")
                    st.rerun
                else:
                    st.sidebar.error("Incorrect password")

            st.sidebar.info("Demo password: clinic-demo")
            st.title("Staff login required")
            st.write("Enter the staff password in the sidebar to open the dashboard.")
            st.stop()
        else:
            if st.sidebar.button("Lock staff area"):
                st.session_state.staff_auth = False
                st.rerun()

            pages = ["Staff Dashboard", "Schedule", "Intake"]
    else:
        pages = ["Intake", "Schedule"]

    page = st.sidebar.radio("Navigate", pages)

    st.sidebar.divider()
    st.sidebar.markdown(
        f"""
        **Demo data**
        - 3 departments
        - 40 seeded appointments
        - Patient intake chat
        - Weekly calendar
        - Staff dashboard
        """
    )

    if page == "Intake":
        render_intake(conn)
    elif page == "Schedule":
        render_schedule(conn)
    else:
        render_dashboard(conn)


if __name__ == "__main__":
    main()