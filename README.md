# Color Blindness Detection System (Flask)

This project is a Flask-based web application that provides:

- Ishihara color vision test
- Mosaic color blindness test
- Python-based evaluation and diagnosis
- Downloadable PDF report for the last test

## Running the app

1. Create and activate a virtual environment (recommended).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the Flask app:

```bash
python app.py
```

4. Open the browser at:

- `http://127.0.0.1:5000/`

## Dependencies

- **Flask**: Web framework used to serve the application and handle routing, sessions, and templates.
- **fpdf2**: Used in `app.py` to generate the downloadable PDF report (`/download-report` route).

If you prefer `reportlab`, you can install it instead and adjust the PDF generation code accordingly:

```bash
pip install reportlab
```

