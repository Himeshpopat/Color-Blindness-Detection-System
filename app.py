from datetime import datetime, timedelta
import io
import json
import random
import sqlite3
import os
import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import send_file, session, redirect, url_for, request, flash


from werkzeug.security import generate_password_hash, check_password_hash

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file,
    jsonify,
)


app = Flask(__name__)
app.secret_key = "change-this-secret-key"  # required for session usage

# ---------------------------------------------------------------------------
# Email / OTP configuration
# In Gmail → Settings → Security → 2-Step Verification → App Passwords,
# generate an app password for "Mail" and paste it below.
# ---------------------------------------------------------------------------
OTP_SENDER_EMAIL    = "societysynced@gmail.com"
OTP_SENDER_PASSWORD = "tvqtykupebrbcfon"   # ← paste app password here
OTP_EXPIRY_MINUTES  = 10

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_results.db")


def init_db():
    """Initialize SQLite database and create tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_type TEXT NOT NULL,
            score INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            diagnosis TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            answers_json TEXT,
            report_data TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            age INTEGER,
            gender TEXT,
            country TEXT,
            occupation TEXT,
            glasses TEXT,
            vision_issues TEXT,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Safely add user_id column to test_results if it doesn't exist
    c.execute("PRAGMA table_info(test_results)")
    columns = [col[1] for col in c.fetchall()]
    if "user_id" not in columns:
        c.execute("ALTER TABLE test_results ADD COLUMN user_id INTEGER")

    conn.commit()
    conn.close()


def save_test_result(test_type: str, score: int, total: int, diagnosis: str,
                     answers_json: str = None, report_data: dict = None) -> int:
    """Save a test result to the database. Returns the new row id."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_str = json.dumps(report_data) if report_data else None
    user_id = session.get("user_id")

    c.execute(
        "INSERT INTO test_results "
        "(test_type, score, total_questions, diagnosis, timestamp, answers_json, report_data, user_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (test_type, score, total, diagnosis, ts, answers_json, report_str, user_id),
    )
    row_id = c.lastrowid
    
    # --- NEW: DATA ADOPTION LOGIC (Part 1) ---
    if not user_id:
        # Save this ID to the session so the user can claim it when they log in/sign up
        session["guest_test_id"] = row_id
    # -----------------------------------------
    
    conn.commit()
    conn.close()
    return row_id


def get_all_test_results(user_id):
    """Fetch all test results from the database."""
    # If there is no user_id (user not logged in), return an empty list immediately
    if user_id is None:
        return []
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if user_id:
        c.execute(
            "SELECT id, test_type, score, total_questions, diagnosis, timestamp, answers_json, report_data "
            "FROM test_results WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        )
    else:
        c.execute(
            "SELECT id, test_type, score, total_questions, diagnosis, timestamp, answers_json, report_data "
            "FROM test_results ORDER BY id DESC"
        )
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_test_result_by_id(result_id: int) -> dict | None:
    """Fetch a single test result by id."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT id, test_type, score, total_questions, diagnosis, timestamp, answers_json, report_data "
        "FROM test_results WHERE id = ?",
        (result_id,),
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Ishihara plate definitions
#
# Plate types:
#   "vanishing"      – only normal vision sees the digit; CB sees nothing ("")
#   "transformation" – normal and CB see different digits
#   "hidden"         – only CB sees the digit; normal vision sees nothing ("")
#   "diagnostic"     – distinguishes Protan from Deutan (different CB answers)
#
# Sources: standard 38-plate Ishihara series (1917, revised editions).
# Images are assumed to be named test1.png … test10.png in static/images/.
# ---------------------------------------------------------------------------

ISHIHARA_PLATES = [
    # Plate 1 — orange digits on grey background.
    # Normal: 12 | Color-blind: cannot see (vanishing).
    {
        "id": 1,
        "image": "plate1.png",
        "type": "vanishing",
        "normal_answer": "12",
        "protan_answer": "",
        "deutan_answer": "",
        "description": "12",
    },
    # Plate 2 — red/pink digits on yellow-green background.
    # Normal: 8 | Color-blind: 3
    {
        "id": 2,
        "image": "plate2.png",
        "type": "transformation",
        "normal_answer": "8",
        "protan_answer": "3",
        "deutan_answer": "3",
        "description": "8",
    },
    # Plate 3 — red digits on yellow-green background.
    # Normal: 29 | Color-blind: 70
    {
        "id": 3,
        "image": "plate3.png",
        "type": "transformation",
        "normal_answer": "29",
        "protan_answer": "70",
        "deutan_answer": "70",
        "description": "29",
    },
    # Plate 4 — green on orange/red. Normal: 5.
    # Color-blind see a different digit: 2.
    {
        "id": 4,
        "image": "plate4.png",
        "type": "vanishing",
        "normal_answer": "5",
        "protan_answer": "2",
        "deutan_answer": "2",
        "description": "5",
    },
    # Plate 5 — green on red/orange.
    # Normal: 3 | Color-blind: 5
    {
        "id": 5,
        "image": "plate5.png",
        "type": "transformation",
        "normal_answer": "3",
        "protan_answer": "5",
        "deutan_answer": "5",
        "description": "3",
    },
    # Plate 6 — green/yellow on red-orange.
    # Normal: 15 | Color-blind: 17
    {
        "id": 6,
        "image": "plate6.png",
        "type": "transformation",
        "normal_answer": "15",
        "protan_answer": "17",
        "deutan_answer": "17",
        "description": "15",
    },
    # Plate 7 — green on orange/red.
    # Normal: 74 | Color-blind: 21
    {
        "id": 7,
        "image": "plate7.png",
        "type": "transformation",
        "normal_answer": "74",
        "protan_answer": "21",
        "deutan_answer": "21",
        "description": "74",
    },
    # Plate 8 — orange digits on yellow-green/grey background.
    # Normal: 6 | Color-blind: nothing (vanishing).
    {
        "id": 8,
        "image": "plate8.png",
        "type": "vanishing",
        "normal_answer": "6",
        "protan_answer": "",
        "deutan_answer": "",
        "description": "6",
    },
    # Plate 9 — orange digits on olive/grey background.
    # Normal: 45 | Color-blind: nothing (vanishing).
    {
        "id": 9,
        "image": "plate9.png",
        "type": "vanishing",
        "normal_answer": "45",
        "protan_answer": "",
        "deutan_answer": "",
        "description": "45",
    },
    # Plate 10 — mixed red-green field.
    # Normal: 5 | Color-blind: nothing (vanishing).
    {
        "id": 10,
        "image": "plate10.png",
        "type": "vanishing",
        "normal_answer": "5",
        "protan_answer": "",
        "deutan_answer": "",
        "description": "5",
    },
    # Plate 11 — green digit on red/yellow background.
    # Normal: 7 | Color-blind: nothing (vanishing).
    {
        "id": 11,
        "image": "plate11.png",
        "type": "vanishing",
        "normal_answer": "7",
        "protan_answer": "",
        "deutan_answer": "",
        "description": "7",
    },
    # Plate 12 — green digits on red/yellow background.
    # Normal: 16 | Color-blind: nothing (vanishing).
    {
        "id": 12,
        "image": "plate12.png",
        "type": "vanishing",
        "normal_answer": "16",
        "protan_answer": "",
        "deutan_answer": "",
        "description": "16",
    },
    # Plate 13 — green digits on red/yellow background.
    # Normal: 73 | Color-blind: nothing (vanishing).
    {
        "id": 13,
        "image": "plate13.png",
        "type": "vanishing",
        "normal_answer": "73",
        "protan_answer": "",
        "deutan_answer": "",
        "description": "73",
    },
    # Plate 14 — diagnostic: red vs purple digits on grey.
    # Normal: 26 | Protan: 6 | Deutan: 2
    {
        "id": 14,
        "image": "plate14.png",
        "type": "diagnostic",
        "normal_answer": "26",
        "protan_answer": "6",
        "deutan_answer": "2",
        "description": "26",
    },
    # Plate 15 — diagnostic: red vs purple digits on grey.
    # Normal: 42 | Protan: 2 | Deutan: 4
    {
        "id": 15,
        "image": "plate15.png",
        "type": "diagnostic",
        "normal_answer": "42",
        "protan_answer": "2",
        "deutan_answer": "4",
        "description": "42",
    },
]


# ---------------------------------------------------------------------------
# Ishihara diagnosis logic
# ---------------------------------------------------------------------------

def _score_plate(plate: dict, user_answer: str) -> dict:
    """
    Evaluate a single plate response and return per-type scoring points.

    Plate types:
        vanishing   – Normal sees the digit; colour-blind see nothing.
        transformation – Normal and colour-blind see different digits.
        hidden      – Only colour-blind see the digit; normal sees nothing.
        diagnostic  – Protan and deutan see different digits; normal sees both.

    Returns a dict:
        normal_point  – 1 if the answer matches normal vision
        protan_point  – 1 if the answer matches a protan response
        deutan_point  – 1 if the answer matches a deutan response
        cb_point      – 1 if the answer matches *any* colour-blind response
        result        – "normal" | "protan" | "deutan" | "colorblind" | "incorrect"
    """
    ua     = user_answer.strip().lower()
    normal = plate["normal_answer"].strip().lower()
    protan = (plate.get("protan_answer") or "").strip().lower()
    deutan = (plate.get("deutan_answer") or "").strip().lower()
    ptype  = plate["type"]

    result = "incorrect"
    normal_point = protan_point = deutan_point = 0

    # Helper: does the user claim to see nothing?
    sees_nothing = ua in ("", "nothing", "none", "0", "x", "-")

    if ptype == "vanishing":
        # Normal vision reads the digit; colour-blind eyes lose it in the bg.
        # Some vanishing plates also have a known CB answer (e.g. plate 4).
        if ua == normal:
            result = "normal"
            normal_point = 1
        elif protan and ua == protan:
            # CB sees a different digit on this plate
            result = "protan"
            protan_point = 1
        elif deutan and deutan != protan and ua == deutan:
            result = "deutan"
            deutan_point = 1
        elif sees_nothing:
            result = "colorblind"   # red-green deficiency confirmed

    elif ptype == "transformation":
        # Normal and colour-blind perceive entirely different digits.
        if ua == normal:
            result = "normal"
            normal_point = 1
        elif protan and ua == protan:
            result = "protan"
            protan_point = 1
        elif deutan and deutan != protan and ua == deutan:
            result = "deutan"
            deutan_point = 1
        elif protan and ua == protan:   # protan == deutan case
            result = "colorblind"

    elif ptype == "hidden":
        # Only colour-blind individuals detect the digit.
        if sees_nothing:
            result = "normal"
            normal_point = 1
        elif protan and ua == protan:
            result = "protan"
            protan_point = 1
        elif deutan and ua == deutan:
            result = "deutan"
            deutan_point = 1

    elif ptype == "diagnostic":
        # Differentiates protan from deutan; both miss what the other sees.
        # Normal vision sees both digits combined (e.g. "26").
        if ua == normal:
            result = "normal"
            normal_point = 1
        elif protan and ua == protan:
            result = "protan"
            protan_point = 1
        elif deutan and ua == deutan:
            result = "deutan"
            deutan_point = 1

    cb_point = 1 if result in ("protan", "deutan", "colorblind") else 0

    return {
        "normal_point": normal_point,
        "protan_point": protan_point,
        "deutan_point": deutan_point,
        "cb_point":     cb_point,
        "result":       result,
    }


def build_ishihara_diagnosis(normal_score: int, protan_score: int,
                            deutan_score: int, total: int,
                            scored_answers: list = None) -> str:
    """
    Produce a clinically-graded diagnosis from aggregated plate scores.

    The Ishihara series primarily screens for RED-GREEN deficiencies
    (Protanopia, Protanomaly, Deuteranopia, Deuteranomaly).  The D15
    test covers blue-yellow (Tritanopia/Tritanomaly) separately.

    Severity thresholds (based on standard 38-plate Ishihara guidelines
    scaled to the number of plates actually shown):

        normal_pct >= 0.90  →  Normal Color Vision
        normal_pct >= 0.70  →  Mild Color Vision Deficiency (borderline)
        normal_pct <  0.70  →  Significant deficiency; classify by type:

            Diagnostic plates give the clearest protan vs deutan split.
            If no diagnostic plates were shown, transformation plates are used.

            protan_score >> deutan_score  →  Protanopia / Protanomaly
            deutan_score >> protan_score  →  Deuteranopia / Deuteranomaly
            protan ≈ deutan               →  Unclassified Red-Green Deficiency

        cb_dominated (many vanishing misses, low normal, low protan/deutan)
            → Possible Red-Green Deficiency (type unclear)

    Note: The Ishihara test cannot detect Tritanopia (blue-yellow); that is
    assessed separately via the D15 test.
    """
    if total <= 0:
        return "Insufficient data to determine result."

    normal_pct = normal_score / total
    cb_score   = (scored_answers and
                    sum(1 for a in scored_answers if a.get("result") == "colorblind")) or 0

    # ── Normal vision ────────────────────────────────────────────────────────
    if normal_pct >= 0.90:
        return "Normal Color Vision"

    # ── Borderline / mild ────────────────────────────────────────────────────
    if normal_pct >= 0.70:
        # Still try to name the sub-type if diagnostic plates gave a clear signal
        if protan_score > 0 and protan_score > deutan_score:
            return "Mild Protanomaly (Weak Red Sensitivity)"
        if deutan_score > 0 and deutan_score > protan_score:
            return "Mild Deuteranomaly (Weak Green Sensitivity)"
        return "Mild Color Vision Deficiency (type unclear)"

    # ── Significant deficiency – classify sub-type ───────────────────────────
    # Weighted ratio to avoid noise from single diagnostic plates.
    protan_dominant = protan_score > deutan_score
    deutan_dominant = deutan_score > protan_score

    # Severity within each type: ratio of CB-type score to total questions.
    protan_pct = protan_score / total
    deutan_pct = deutan_score / total

    if protan_dominant:
        if protan_pct >= 0.20:
            return "Protanopia (Severe Red-Green Deficiency — Red blind)"
        return "Protanomaly (Moderate Red-Green Deficiency — Red weak)"

    if deutan_dominant:
        if deutan_pct >= 0.20:
            return "Deuteranopia (Severe Red-Green Deficiency — Green blind)"
        return "Deuteranomaly (Moderate Red-Green Deficiency — Green weak)"

    # Neither protan nor deutan signals dominate but normal score is low →
    # generic red-green deficiency (common when mostly vanishing plates shown).
    if cb_score > 0 or (normal_pct < 0.50):
        return "Red-Green Color Vision Deficiency (type unclear)"

    return "Possible Color Vision Deficiency (borderline result)"


# ---------------------------------------------------------------------------
# Farnsworth D-15 — cap definitions & scoring
#
# 16 caps evenly spaced around the hue wheel (22.5° apart), starting at
# purple (hue 270°). Hex values must stay identical to D15_CAPS in script.js.
# Correct arrangement order: 0 → 1 → 2 → … → 15.
# ---------------------------------------------------------------------------

D15_CAPS = [
    {"id":  0, "label": "Cap 0",  "hex": "#9351d6"},  # 270° violet-purple   — reference (fixed)
    {"id":  1, "label": "Cap 1",  "hex": "#c44dd4"},  # 293° magenta-purple
    {"id":  2, "label": "Cap 2",  "hex": "#d64daa"},  # 315° hot pink
    {"id":  3, "label": "Cap 3",  "hex": "#d64d72"},  # 338° rose-red
    {"id":  4, "label": "Cap 4",  "hex": "#d64d4d"},  # 0°   pure red
    {"id":  5, "label": "Cap 5",  "hex": "#d6804d"},  # 22°  orange
    {"id":  6, "label": "Cap 6",  "hex": "#d6b94d"},  # 45°  amber-yellow
    {"id":  7, "label": "Cap 7",  "hex": "#b8d64d"},  # 68°  yellow-green
    {"id":  8, "label": "Cap 8",  "hex": "#7ad64d"},  # 90°  lime green
    {"id":  9, "label": "Cap 9",  "hex": "#4dd66b"},  # 112° green
    {"id": 10, "label": "Cap 10", "hex": "#4dd6a6"},  # 135° green-teal
    {"id": 11, "label": "Cap 11", "hex": "#4dd6d6"},  # 158° cyan
    {"id": 12, "label": "Cap 12", "hex": "#4da6d6"},  # 180° sky blue
    {"id": 13, "label": "Cap 13", "hex": "#4d72d6"},  # 202° cobalt blue
    {"id": 14, "label": "Cap 14", "hex": "#6b4dd6"},  # 225° blue-violet
    {"id": 15, "label": "Cap 15", "hex": "#5e4dd6"},  # 248° indigo          — end cap (fixed)
]

# Correct sequence: 0,1,2,…,15
CORRECT_D15_ORDER = list(range(16))

# ---------------------------------------------------------------------------
# Confusion-axis vectors (Vingrys & King-Smith 1988)
#
# Each entry defines a named axis by its two "poles" in cap-id space.
# When a user's connecting lines repeatedly cross the area between two
# specific cap ids, it indicates confusion along that axis.
#
# Protan  axis: roughly caps 1–2  ↔  caps 9–10  (blue-purple ↔ olive-yellow)
# Deutan  axis: roughly caps 3–4  ↔  caps 11–12 (cyan-blue   ↔ orange-red)
# Tritan  axis: roughly caps 5–6  ↔  caps 13–14 (green-teal  ↔ red-pink)
# ---------------------------------------------------------------------------

D15_CONFUSION_AXES = {
    "Protan":  (frozenset({1, 2}),  frozenset({9,  10})),
    "Deutan":  (frozenset({3, 4}),  frozenset({11, 12})),
    "Tritan":  (frozenset({5, 6}),  frozenset({13, 14})),
}


def _step_error(a: int, b: int) -> int:
    """
    Error score for a single connecting step from cap a → cap b.

    The D-15 error score is defined as the absolute difference between
    cap ids minus 1 (adjacent caps score 0, one step away scores 1, etc.).
    Maximum possible error per step = 14 (jumping all the way across).

    Reference: Bowman (1982), Vingrys & King-Smith (1988).
    """
    return max(0, abs(b - a) - 1)


def _count_crossings(user_order: list) -> dict:
    """
    Count how many of the user's connecting lines cross each confusion axis.

    A crossing occurs when a user step (u_a → u_b) spans across the
    midpoint of a named confusion axis (i.e. one pole is on each side
    of the axis boundary in hue space).

    Returns a dict: axis_name → crossing_count.
    """
    crossings = {axis: 0 for axis in D15_CONFUSION_AXES}

    for i in range(len(user_order) - 1):
        a = user_order[i]
        b = user_order[i + 1]
        step_set = frozenset({a, b})

        for axis_name, (pole1, pole2) in D15_CONFUSION_AXES.items():
            # A crossing occurs when one endpoint is near pole1 and the other
            # is near pole2 (or vice versa).  We use a generous neighbourhood
            # of ±2 caps around each pole centre.
            def near(cap_id, pole):
                return any(abs(cap_id - p) <= 2 for p in pole)

            if (near(a, pole1) and near(b, pole2)) or \
                (near(a, pole2) and near(b, pole1)):
                crossings[axis_name] += 1

    return crossings


def score_d15(user_order: list) -> dict:
    """
    Score a Farnsworth D-15 arrangement.

    Parameters
    ----------
    user_order : list of int
        Full 16-cap sequence as submitted by the user, starting with cap 0
        (reference) and ending with cap 15 (end cap).

    Returns
    -------
    dict with keys:
        total_error_score  – sum of step errors (0 = perfect)
        crossings          – total confusion-axis crossing count
        confusion_axis     – dominant axis name or None
        axis_crossings     – per-axis crossing dict
        sequence           – per-step detail list for the result table
        full_order         – user_order (for the polar diagram)
    """
    cap_map = {c["id"]: c for c in D15_CAPS}

    total_error  = 0
    sequence     = []

    for pos, cap_id in enumerate(user_order):
        step_error = 0
        if pos > 0:
            step_error   = _step_error(user_order[pos - 1], cap_id)
            total_error += step_error

        sequence.append({
            "position":   pos,
            "cap_id":     cap_id,
            "hex":        cap_map[cap_id]["hex"],
            "step_error": step_error,
        })

    axis_crossings = _count_crossings(user_order)
    total_crossings = sum(axis_crossings.values())

    # Dominant confusion axis = whichever axis has the most crossings
    dominant_axis = None
    if total_crossings > 0:
        dominant_axis = max(axis_crossings, key=axis_crossings.get)
        if axis_crossings[dominant_axis] == 0:
            dominant_axis = None

    return {
        "total_error_score": total_error,
        "crossings":         total_crossings,
        "confusion_axis":    dominant_axis,
        "axis_crossings":    axis_crossings,
        "sequence":          sequence,
        "full_order":        user_order,
    }


def diagnose_d15(summary: dict) -> str:
    """
    Produce a diagnosis from the D-15 scoring summary.

    Clinical thresholds (Bowman 1982 / Vingrys & King-Smith 1988):
        total_error_score == 0 and crossings == 0  →  Normal Color Vision
        total_error_score <= 4 and crossings == 0  →  Near Normal (minor errors)
        crossings >= 2 on a single axis             →  Significant deficiency
        crossings == 1                              →  Borderline / mild anomaly
        dominant axis                               →  names the CVD type

    The D-15 can detect Protan, Deutan, AND Tritan axes — it is the only
    common clinical test that covers all three red-green and blue-yellow types.
    """
    error  = summary.get("total_error_score", 0)
    cross  = summary.get("crossings", 0)
    axis   = summary.get("confusion_axis")
    ac     = summary.get("axis_crossings", {})

    # ── Normal ──────────────────────────────────────────────────────────────
    if error == 0 and cross == 0:
        return "Normal Color Vision"

    if error <= 4 and cross == 0:
        return "Near Normal Color Vision (minor arrangement errors)"

    # ── Single crossing — borderline ─────────────────────────────────────────
    if cross == 1:
        if axis == "Protan":
            return "Borderline — Possible Mild Protanomaly (Weak Red Sensitivity)"
        if axis == "Deutan":
            return "Borderline — Possible Mild Deuteranomaly (Weak Green Sensitivity)"
        if axis == "Tritan":
            return "Borderline — Possible Mild Tritanomaly (Weak Blue-Yellow Sensitivity)"
        return "Borderline Color Vision — single confusion-axis crossing detected"

    # ── Multiple crossings — significant deficiency ──────────────────────────
    protan_cross = ac.get("Protan", 0)
    deutan_cross = ac.get("Deutan", 0)
    tritan_cross = ac.get("Tritan", 0)

    # Severe = dominant axis has 3+ crossings
    severe_thresh = 3

    if axis == "Protan":
        if protan_cross >= severe_thresh:
            return "Protanopia (Severe Red-Green Deficiency — Red Blind)"
        return "Protanomaly (Moderate Red-Green Deficiency — Red Weak)"

    if axis == "Deutan":
        if deutan_cross >= severe_thresh:
            return "Deuteranopia (Severe Red-Green Deficiency — Green Blind)"
        return "Deuteranomaly (Moderate Red-Green Deficiency — Green Weak)"

    if axis == "Tritan":
        if tritan_cross >= severe_thresh:
            return "Tritanopia (Severe Blue-Yellow Deficiency — Blue Blind)"
        return "Tritanomaly (Moderate Blue-Yellow Deficiency — Blue Weak)"

    # Mixed — errors spread across multiple axes
    if cross >= 4:
        return "General Color Vision Deficiency (multiple confusion axes affected)"

    return "Mild Color Vision Anomaly — axis unclear; clinical testing recommended"

# ---- Mosaic (Digit) test configuration ----

# Each mosaic plate visually encodes a single digit (0–9) using
# a 6x6 grid and two color groups (foreground vs background).

MOSAIC_QUESTIONS = [
    {
        "id": 1,
        "label": "Mosaic Plate 1",
        "description": "Red–green mosaic forming the digit 3.",
        "correct_answer": "3",
        "type": "rg",  # red‑green oriented
    },
    {
        "id": 2,
        "label": "Mosaic Plate 2",
        "description": "Red–green mosaic forming the digit 5.",
        "correct_answer": "5",
        "type": "rg",
    },
    {
        "id": 3,
        "label": "Mosaic Plate 3",
        "description": "Blue–yellow mosaic forming the digit 8.",
        "correct_answer": "8",
        "type": "by",  # blue‑yellow oriented
    },
    {
        "id": 4,
        "label": "Mosaic Plate 4",
        "description": "Red–green mosaic forming the digit 2.",
        "correct_answer": "2",
        "type": "rg",
    },
    {
        "id": 5,
        "label": "Mosaic Plate 5",
        "description": "Blue–yellow mosaic forming the digit 9.",
        "correct_answer": "9",
        "type": "by",
    },
]


def diagnose_mosaic_result(summary: dict) -> str:
    """Return a human readable diagnosis for the mosaic test."""
    total = summary["total"]
    correct = summary["correct"]
    rg_correct = summary["rg_correct"]
    by_correct = summary["by_correct"]

    accuracy = correct / total if total else 0
    rg_accuracy = rg_correct / summary["rg_total"] if summary["rg_total"] else 0
    by_accuracy = by_correct / summary["by_total"] if summary["by_total"] else 0

    if accuracy >= 0.8 and rg_accuracy >= 0.8 and by_accuracy >= 0.8:
        return "Normal Color Vision"
    if rg_accuracy < 0.7 and rg_accuracy <= by_accuracy:
        return "Possible Red-Green Deficiency"
    if by_accuracy < 0.7 and by_accuracy < rg_accuracy:
        return "Possible Blue-Yellow Deficiency"
    return "Borderline or Mild Color Vision Change"

@app.route("/mosaic", methods=["GET"])
def mosaic():
    # 1. Create a copy of the mosaic questions so we don't alter the master list
    shuffled_questions = list(MOSAIC_QUESTIONS)
    
    # 2. Shuffle the copied list randomly
    random.shuffle(shuffled_questions)
    
    # 3. Pass the shuffled list to the template
    return render_template(
        "mosaic.html", 
        questions_json=json.dumps(shuffled_questions),
        total_questions=len(shuffled_questions)
    )
    
@app.route("/submit-mosaic", methods=["POST"])
def submit_mosaic():
    # Retrieve the JSON string generated by the Javascript numpad
    raw_answers = request.form.get("mosaicAnswersJson", "[]")
    try:
        answers_list = json.loads(raw_answers)
    except (json.JSONDecodeError, TypeError):
        answers_list = []

    # Map answers to a dictionary for easy grading {id: "user_answer"}
    user_answers_dict = {ans.get("id"): str(ans.get("user_answer", "")) for ans in answers_list}

    details = []
    correct_count = 0
    rg_correct = 0
    by_correct = 0
    rg_total = sum(1 for q in MOSAIC_QUESTIONS if q["type"] == "rg")
    by_total = sum(1 for q in MOSAIC_QUESTIONS if q["type"] == "by")

    for q in MOSAIC_QUESTIONS:
        user_answer = user_answers_dict.get(q["id"], "")
        is_correct = user_answer == q["correct_answer"]
        
        if is_correct:
            correct_count += 1
            if q["type"] == "rg":
                rg_correct += 1
            else:
                by_correct += 1

        details.append(
            {
                "id": q["id"],
                "label": q["label"],
                "description": q["description"],
                "correct_answer": q["correct_answer"],
                "user_answer": user_answer or "No answer",
                "is_correct": is_correct,
                "type": q["type"],
            }
        )

    summary = {
        "correct": correct_count,
        "total": len(MOSAIC_QUESTIONS),
        "rg_correct": rg_correct,
        "by_correct": by_correct,
        "rg_total": rg_total,
        "by_total": by_total,
    }

    diagnosis = diagnose_mosaic_result(summary)

    report = {
        "test_name": "Mosaic Color Blindness Test",
        "kind": "mosaic",
        "details": details,
        "summary": summary,
        "diagnosis": diagnosis,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    store_report(report)
    save_test_result(
        test_type="mosaic",
        score=correct_count,
        total=len(MOSAIC_QUESTIONS),
        diagnosis=diagnosis,
        answers_json=json.dumps(details),
        report_data=report,
    )
    return redirect(url_for("result"))

# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def store_report(report: dict) -> None:
    """Store the latest report in the session."""
    session["last_report"] = report


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# OTP helpers
# ---------------------------------------------------------------------------

def _send_otp_email(to_email: str, otp_code: str) -> tuple[bool, str]:
    """
    Send a 6-digit OTP via Gmail SMTP (port 587 + STARTTLS).
    Returns (True, "") on success or (False, error_message) on failure.

    Requirements:
      - 2-Step Verification must be ON for societysync@gmail.com
      - OTP_SENDER_PASSWORD must be a Gmail App Password (16 chars, no spaces)
      - "Less secure app access" is NOT needed — App Passwords bypass that
    """
    if OTP_SENDER_PASSWORD == "YOUR_GMAIL_APP_PASSWORD":
        return False, "OTP_SENDER_PASSWORD not configured in app.py."

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Your Color Vision Detector verification code"
        msg["From"]    = OTP_SENDER_EMAIL
        msg["To"]      = to_email

        body_text = (
            f"Your verification code is: {otp_code}\n\n"
            f"It expires in {OTP_EXPIRY_MINUTES} minutes.\n"
            f"If you did not request this, ignore this email."
        )
        body_html = f"""<div style="font-family:sans-serif;max-width:420px;margin:auto;
                padding:30px;background:#1a1a2e;border-radius:16px;color:#eee;">
            <h2 style="color:#ffc83c;margin-bottom:8px;">Color Vision Detector</h2>
            <p style="color:#aaa;margin-bottom:24px;">Your email verification code:</p>
            <div style="font-size:36px;font-weight:700;letter-spacing:10px;text-align:center;
                        background:rgba(255,255,255,0.07);border-radius:12px;padding:18px;color:#fff;">
                {otp_code}
            </div>
            <p style="color:#888;font-size:13px;margin-top:20px;">
                Expires in {OTP_EXPIRY_MINUTES} minutes.
                If you didn't request this, ignore this email.
            </p>
        </div>"""

        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html,  "html"))

        # Port 587 + STARTTLS is the standard Gmail approach
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(OTP_SENDER_EMAIL, OTP_SENDER_PASSWORD)
            server.sendmail(OTP_SENDER_EMAIL, to_email, msg.as_string())

        return True, ""

    except smtplib.SMTPAuthenticationError:
        return False, ("Gmail authentication failed. Make sure you are using a Gmail "
                       "App Password (not your regular password). Go to "
                       "myaccount.google.com → Security → App Passwords to generate one.")
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


@app.route("/send-otp", methods=["POST"])
def send_otp():
    """Generate a 6-digit OTP, store it in session, and email it."""
    data  = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()

    if not email or "@" not in email:
        return jsonify(ok=False, error="Invalid email address.")

    # Check if email is already registered
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email = ?", (email,))
    exists = c.fetchone()
    conn.close()
    if exists:
        return jsonify(ok=False, error="An account with this email already exists.")

    otp  = str(random.randint(100000, 999999))
    expiry = (datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat()

    # Store in session (keyed by email so multiple tabs can't interfere)
    session["otp_data"] = {"email": email, "code": otp, "expiry": expiry}

    ok_flag, err_msg = _send_otp_email(email, otp)
    if ok_flag:
        return jsonify(ok=True)
    return jsonify(ok=False, error=err_msg or "Failed to send email. Please try again.")


@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    """Validate the OTP and return a short-lived token the signup form uses."""
    data  = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    code  = (data.get("otp")   or "").strip()

    otp_data = session.get("otp_data")

    if not otp_data:
        return jsonify(ok=False, error="No verification request found. Please send the code first.")

    if otp_data.get("email") != email:
        return jsonify(ok=False, error="Email mismatch. Please start over.")

    if datetime.now() > datetime.fromisoformat(otp_data["expiry"]):
        session.pop("otp_data", None)
        return jsonify(ok=False, error="Code has expired. Please request a new one.")

    if otp_data["code"] != code:
        return jsonify(ok=False, error="Incorrect code. Please try again.")

    # OTP is valid — issue a single-use token so the signup POST can confirm
    token = secrets.token_hex(32)
    session["otp_verified"] = {"email": email, "token": token}
    session.pop("otp_data", None)
    return jsonify(ok=True, token=token)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name      = request.form.get("name",  "").strip()
        username = request.form.get("username", "").strip().lower()
        email     = request.form.get("email", "").strip().lower()
        password  = request.form.get("password",  "")
        password2 = request.form.get("password2", "")
        age       = request.form.get("age")
        gender    = request.form.get("gender")
        token     = request.form.get("otp_token", "")

        # Basic validation
        if not name or not email or not password:
            return render_template("signup.html", error="Name, email and password are required.")

        if len(password) < 8:
            return render_template("signup.html", error="Password must be at least 8 characters.")

        if password != password2:
            return render_template("signup.html", error="Passwords do not match.")

        # Verify OTP token
        verified = session.get("otp_verified")
        if not verified or verified.get("email") != email or verified.get("token") != token:
            return render_template("signup.html", error="Email not verified. Please complete OTP verification.")

        hashed = generate_password_hash(password)

        init_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO users (name, username, email, password, age, gender) VALUES (?, ?, ?, ?, ?, ?)",
                (name, username, email, hashed, age or None, gender or None),
            )
            conn.commit()
            session.pop("otp_verified", None)
            return redirect(url_for("login"))
        except sqlite3.IntegrityError as e:
            if "username" in str(e):
                return render_template("signup.html", error="Username already taken.")
            return render_template("signup.html", error="An account with this email already exists.")
        finally:
            conn.close()

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identity = request.form.get("login_identity", "").strip().lower()
        password = request.form.get("password", "")

        init_db()
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ? OR username =?", (identity, identity))
        user_row = c.fetchone()
        
        if user_row and check_password_hash(user_row["password"], password):
            session["user_id"]   = user_row["id"]
            session["user_name"] = user_row["username"]
            
            # --- NEW: DATA ADOPTION LOGIC ---
            if "guest_test_id" in session:
                guest_test_id = session.pop("guest_test_id")
                # Update the orphaned test to belong to this newly logged-in user
                c.execute("UPDATE test_results SET user_id = ? WHERE id = ?", (user_row["id"], guest_test_id))
                conn.commit()
            # --------------------------------
            
            conn.close() # Close connection AFTER adoption

            # --- NEW PDF AUTO-DOWNLOAD LOGIC ---
            if "pending_download" in session:
                session["auto_download"] = session.pop("pending_download")
                return redirect(url_for("dashboard"))
            # -----------------------------------
            
            return redirect(url_for("dashboard"))
            
        conn.close()
        return render_template("login.html", error="Invalid email or password.")
        
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id",   None)
    session.pop("user_name", None)
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Forgot Password Routes
# ---------------------------------------------------------------------------

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        token = request.form.get("reset_token", "")

        if not email or not password:
            return render_template("forgot_password.html", error="Missing fields.")
        if len(password) < 8:
            return render_template("forgot_password.html", error="Password must be at least 8 characters.")
        if password != password2:
            return render_template("forgot_password.html", error="Passwords do not match.")
        
        # Verify the security token to prevent unauthorized password changes
        verified = session.get("reset_verified")
        if not verified or verified.get("email") != email or verified.get("token") != token:
            return render_template("forgot_password.html", error="Session expired or invalid token. Please try again.")

        # Hash the new password and update the database
        hashed = generate_password_hash(password)
        init_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET password = ? WHERE email = ?", (hashed, email))
        conn.commit()
        conn.close()
        
        # Clean up session and redirect to login
        session.pop("reset_verified", None)
        flash("Password updated successfully! Please login with your new password.", "success")
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/send-reset-otp", methods=["POST"])
def send_reset_otp():
    """Send an OTP only if the email exists in the database."""
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()

    if not email or "@" not in email:
        return jsonify(ok=False, error="Invalid email address.")

    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email = ?", (email,))
    exists = c.fetchone()
    conn.close()

    if not exists:
        return jsonify(ok=False, error="No account found with this email address.")

    otp = str(random.randint(100000, 999999))
    expiry = (datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat()
    session["reset_otp_data"] = {"email": email, "code": otp, "expiry": expiry}

    ok_flag, err_msg = _send_otp_email(email, otp)
    if ok_flag:
        return jsonify(ok=True)
    return jsonify(ok=False, error=err_msg or "Failed to send email.")


@app.route("/verify-reset-otp", methods=["POST"])
def verify_reset_otp():
    """Validate the reset OTP."""
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    code = (data.get("otp") or "").strip()

    otp_data = session.get("reset_otp_data")

    if not otp_data:
        return jsonify(ok=False, error="No request found. Send code first.")
    if otp_data.get("email") != email:
        return jsonify(ok=False, error="Email mismatch.")
    if datetime.now() > datetime.fromisoformat(otp_data["expiry"]):
        session.pop("reset_otp_data", None)
        return jsonify(ok=False, error="Code expired. Please request a new one.")
    if otp_data["code"] != code:
        return jsonify(ok=False, error="Incorrect code.")

    # Issue a secure token for the password reset form submission
    token = secrets.token_hex(32)
    session["reset_verified"] = {"email": email, "token": token}
    session.pop("reset_otp_data", None)
    return jsonify(ok=True, token=token)


# ---------------------------------------------------------------------------
# Main pages
# ---------------------------------------------------------------------------

@app.route("/")

def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    user_history = []
    global_stats = None

    # 1. Define auto_download right here so it ALWAYS exists
    auto_download = session.pop("auto_download", None)

    if user_id:
        # Fetch logged-in user's personal history
        c.execute(
            "SELECT id, test_type, score, total_questions, diagnosis, timestamp "
            "FROM test_results WHERE user_id = ? ORDER BY id DESC LIMIT 5",
            (user_id,),
        )
        user_history = [dict(row) for row in c.fetchall()]
    else:
        # Fetch global statistics for guest users
        c.execute("SELECT COUNT(*) FROM test_results")
        total_tests = c.fetchone()[0]
        
        c.execute("SELECT diagnosis, COUNT(*) as count FROM test_results GROUP BY diagnosis")
        stats_rows = c.fetchall()
        
        # Dictionary to hold merged counts (fixes the chart duplicates)
        merged_stats = {}
        for row in stats_rows:
            raw_diag = row['diagnosis'] if row['diagnosis'] else "Normal Color Vision"
            clean_diag = raw_diag.replace("blind", "Blind").replace("weak", "Weak").strip()
            if clean_diag in merged_stats:
                merged_stats[clean_diag] += row['count']
            else:
                merged_stats[clean_diag] = row['count']
                
        global_stats = {
            "total": total_tests,
            "labels": list(merged_stats.keys()),
            "data": list(merged_stats.values())
        }
    
    conn.close()
    
    # 2. Safely pass it to the template
    return render_template("dashboard.html", 
                           user_history=user_history, 
                           global_stats=global_stats,
                           auto_download=auto_download)

@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/simulation")
def simulation():
    return render_template("simulation.html")


@app.route("/reports")
def reports():
    user_id = session.get("user_id")
    
    # If no one is logged in, 'tests' will be an empty list []
    tests = get_all_test_results(user_id)
    
    # If user is a guest (not logged in), we can force counts to 0
    if not user_id:
        return render_template(
            "reports.html",
            tests=[],
            total_count=0,
            ishihara_count=0,
            d15_count=0,
            mosaic_count=0,
        )

    # Standard logic for logged-in users...
    ishihara_count = sum(1 for t in tests if t.get("test_type") == "ishihara")
    d15_count   = sum(1 for t in tests if t.get("test_type") == "d15")
    mosaic_count = sum(1 for t in tests if t.get("test_type") == "mosaic")
    tests_safe = [
        {
            "id":              t["id"],
            "test_type":       t["test_type"],
            "score":           t["score"],
            "total_questions": t["total_questions"],
            "diagnosis":       t["diagnosis"],
            "timestamp":       t["timestamp"],
        }
        for t in tests
    ]
    
    return render_template(
        "reports.html",
        tests=tests_safe,
        total_count=len(tests_safe),
        ishihara_count=ishihara_count,
        d15_count=d15_count,
        mosaic_count=mosaic_count,
    )


# ---------------------------------------------------------------------------
# Ishihara test
# ---------------------------------------------------------------------------

@app.route("/test")
def test():
    """
    Select 10 random plates from the full 15-plate bank on every visit.

    Selection strategy (ensures diagnostic quality):
        1. Always include BOTH diagnostic plates (ids 14 & 15).
        2. Always include at least 2 transformation plates for protan/deutan evidence.
        3. Fill remaining slots randomly from vanishing + leftover transformation.
        4. Shuffle the final 10 before sending so question order varies each run.
    """
    TARGET = 10

    diagnostic_plates    = [p for p in ISHIHARA_PLATES if p["type"] == "diagnostic"]
    transformation_plates = [p for p in ISHIHARA_PLATES if p["type"] == "transformation"]
    vanishing_plates     = [p for p in ISHIHARA_PLATES if p["type"] == "vanishing"]

    # Fixed: all diagnostic plates (currently 2)
    selected = list(diagnostic_plates)

    # Guarantee at least 2 transformation plates
    min_transform = 2
    transform_pick = random.sample(transformation_plates,
                                    min(min_transform, len(transformation_plates)))
    selected.extend(transform_pick)

    # Fill remaining slots from unused transformation + vanishing plates
    remaining_pool = (
        [p for p in transformation_plates if p not in transform_pick] + vanishing_plates
    )
    remaining_needed = TARGET - len(selected)
    if remaining_needed > 0:
        selected.extend(random.sample(remaining_pool,
                                        min(remaining_needed, len(remaining_pool))))

    random.shuffle(selected)

    return render_template(
        "test.html",
        plates=selected,
        plates_json=json.dumps(selected),
        total_questions=len(selected),
    )


@app.route("/ishihara-submit", methods=["POST"])
def ishihara_submit():
    """
    Receive per-question answers from the frontend, score each plate
    server-side using _score_plate(), then build a full diagnosis.
    """
    # The frontend now sends answersJson as the primary source of truth.
    # normalScore / protanScore / deutanScore are kept for backward compat.
    answers_list = []
    try:
        raw = request.form.get("answersJson", "[]")
        answers_list = json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        pass

    # Build a quick lookup: plate_id → plate definition
    plate_map = {p["id"]: p for p in ISHIHARA_PLATES}

    normal_score = protan_score = deutan_score = 0
    scored_answers = []

    for entry in answers_list:
        plate_id    = entry.get("plateId")
        user_answer = str(entry.get("userAnswer", "")).strip()
        plate       = plate_map.get(plate_id)

        if plate is None:
            # Plate id not found — skip
            scored_answers.append({**entry, "result": "unknown",
                                    "correctAnswer": "?"})
            continue

        pts = _score_plate(plate, user_answer)
        normal_score += pts["normal_point"]
        protan_score += pts["protan_point"]
        deutan_score += pts["deutan_point"]

        scored_answers.append({
            "plateId":      plate_id,
            "question":     plate.get("description", f"Plate {plate_id}"),
            "userAnswer":   user_answer,
            "correctAnswer": plate["normal_answer"] or "(nothing)",
            "result":       pts["result"],
        })

    total_questions = len(scored_answers) or 10

    # Fall back to frontend-tallied scores if no per-answer data arrived
    if not answers_list:
        try:
            normal_score = int(request.form.get("normalScore", "0"))
            protan_score = int(request.form.get("protanScore", "0"))
            deutan_score = int(request.form.get("deutanScore", "0"))
            total_questions = int(request.form.get("totalQuestions", "10"))
        except ValueError:
            pass

    diagnosis  = build_ishihara_diagnosis(
        normal_score, protan_score, deutan_score, total_questions, scored_answers
    )
    percentage = round((normal_score / total_questions) * 100) if total_questions else 0

    report = {
        "test_name": "Ishihara Color Vision Test",
        "kind":      "ishihara",
        "details": {
            "normal_score":     normal_score,
            "protan_score":     protan_score,
            "deutan_score":     deutan_score,
            "total_questions":  total_questions,
            "percentage":       percentage,
            "correct_count":    normal_score,
            "answers":          scored_answers,
        },
        "summary": {
            "correct": normal_score,
            "total":   total_questions,
        },
        "diagnosis": diagnosis,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    store_report(report)
    save_test_result(
        test_type="ishihara",
        score=normal_score,
        total=total_questions,
        diagnosis=diagnosis,
        answers_json=json.dumps(scored_answers),
        report_data=report,
    )
    return redirect(url_for("result"))


# ---------------------------------------------------------------------------
# Farnsworth D-15 test routes
# ---------------------------------------------------------------------------

@app.route("/d15", methods=["GET"])
def d15():
    """Render the Farnsworth D-15 drag-and-drop arrangement test."""
    return render_template("d15.html")


@app.route("/submit-d15", methods=["POST"])
def submit_d15():
    """
    Receive the user's cap arrangement from d15.html, score it using
    the D-15 error-score and confusion-axis crossing algorithm, then
    build a full report and redirect to the result page.
    """
    raw = request.form.get("disc_order", "[]")
    try:
        user_order = json.loads(raw)
        # Validate: must be a list of 16 integers covering ids 0–15
        if not isinstance(user_order, list) or len(user_order) != 16:
            raise ValueError("Invalid order length")
        user_order = [int(x) for x in user_order]
    except (json.JSONDecodeError, ValueError, TypeError):
        # Fallback to correct order if submission is malformed
        user_order = CORRECT_D15_ORDER[:]

    summary   = score_d15(user_order)
    diagnosis = diagnose_d15(summary)

    report = {
        "test_name": "Farnsworth D-15 Color Vision Test",
        "kind":      "d15",
        "details":   summary,          # full_order, sequence, axis_crossings …
        "summary":   summary,          # result.html reads from both keys
        "diagnosis": diagnosis,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    store_report(report)
    save_test_result(
        test_type="d15",
        score=max(0, 100 - summary["total_error_score"]),  # normalised score
        total=100,
        diagnosis=diagnosis,
        answers_json=json.dumps(summary["sequence"]),
        report_data=report,
    )
    return redirect(url_for("result"))


# ---------------------------------------------------------------------------
# Result & report views
# ---------------------------------------------------------------------------

@app.route("/result")
def result():
    report = session.get("last_report")
    if not report:
        return redirect(url_for("index"))
    return render_template("result.html", report=report, from_history=False, report_id=None)


@app.route("/report/<int:report_id>")
def report_detail(report_id):
    """View full report for a specific test result."""
    row = get_test_result_by_id(report_id)
    if not row:
        return redirect(url_for("reports"))

    report_data = None
    if row.get("report_data"):
        try:
            report_data = json.loads(row["report_data"])
        except (json.JSONDecodeError, TypeError):
            pass

    if not report_data:
        kind = row["test_type"]
        report_data = {
            "test_name": f"{row['test_type'].title()} Test",
            "kind":      kind,
            "diagnosis": row["diagnosis"],
            "timestamp": row["timestamp"],
        }

        if kind == "d15":
            # Rebuild summary from answers_json (which stores the sequence list)
            sequence = []
            full_order = list(range(16))  # fallback: correct order
            if row.get("answers_json"):
                try:
                    sequence = json.loads(row["answers_json"])
                    full_order = [item["cap_id"] for item in sequence]
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass

            # Re-score from the stored sequence so all fields exist
            rebuilt_summary = score_d15(full_order)
            report_data["summary"] = rebuilt_summary
            report_data["details"] = rebuilt_summary

        elif kind == "mosaic":
            details_list = []
            if row.get("answers_json"):
                try:
                    details_list = json.loads(row["answers_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            rg_total   = sum(1 for a in details_list if a.get("type") == "rg")
            by_total   = sum(1 for a in details_list if a.get("type") == "by")
            rg_correct = sum(1 for a in details_list if a.get("type") == "rg" and a.get("is_correct"))
            by_correct = sum(1 for a in details_list if a.get("type") == "by" and a.get("is_correct"))
            correct    = sum(1 for a in details_list if a.get("is_correct"))
            total      = len(details_list) or row["total_questions"]
            summary = {
                "correct":    correct,
                "total":      total,
                "rg_correct": rg_correct,
                "rg_total":   rg_total,
                "by_correct": by_correct,
                "by_total":   by_total,
            }
            report_data["summary"] = summary
            report_data["details"] = details_list

        else:
            # Ishihara fallback
            answers = []
            if row.get("answers_json"):
                try:
                    answers = json.loads(row["answers_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            report_data["details"] = {
                "normal_score":    row["score"],
                "total_questions": row["total_questions"],
                "percentage":      round(
                    (row["score"] / row["total_questions"]) * 100
                ) if row["total_questions"] else 0,
                "answers": answers,
            }
            report_data["summary"] = {"correct": row["score"], "total": row["total_questions"]}

    return render_template(
        "result.html", report=report_data, from_history=True, report_id=report_id
    )


# ---------------------------------------------------------------------------
# PDF download routes
# ---------------------------------------------------------------------------

@app.route("/download-ishihara-report")
def download_ishihara_report():
    # 1. Enforce login and remember the requested download URL
    if not session.get("user_id"):
        session["pending_download"] = request.url
        return redirect(url_for("login"))

    report_id = request.args.get("id", type=int)
    if report_id:
        row = get_test_result_by_id(report_id)
        if row and row.get("report_data"):
            try:
                report = json.loads(row["report_data"])
                if report.get("kind") == "ishihara":
                    return _generate_pdf_report(report, "ishihara_report.pdf")
            except (json.JSONDecodeError, TypeError):
                pass
        return redirect(url_for("reports"))
    report = session.get("last_report")
    if report and report.get("kind") == "ishihara":
        return _generate_pdf_report(report, "ishihara_report.pdf")
    return redirect(url_for("index"))


@app.route("/download-report")
def download_report():
    # 1. Enforce login and remember the requested download URL
    if not session.get("user_id"):
        session["pending_download"] = request.url
        return redirect(url_for("login"))

    report_id = request.args.get("id", type=int)
    if report_id:
        row = get_test_result_by_id(report_id)
        if row and row.get("report_data"):
            try:
                report = json.loads(row["report_data"])
                return _generate_pdf_report(report, "color_vision_report.pdf")
            except (json.JSONDecodeError, TypeError):
                pass
        return redirect(url_for("reports"))
    report = session.get("last_report")
    if not report:
        return redirect(url_for("index"))
    return _generate_pdf_report(report, "d15_report.pdf")


@app.route("/download-mosaic-report")
def download_mosaic_report():
    # 1. Enforce login and remember the requested download URL
    if not session.get("user_id"):
        session["pending_download"] = request.url
        return redirect(url_for("login"))

    report_id = request.args.get("id", type=int)
    if report_id:
        row = get_test_result_by_id(report_id)
        if row and row.get("report_data"):
            try:
                report = json.loads(row["report_data"])
                if report.get("kind") == "mosaic":
                    return _generate_pdf_report(report, "mosaic_report.pdf")
            except (json.JSONDecodeError, TypeError):
                pass
        return redirect(url_for("reports"))
    
    report = session.get("last_report")
    if report and report.get("kind") == "mosaic":
        return _generate_pdf_report(report, "mosaic_report.pdf")
    
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def _generate_pdf_report(report: dict, filename: str):
    """Generate a PDF report using reportlab."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=inch * 0.75,
        leftMargin=inch * 0.75,
        topMargin=inch * 0.75,
        bottomMargin=inch * 0.75,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=6,
        textColor=colors.HexColor("#1a1a2e"),
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=12,
        spaceAfter=4,
        textColor=colors.HexColor("#16213e"),
    )

    story = []

    # Title block
    story.append(Paragraph("Color Blindness Detection System", title_style))
    story.append(Paragraph(f"Test: {report.get('test_name', 'Unknown')}", styles["Heading2"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 8))

    # ---- NEW: Patient Information Block ----
    user_id = session.get("user_id")
    if user_id:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT name, username, email, age, gender FROM users WHERE id = ?", (user_id,))
        user_info = c.fetchone()
        conn.close()

        if user_info:
            story.append(Paragraph("Patient Information", heading_style))
            patient_data = [
                ["Name", user_info["name"] or "-"],
                ["Username", user_info["username"] or "-"],
                ["Email", user_info["email"] or "-"],
                ["Age", str(user_info["age"]) if user_info["age"] else "-"],
                ["Gender", user_info["gender"] or "-"],
            ]
            patient_table = Table(patient_data, colWidths=[1.8 * inch, 5 * inch])
            patient_table.setStyle(TableStyle([
                ("BACKGROUND",   (0, 0), (0, -1), colors.HexColor("#e8eaf6")),
                ("FONTNAME",     (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE",     (0, 0), (-1, -1), 11),
                ("ROWBACKGROUNDS", (1, 0), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("TOPPADDING",   (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
                ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ]))
            story.append(patient_table)
            story.append(Spacer(1, 14))
    # ----------------------------------------

    # Summary info table
    story.append(Paragraph("Diagnosis Overview", heading_style))
    diagnosis = report.get("diagnosis", "-")
    timestamp = report.get("timestamp", "-")
    kind      = report.get("kind", "")

    summary_data = [
        ["Diagnosis", diagnosis],
        ["Date / Time", timestamp],
    ]
    summary_table = Table(summary_data, colWidths=[1.8 * inch, 5 * inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (0, -1), colors.HexColor("#e8eaf6")),
        ("FONTNAME",     (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 11),
        ("ROWBACKGROUNDS", (1, 0), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 14))

    # ---- Farnsworth D-15 detail ----
    if kind == "d15":
        summary = report.get("summary", {})
        story.append(Paragraph("Score Summary", heading_style))
        score_data = [
            ["Metric",              "Result"],
            ["Total Error Score",   str(summary.get("total_error_score", 0))],
            ["Confusion Crossings", str(summary.get("crossings", 0))],
            ["Dominant Axis",       summary.get("confusion_axis") or "None"],
        ]
        ax = summary.get("axis_crossings", {})
        for axis_name, cnt in ax.items():
            score_data.append([f"  {axis_name} axis crossings", str(cnt)])

        score_table = Table(score_data, colWidths=[2.5 * inch, 4.3 * inch])
        score_table.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#3949ab")),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 11),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("TOPPADDING",   (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 14))

        story.append(Paragraph("Arrangement Sequence", heading_style))
        seq = summary.get("sequence", [])
        q_data = [["Position", "Cap ID", "Step Error"]]
        for item in seq:
            q_data.append([
                str(item.get("position", "")),
                f"Cap {item.get('cap_id', '')}",
                str(item.get("step_error", 0)),
            ])
        col_w = [1.2 * inch, 2.0 * inch, 1.5 * inch]
        q_table = Table(q_data, colWidths=col_w)
        result_colors = [
            ("TEXTCOLOR", (2, i + 1), (2, i + 1),
             colors.HexColor("#2e7d32") if row[2] == "0" else colors.HexColor("#c62828"))
            for i, row in enumerate(q_data[1:])
        ]
        q_table.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#3949ab")),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
            ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ] + result_colors))
        story.append(q_table)

    # ---- Ishihara detail ----
    elif kind == "ishihara":
        details     = report.get("details", {})
        total_q     = details.get("total_questions", 0)
        correct     = details.get("normal_score", details.get("correct_count", 0))
        percentage  = details.get("percentage", 0)

        story.append(Paragraph("Score Summary", heading_style))
        score_data = [
            ["Metric",          "Result"],
            ["Total Questions",  str(total_q)],
            ["Correct Answers",  str(correct)],
            ["Score",            f"{correct} / {total_q}"],
            ["Accuracy",         f"{percentage}%"],
            ["Protan Matches",   str(details.get("protan_score", 0))],
            ["Deutan Matches",   str(details.get("deutan_score", 0))],
        ]
        score_table = Table(score_data, colWidths=[2.5 * inch, 4.3 * inch])
        score_table.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#3949ab")),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 11),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("TOPPADDING",   (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 14))

        answers = details.get("answers", [])
        if answers:
            story.append(Paragraph("Answer Table", heading_style))
            a_data = [["Question", "Your Answer", "Correct Answer", "Result"]]
            for a in answers:
                user_ans    = str(a.get("userAnswer", ""))
                correct_ans = str(a.get("correctAnswer", ""))
                is_right    = a.get("result", "") == "normal"
                a_data.append([
                    str(a.get("question", "")),
                    user_ans,
                    correct_ans,
                    "Correct" if is_right else "Incorrect",
                ])
            col_w = [1.5 * inch, 1.8 * inch, 1.8 * inch, 1.7 * inch]
            a_table = Table(a_data, colWidths=col_w)
            result_colors = [
                ("TEXTCOLOR", (3, i + 1), (3, i + 1),
                 colors.HexColor("#2e7d32") if row[3] == "Correct" else colors.HexColor("#c62828"))
                for i, row in enumerate(a_data[1:])
            ]
            a_table.setStyle(TableStyle([
                ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#3949ab")),
                ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
                ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",     (0, 0), (-1, -1), 10),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("TOPPADDING",   (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
                ("LEFTPADDING",  (0, 0), (-1, -1), 6),
            ] + result_colors))
            story.append(a_table)
            
    # ---- Mosaic detail ----
    elif kind == "mosaic":
        summary = report.get("summary", {})
        story.append(Paragraph("Score Summary", heading_style))
        
        score_data = [
            ["Metric", "Result"],
            ["Total Questions", str(summary.get('total', 0))],
            ["Correct Answers", str(summary.get('correct', 0))],
            ["Red-Green Correct", f"{summary.get('rg_correct', 0)} / {summary.get('rg_total', 0)}"],
            ["Blue-Yellow Correct", f"{summary.get('by_correct', 0)} / {summary.get('by_total', 0)}"],
        ]
        score_table = Table(score_data, colWidths=[2.5 * inch, 4.3 * inch])
        score_table.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#3949ab")),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 11),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("TOPPADDING",   (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 14))

        details = report.get("details", [])
        if details:
            story.append(Paragraph("Answer Details", heading_style))
            a_data = [["Question", "Expected", "Your Answer", "Result"]]
            for item in details:
                a_data.append([
                    f"Q{item['id']} - {item['label']}",
                    str(item.get("correct_answer", "")),
                    str(item.get("user_answer", "")),
                    "Correct" if item.get("is_correct") else "Incorrect"
                ])
            
            a_table = Table(a_data, colWidths=[2.3 * inch, 1.3 * inch, 1.5 * inch, 1.7 * inch])
            result_colors = [
                ("TEXTCOLOR", (3, i + 1), (3, i + 1),
                 colors.HexColor("#2e7d32") if row[3] == "Correct" else colors.HexColor("#c62828"))
                for i, row in enumerate(a_data[1:])
            ]
            a_table.setStyle(TableStyle([
                ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#3949ab")),
                ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
                ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",     (0, 0), (-1, -1), 10),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("TOPPADDING",   (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
                ("LEFTPADDING",  (0, 0), (-1, -1), 6),
            ] + result_colors))
            story.append(a_table)
            
    doc.build(story)
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

@app.route("/test-email")
def test_email():
    import smtplib
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(OTP_SENDER_EMAIL, OTP_SENDER_PASSWORD)
            return f"<h2 style='color:green'>✓ Login SUCCESS for {OTP_SENDER_EMAIL}</h2>"
    except smtplib.SMTPAuthenticationError as e:
        return f"<h2 style='color:red'>✗ Auth Failed</h2><pre>{e.smtp_code}: {e.smtp_error}</pre>"
    except Exception as e:
        return f"<h2 style='color:red'>✗ Error</h2><pre>{type(e).__name__}: {e}</pre>"

if __name__ == "__main__":
    app.run(debug=True)