from datetime import datetime
import io
import json
import sqlite3
import os

from werkzeug.security import generate_password_hash, check_password_hash

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file,
)


app = Flask(__name__)
app.secret_key = "change-this-secret-key"  # required for session usage

# Database path
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
        "INSERT INTO test_results (test_type, score, total_questions, diagnosis, timestamp, answers_json, report_data, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (test_type, score, total, diagnosis, ts, answers_json, report_str, user_id),
    )
    row_id = c.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_all_test_results(user_id=None):
    """Fetch all test results from the database."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if user_id:
        c.execute(
            "SELECT id, test_type, score, total_questions, diagnosis, timestamp, answers_json, report_data FROM test_results WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        )
    else:
        c.execute(
            "SELECT id, test_type, score, total_questions, diagnosis, timestamp, answers_json, report_data FROM test_results ORDER BY id DESC"
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
        "SELECT id, test_type, score, total_questions, diagnosis, timestamp, answers_json, report_data FROM test_results WHERE id = ?",
        (result_id,),
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


# ---- Ishihara configuration ----

ISHIHARA_TOTAL_QUESTIONS = 10


# ---- Mosaic test configuration ----

# Each mosaic plate visually encodes a single digit (0-9) using
# a 6x6 grid and two color groups (foreground vs background).

MOSAIC_QUESTIONS = [
    {
        "id": 1,
        "label": "Mosaic Plate 1",
        "description": "Red-green mosaic forming the digit 3.",
        "correct_answer": "3",
        "type": "rg",  # red-green oriented
    },
    {
        "id": 2,
        "label": "Mosaic Plate 2",
        "description": "Red-green mosaic forming the digit 5.",
        "correct_answer": "5",
        "type": "rg",
    },
    {
        "id": 3,
        "label": "Mosaic Plate 3",
        "description": "Blue-yellow mosaic forming the digit 8.",
        "correct_answer": "8",
        "type": "by",  # blue-yellow oriented
    },
    {
        "id": 4,
        "label": "Mosaic Plate 4",
        "description": "Red-green mosaic forming the digit 2.",
        "correct_answer": "2",
        "type": "rg",
    },
    {
        "id": 5,
        "label": "Mosaic Plate 5",
        "description": "Blue-yellow mosaic forming the digit 9.",
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


def build_ishihara_diagnosis(normal_score: int, protan_score: int, deutan_score: int, total: int) -> str:
    """Server-side interpretation of Ishihara scores.
    score >= 8: Normal Color Vision
    score 5-7: Possible Red-Green Deficiency
    score < 5: High probability of Color Vision Deficiency
    """
    if total <= 0:
        return "Insufficient data to determine result."

    if normal_score >= 8:
        return "Normal Color Vision"
    if 5 <= normal_score <= 7:
        return "Possible Red-Green Deficiency"
    return "High probability of Color Vision Deficiency"


def store_report(report: dict) -> None:
    """Store the latest report in the session."""
    session["last_report"] = report


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        age = request.form.get("age")
        gender = request.form.get("gender")
        country = request.form.get("country")
        occupation = request.form.get("occupation")
        glasses = request.form.get("glasses")
        vision_issues = request.form.get("vision_issues")
        phone = request.form.get("phone")

        if not name or not email or not password:
            return render_template("signup.html", error="Name, Email and Password are required.")

        hashed_password = generate_password_hash(password)

        init_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO users (name, email, password, age, gender, country, occupation, glasses, vision_issues, phone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, email, hashed_password, age, gender, country, occupation, glasses, vision_issues, phone))
            conn.commit()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return render_template("signup.html", error="Email already exists.")
        finally:
            conn.close()

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        init_db()
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        user_row = c.fetchone()
        conn.close()

        if user_row and check_password_hash(user_row["password"], password):
            session["user_id"] = user_row["id"]
            session["user_name"] = user_row["name"]
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Invalid email or password.")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    return redirect(url_for("index"))

@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    user_history = []
    
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    if user_id:
        c.execute(
            "SELECT id, test_type, score, total_questions, diagnosis, timestamp, answers_json, report_data FROM test_results WHERE user_id = ? ORDER BY id DESC LIMIT 5",
            (user_id,)
        )
        user_history = [dict(row) for row in c.fetchall()]
    else:
        # If not logged in, show general test results (latest 5)
        c.execute(
            "SELECT id, test_type, score, total_questions, diagnosis, timestamp, answers_json, report_data FROM test_results ORDER BY id DESC LIMIT 5"
        )
        user_history = [dict(row) for row in c.fetchall()]
        
    conn.close()
    
    return render_template("dashboard.html", user_history=user_history)


@app.route("/test")
def test():
    # Ishihara test page (front-end handled progression, backend handles diagnosis)
    return render_template("test.html", total_questions=ISHIHARA_TOTAL_QUESTIONS)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/reports")
def reports():
    user_id = session.get("user_id")
    tests = get_all_test_results(user_id)
    ishihara_count = sum(1 for t in tests if t.get("test_type") == "ishihara")
    mosaic_count = sum(1 for t in tests if t.get("test_type") == "mosaic")
    return render_template(
        "reports.html",
        tests=tests,
        total_count=len(tests),
        ishihara_count=ishihara_count,
        mosaic_count=mosaic_count,
    )


@app.route("/simulation")
def simulation():
    return render_template("simulation.html")


@app.route("/mosaic", methods=["GET"])
def mosaic():
    return render_template("mosaic.html", questions=MOSAIC_QUESTIONS)


@app.route("/submit-mosaic", methods=["POST"])
def submit_mosaic():
    answers = {}
    for q in MOSAIC_QUESTIONS:
        field_name = f"answer_{q['id']}"
        answers[q["id"]] = request.form.get(field_name, "").strip()

    details = []
    correct_count = 0
    rg_correct = 0
    by_correct = 0
    rg_total = sum(1 for q in MOSAIC_QUESTIONS if q["type"] == "rg")
    by_total = sum(1 for q in MOSAIC_QUESTIONS if q["type"] == "by")

    for q in MOSAIC_QUESTIONS:
        user_answer = answers.get(q["id"], "")
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


@app.route("/ishihara-submit", methods=["POST"])
def ishihara_submit():
    """Receive Ishihara scores from the front-end and evaluate in Python."""
    try:
        normal_score = int(request.form.get("normalScore", "0"))
        protan_score = int(request.form.get("protanScore", "0"))
        deutan_score = int(request.form.get("deutanScore", "0"))
        total_questions = int(request.form.get("totalQuestions", str(ISHIHARA_TOTAL_QUESTIONS)))
    except ValueError:
        normal_score = protan_score = deutan_score = 0
        total_questions = ISHIHARA_TOTAL_QUESTIONS

    # Parse per-question answers from frontend
    answers_list = []
    try:
        answers_json = request.form.get("answersJson", "[]")
        answers_list = json.loads(answers_json) if answers_json else []
    except (json.JSONDecodeError, TypeError):
        pass

    diagnosis = build_ishihara_diagnosis(normal_score, protan_score, deutan_score, total_questions)
    percentage = round((normal_score / total_questions) * 100) if total_questions else 0

    report = {
        "test_name": "Ishihara Color Vision Test",
        "kind": "ishihara",
        "details": {
            "normal_score": normal_score,
            "protan_score": protan_score,
            "deutan_score": deutan_score,
            "total_questions": total_questions,
            "percentage": percentage,
            "correct_count": normal_score,
            "answers": answers_list,
        },
        "summary": {
            "correct": normal_score,
            "total": total_questions,
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
        answers_json=json.dumps(answers_list),
        report_data=report,
    )
    return redirect(url_for("result"))


@app.route("/result")
def result():
    report = session.get("last_report")
    if not report:
        return redirect(url_for("index"))
    return render_template("result.html", report=report)


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
        report_data = {
            "test_name": f"{row['test_type'].title()} Test",
            "kind": row["test_type"],
            "diagnosis": row["diagnosis"],
            "timestamp": row["timestamp"],
            "details": {
                "normal_score": row["score"],
                "total_questions": row["total_questions"],
                "percentage": round((row["score"] / row["total_questions"]) * 100) if row["total_questions"] else 0,
            },
            "summary": {"correct": row["score"], "total": row["total_questions"]},
        }
        if row.get("answers_json"):
            try:
                report_data["details"]["answers"] = json.loads(row["answers_json"])
            except (json.JSONDecodeError, TypeError):
                pass
    return render_template("result.html", report=report_data, from_history=True, report_id=report_id)


@app.route("/download-ishihara-report")
def download_ishihara_report():
    """Download Ishihara test PDF report (uses session or report_id)."""
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
    """Download PDF report (session or by id)."""
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
    return _generate_pdf_report(report, "color_vision_report.pdf")


def _generate_pdf_report(report: dict, filename: str):
    """Generate a PDF report using reportlab (replaces broken fpdf dependency)."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
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

    # Summary info table
    diagnosis = report.get("diagnosis", "-")
    timestamp = report.get("timestamp", "-")
    kind = report.get("kind", "")

    summary_data = [
        ["Diagnosis", diagnosis],
        ["Date / Time", timestamp],
    ]
    summary_table = Table(summary_data, colWidths=[1.8 * inch, 5 * inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8eaf6")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ROWBACKGROUNDS", (1, 0), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 14))

    # Kind-specific sections
    if kind == "mosaic":
        summary = report.get("summary", {})
        story.append(Paragraph("Score Summary", heading_style))
        score_data = [
            ["Metric", "Result"],
            ["Total Correct", f"{summary.get('correct', 0)} / {summary.get('total', 0)}"],
            ["Red-Green Correct", f"{summary.get('rg_correct', 0)} / {summary.get('rg_total', 0)}"],
            ["Blue-Yellow Correct", f"{summary.get('by_correct', 0)} / {summary.get('by_total', 0)}"],
        ]
        score_table = Table(score_data, colWidths=[2.5 * inch, 4.3 * inch])
        score_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3949ab")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 14))

        # Per-question breakdown
        story.append(Paragraph("Question Breakdown", heading_style))
        q_data = [["Q#", "Label", "Expected", "Your Answer", "Result"]]
        for item in report.get("details", []):
            q_data.append([
                str(item.get("id", "")),
                item.get("label", ""),
                item.get("correct_answer", ""),
                item.get("user_answer", ""),
                "Correct" if item.get("is_correct") else "Incorrect",
            ])
        col_w = [0.4 * inch, 1.8 * inch, 1.1 * inch, 1.4 * inch, 1.1 * inch]
        q_table = Table(q_data, colWidths=col_w)
        result_colors = []
        for i, row in enumerate(q_data[1:]):
            color = colors.HexColor("#2e7d32") if row[4] == "Correct" else colors.HexColor("#c62828")
            result_colors.append(("TEXTCOLOR", (4, i + 1), (4, i + 1), color))
        q_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3949ab")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ] + result_colors))
        story.append(q_table)

    elif kind == "ishihara":
        details = report.get("details", {})
        total_q = details.get("total_questions", 0)
        correct = details.get("normal_score", details.get("correct_count", 0))
        percentage = details.get("percentage", 0)

        story.append(Paragraph("Score Summary", heading_style))
        score_data = [
            ["Metric", "Result"],
            ["Total Questions", str(total_q)],
            ["Correct Answers", str(correct)],
            ["Score", f"{correct} / {total_q}"],
            ["Accuracy", f"{percentage}%"],
            ["Protan Matches", str(details.get("protan_score", 0))],
            ["Deutan Matches", str(details.get("deutan_score", 0))],
        ]
        score_table = Table(score_data, colWidths=[2.5 * inch, 4.3 * inch])
        score_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3949ab")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 14))

        answers = details.get("answers", [])
        if answers:
            story.append(Paragraph("Answer Table", heading_style))
            a_data = [["Question", "Your Answer", "Correct Answer", "Result"]]
            for a in answers:
                user_ans = str(a.get("userAnswer", ""))
                correct_ans = str(a.get("correctAnswer", ""))
                is_right = user_ans.strip() == correct_ans.strip()
                a_data.append([
                    str(a.get("question", "")),
                    user_ans,
                    correct_ans,
                    "Correct" if is_right else "Incorrect",
                ])
            col_w = [1.5 * inch, 1.8 * inch, 1.8 * inch, 1.7 * inch]
            a_table = Table(a_data, colWidths=col_w)
            result_colors = []
            for i, row in enumerate(a_data[1:]):
                color = colors.HexColor("#2e7d32") if row[3] == "Correct" else colors.HexColor("#c62828")
                result_colors.append(("TEXTCOLOR", (3, i + 1), (3, i + 1), color))
            a_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3949ab")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ] + result_colors))
            story.append(a_table)

    # Build PDF and return
    doc.build(story)
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    app.run(debug=True)