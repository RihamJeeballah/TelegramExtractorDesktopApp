# desktop/theme.py
APP_QSS = """
* { font-family: Segoe UI, Inter, Arial; font-size: 14px; }
QWidget#AppRoot { background: #0f172a; color: #e5e7eb; }
QGroupBox {
  border: 1px solid #1f2937; border-radius: 10px; margin-top: 12px;
  background: #0b1221; padding: 12px;
}
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 4px; color: #93c5fd; }
QLineEdit, QComboBox, QTextEdit {
  background: #0f1b31; border: 1px solid #1f2937; border-radius: 8px; padding: 8px; color: #e5e7eb;
}
QLineEdit:disabled { color:#94a3b8; }
QPushButton {
  background: #2563eb; border: none; border-radius: 8px; padding: 9px 14px; color: white; font-weight: 600;
}
QPushButton:disabled { background:#334155; color:#cbd5e1; }
QPushButton#ghost { background: transparent; border: 1px solid #334155; color: #cbd5e1; }
QLabel[class="h1"] { font-size: 20px; font-weight: 800; color:#f8fafc; margin: 6px 0 2px 0; }
QLabel[class="hint"] { color:#a5b4fc; }
QLabel[class="muted"] { color:#94a3b8; }
QTableView {
  background:#0f1b31; gridline-color:#1f2937; border:1px solid #1f2937; border-radius: 8px;
}
"""
