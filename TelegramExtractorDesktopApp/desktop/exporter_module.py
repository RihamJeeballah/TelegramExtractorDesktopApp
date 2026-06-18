# desktop/exporter_module.py
import os
import pandas as pd
from pathlib import Path
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet


DATA_FILE = Path.home() / "Documents" / "telegram_extracted_data.xlsx"

# Ensure file exists
def initialize_data_file():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        df = pd.DataFrame(columns=[
            "timestamp", "account_number", "name", "amount",
            "currency", "project", "details", "raw_message"
        ])
        df.to_excel(DATA_FILE, index=False)

def append_row(data: dict):
    initialize_data_file()
    try:
        df = pd.read_excel(DATA_FILE)
    except Exception:
        df = pd.DataFrame(columns=[
            "timestamp", "account_number", "name", "amount",
            "currency", "project", "details", "raw_message"
        ])
    df.loc[len(df)] = data
    df.to_excel(DATA_FILE, index=False)

def load_data():
    initialize_data_file()
    return pd.read_excel(DATA_FILE)

def export_as_excel(path=None):
    if not path:
        path = DATA_FILE
    df = load_data()
    df.to_excel(path, index=False)
    return path

def export_as_pdf(path=None):
    initialize_data_file()
    if not path:
        path = DATA_FILE.with_suffix(".pdf")

    df = load_data()
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()

    data = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
    ]))

    doc.build([Paragraph("Extracted Telegram Data", styles["Title"]), table])
    return path
