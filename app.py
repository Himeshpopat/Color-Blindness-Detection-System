from datetime import datetime
import io

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


# ---- Ishihara configuration ----

ISHIHARA_TOTAL_QUESTIONS = 10


# ---- Mosaic test configuration ----

MOSAIC_QUESTIONS = [
    {
        "id": 1,
        "label": "Mosaic Plate 1",
        "description": "A green-red mosaic with a number hidden inside.",
        "correct_answer": "12",
        "type": "rg",  # red‑green oriented
    },
    {
        "id": 2,
        "label": "Mosaic Plate 2",
        "description": "Warm‑tone tiles forming a digit pattern.",
        "correct_answer": "5",
        "type": "rg",
    },
    {
        "id": 3,
        "label": "Mosaic Plate 3",
        "description": "Cool blue and yellow tiles with a number.",
        "correct_answer": "8",
        "type": "by",  # blue‑yellow oriented
    },
    {
        "id": 4,
        "label": "Mosaic Plate 4",
        "description": "Mixed color mosaic with a two‑digit number.",
        "correct_answer": "26",
        "type": "rg",
    },
    {
        "id": 5,
        "label": "Mosaic Plate 5",
        "description": "High‑contrast blue and yellow grid pattern.",
        "correct_answer": "3",
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
    """Server‑side interpretation of Ishihara style scores."""
    if total <= 0:
        return "Insufficient data to determine result."

    percentage = normal_score / total

    if percentage >= 0.8:
        return "No Color Vision Deficiency Detected"

    if protan_score > deutan_score:
        return "Possible Protanopia (red‑weak / red‑blind)"

    if deutan_score > protan_score:
        return "Possible Deuteranopia (green‑weak / green‑blind)"

    return "Non‑specific Color Vision Difference"


def store_report(report: dict) -> None:
    """Store the latest report in the session."""
    session["last_report"] = report


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/test")
def test():
    # Ishihara test page (front‑end handled progression, backend handles diagnosis)
    return render_template("test.html", total_questions=ISHIHARA_TOTAL_QUESTIONS)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/reports")
def reports():
    # Existing analytics page; currently still mostly client‑side.
    return render_template("reports.html")


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
    return redirect(url_for("result"))


@app.route("/ishihara-submit", methods=["POST"])
def ishihara_submit():
    """Receive Ishihara scores from the front‑end and evaluate in Python."""
    try:
        normal_score = int(request.form.get("normalScore", "0"))
        protan_score = int(request.form.get("protanScore", "0"))
        deutan_score = int(request.form.get("deutanScore", "0"))
        total_questions = int(request.form.get("totalQuestions", str(ISHIHARA_TOTAL_QUESTIONS)))
    except ValueError:
        normal_score = protan_score = deutan_score = 0
        total_questions = ISHIHARA_TOTAL_QUESTIONS

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
        },
        "diagnosis": diagnosis,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    store_report(report)
    return redirect(url_for("result"))


@app.route("/result")
def result():
    report = session.get("last_report")
    if not report:
        # Fallback: if no report, send user to home.
        return redirect(url_for("index"))
    return render_template("result.html", report=report)


@app.route("/download-report")
def download_report():
    report = session.get("last_report")
    if not report:
        return redirect(url_for("index"))

    # Lazy import to avoid dependency issues if PDF is not installed yet.
    try:
        from fpdf import FPDF
    except Exception:
        # If fpdf is not installed, show a simple text file instead.
        buffer = io.BytesIO()
        content_lines = [
            "Color Blindness Detection System Report",
            "",
            f"Test: {report.get('test_name', 'Unknown')}",
            f"Diagnosis: {report.get('diagnosis', '-')}",
            f"Timestamp: {report.get('timestamp', '-')}",
        ]
        buffer.write("\n".join(content_lines).encode("utf-8"))
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="text/plain",
            as_attachment=True,
            download_name="color_vision_report.txt",
        )

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Color Blindness Detection System", ln=True)

    pdf.set_font("Arial", "", 12)
    pdf.ln(5)
    pdf.cell(0, 8, f"Test: {report.get('test_name', 'Unknown')}", ln=True)
    pdf.cell(0, 8, f"Diagnosis: {report.get('diagnosis', '-')}", ln=True)
    pdf.cell(0, 8, f"Timestamp: {report.get('timestamp', '-')}", ln=True)

    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Details:", ln=True)

    pdf.set_font("Arial", "", 11)
    kind = report.get("kind")
    if kind == "mosaic":
        summary = report.get("summary", {})
        pdf.cell(0, 8, f"Score: {summary.get('correct', 0)} / {summary.get('total', 0)}", ln=True)
        pdf.cell(
            0,
            8,
            f"Red-Green correct: {summary.get('rg_correct', 0)} / {summary.get('rg_total', 0)}",
            ln=True,
        )
        pdf.cell(
            0,
            8,
            f"Blue-Yellow correct: {summary.get('by_correct', 0)} / {summary.get('by_total', 0)}",
            ln=True,
        )

        pdf.ln(4)
        for item in report.get("details", []):
            pdf.multi_cell(
                0,
                6,
                f"Q{item['id']} - {item['label']}: expected {item['correct_answer']}, "
                f"you answered {item['user_answer']} "
                f"({'correct' if item['is_correct'] else 'incorrect'})",
            )
            pdf.ln(1)
    elif kind == "ishihara":
        details = report.get("details", {})
        pdf.cell(
            0,
            8,
            f"Normal score: {details.get('normal_score', 0)} / {details.get('total_questions', 0)}",
            ln=True,
        )
        pdf.cell(0, 8, f"Protan matches: {details.get('protan_score', 0)}", ln=True)
        pdf.cell(0, 8, f"Deutan matches: {details.get('deutan_score', 0)}", ln=True)
        pdf.cell(0, 8, f"Accuracy: {details.get('percentage', 0)}%", ln=True)

    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="color_vision_report.pdf",
    )


if __name__ == "__main__":
    app.run(debug=True)

