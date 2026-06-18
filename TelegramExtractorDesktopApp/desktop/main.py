from __future__ import annotations
import sys, re, traceback, hashlib
from datetime import datetime
from pathlib import Path
import pandas as pd
from desktop.dashboard_page import DashboardPage
import qasync
import asyncio   


from PySide6.QtCore import Qt, Signal, QAbstractTableModel, QModelIndex, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QApplication, QWidget, QStackedWidget, QVBoxLayout, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QTableView, QMessageBox, QGroupBox,
    QAbstractItemView, QInputDialog
)

# crash log
def _log_excepthook(exctype, value, tb):
    p = Path.home() / ".telegram_extractor" / "last_error.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(traceback.format_exception(exctype, value, tb)), encoding="utf-8")
    sys.__excepthook__(exctype, value, tb)
sys.excepthook = _log_excepthook

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from desktop.config import load_config, save_config
from desktop.export_utils import export_csv, export_excel, export_pdf, export_docx
from desktop.telegram_worker import TelegramWorker

try:
    from shared.extractor import set_openai_key
except Exception:
    def set_openai_key(*_a, **_k): pass

THEME_QSS = """
QWidget { background:#0b1220; color:#cbd5e1; font: 11pt "Segoe UI"; }
QLineEdit, QTextEdit, QComboBox { background:#0f1629; border:1px solid #2a3350; border-radius:12px; padding:10px; }
QPushButton { background:#1e293b; border:1px solid #2a3350; border-radius:12px; padding:10px 16px; color:#cbd5e1; }
QPushButton:hover { background:#22304a; } QPushButton:pressed { background:#1b2740; }
QPushButton#primary { background:#3b82f6; color:white; border:1px solid #3b82f6; }
QWidget#card { background:#0f1629; border:1px solid #27324a; border-radius:16px; }
QLabel#title { font-size:28px; font-weight:800; color:#e5e7eb; padding:4px 0 10px; }
QLabel#footer { color:#8ea0bf; font-size:10pt; padding:8px; }
QGroupBox { border:1px solid #1f2a44; border-radius:12px; margin-top:12px; }
QGroupBox::title { subcontrol-origin: margin; left:12px; padding:0 6px; color:#93c5fd; }
"""

# --------- table model ---------
class DataFrameModel(QAbstractTableModel):
    def __init__(self, df=pd.DataFrame(), parent=None):
        super().__init__(parent); self._df = df
    def setDataFrame(self, df): self.beginResetModel(); self._df = df.copy(); self.endResetModel()
    def rowCount(self, _=QModelIndex()): return 0 if self._df is None else len(self._df)
    def columnCount(self, _=QModelIndex()): return 0 if self._df is None else len(self._df.columns)
    def data(self, idx, role=Qt.DisplayRole):
        if not idx.isValid() or role not in (Qt.DisplayRole, Qt.EditRole): return None
        v = self._df.iat[idx.row(), idx.column()]
        return "" if pd.isna(v) else str(v)
    def headerData(self, s, o, r=Qt.DisplayRole):
        if r != Qt.DisplayRole: return None
        return str(self._df.columns[s] if o==Qt.Horizontal else s)
    def flags(self, _): return Qt.ItemIsSelectable | Qt.ItemIsEnabled

# --------- helpers ---------
PASS_POLICY_RE = re.compile(r'^(?=.{8,}$)(?=.*\d)(?=.*[^A-Za-z0-9])[A-Z].*$')
def _password_error(p: str) -> str | None:
    if not p: return "Password is required."
    if not PASS_POLICY_RE.match(p):
        return ("Password must start with an uppercase letter, be at least 8 characters, "
                "and include at least one number and one special character.")
    return None

def _hash_password(password: str, salt: str | None = None) -> dict:
    import secrets, string
    if not salt:
        salt = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return {"salt": salt, "hash": h}

def _verify_password(password: str, salt: str, pw_hash: str) -> bool:
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return h == pw_hash

# --------- Page 1: Account ---------
class AccountPage(QWidget):
    signed_in = Signal()

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(12)

        title = QLabel("Telegram Extractor App")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignHCenter)
        root.addWidget(title, 0, Qt.AlignHCenter)

        root.addStretch(1)

        card = QWidget(); card.setObjectName("card"); card.setFixedWidth(560)
        cardL = QVBoxLayout(card); cardL.setContentsMargins(24, 24, 24, 24); cardL.setSpacing(14)

        tabs = QHBoxLayout()
        self.btn_tab_signup = QPushButton("Sign up")
        self.btn_tab_signin = QPushButton("Sign in")
        for b in (self.btn_tab_signup, self.btn_tab_signin):
            b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton { padding:10px 18px; border-radius:12px; border:1px solid #2a3350;
                              background:#0f1629; color:#cbd5e1; }
                QPushButton:checked { background:#3b82f6; color:white; border:1px solid #3b82f6; }
            """)
        self.btn_tab_signup.setChecked(True)
        tabs.addStretch(1); tabs.addWidget(self.btn_tab_signup); tabs.addWidget(self.btn_tab_signin); tabs.addStretch(1)
        cardL.addLayout(tabs)

        self.stack = QStackedWidget()
        cardL.addWidget(self.stack)

        # ----- Sign up -----
        su = QWidget(); suL = QGridLayout(su); r = 0
        self.su_phone = QLineEdit()
        self.su_phone.setPlaceholderText("+968xxxxxxxx")
        self.su_phone.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\+\d{6,15}$")))
        suL.addWidget(QLabel("Phone"), r, 0); suL.addWidget(self.su_phone, r, 1); r += 1

        self.su_email = QLineEdit()
        self.su_email.setPlaceholderText("Enter your email")
        suL.addWidget(QLabel("Email"), r, 0); suL.addWidget(self.su_email, r, 1); r += 1

        self.su_pass = QLineEdit(); self.su_pass.setEchoMode(QLineEdit.Password)
        self.su_pass.setPlaceholderText("Password (First Uppercase, ≥8, include digit & special)")
        suL.addWidget(QLabel("Password"), r, 0); suL.addWidget(self.su_pass, r, 1); r += 1

        self.su_pass2 = QLineEdit(); self.su_pass2.setEchoMode(QLineEdit.Password)
        self.su_pass2.setPlaceholderText("Confirm password")
        suL.addWidget(QLabel("Confirm Password"), r, 0); suL.addWidget(self.su_pass2, r, 1); r += 1

        self.btn_create = QPushButton("Create Account"); self.btn_create.setObjectName("primary")
        suL.addWidget(self.btn_create, r, 0, 1, 2); r += 1
        self.stack.addWidget(su)

        # ----- Sign in -----
        si = QWidget(); siL = QGridLayout(si); r = 0
        self.si_phone = QLineEdit()
        self.si_phone.setPlaceholderText("+968xxxxxxxx")
        self.si_phone.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\+\d{6,15}$")))
        siL.addWidget(QLabel("Phone"), r, 0); siL.addWidget(self.si_phone, r, 1); r += 1

        self.si_pass = QLineEdit(); self.si_pass.setEchoMode(QLineEdit.Password)
        self.si_pass.setPlaceholderText("Password")
        siL.addWidget(QLabel("Password"), r, 0); siL.addWidget(self.si_pass, r, 1); r += 1

        h = QHBoxLayout()
        self.btn_signin = QPushButton("Sign In"); self.btn_signin.setObjectName("primary")
        h.addWidget(self.btn_signin)
        siL.addLayout(h, r, 0, 1, 2); r += 1

        self.btn_forgot = QPushButton("Forgot Password?")
        siL.addWidget(self.btn_forgot, r, 0, 1, 2); r += 1

        self.stack.addWidget(si)

        container = QHBoxLayout()
        container.addStretch(1); container.addWidget(card, 0, Qt.AlignHCenter); container.addStretch(1)
        root.addLayout(container)
        root.addStretch(2)

        footer = QLabel("© powered by Equipation Ltd 2025")
        footer.setObjectName("footer"); footer.setAlignment(Qt.AlignHCenter)
        root.addWidget(footer, 0, Qt.AlignHCenter)

        # wire
        self.btn_tab_signup.clicked.connect(lambda: self._switch_tab(0))
        self.btn_tab_signin.clicked.connect(lambda: self._switch_tab(1))
        self.btn_create.clicked.connect(self._create_account)
        self.btn_signin.clicked.connect(self._sign_in)
        self.btn_forgot.clicked.connect(self._forgot_password)

    def _switch_tab(self, idx):
        self.stack.setCurrentIndex(idx)
        self.btn_tab_signup.setChecked(idx == 0)
        self.btn_tab_signin.setChecked(idx == 1)

    def _create_account(self):
        phone = self.su_phone.text().strip()
        email = self.su_email.text().strip()
        p1 = self.su_pass.text().strip()
        p2 = self.su_pass2.text().strip()

        if not phone or not self.su_phone.hasAcceptableInput():
            QMessageBox.warning(self, "Phone", "Enter a valid phone."); return
        if not email or "@" not in email:
            QMessageBox.warning(self, "Email", "Enter a valid email."); return
        err = _password_error(p1)
        if err: QMessageBox.warning(self, "Password", err); return
        if p1 != p2: QMessageBox.warning(self, "Password", "Passwords do not match."); return

        hp = _hash_password(p1)
        cfg = load_config()
        cfg["local_phone"] = phone
        cfg["local_user_id"] = phone
        cfg["local_email"] = email
        cfg["password_salt"] = hp["salt"]
        cfg["password_hash"] = hp["hash"]
        save_config(cfg)
        QMessageBox.information(self, "Account created", "Your account has been created. Please sign in.")
        self._switch_tab(1)

    def _sign_in(self):
        phone = self.si_phone.text().strip()
        pw    = self.si_pass.text().strip()
        cfg = load_config()
        ok_user = (phone and phone == cfg.get("local_phone"))
        ok_pw = (cfg.get("password_salt") and cfg.get("password_hash") and
                 _verify_password(pw, cfg["password_salt"], cfg["password_hash"]))
        if not ok_user or not ok_pw:
            QMessageBox.critical(self, "Sign in failed", "Invalid phone or password."); return
        self.signed_in.emit()

    def _forgot_password(self):
        cfg = load_config()
        if not cfg.get("local_email"):
            QMessageBox.critical(self, "Error", "No email registered. Please sign up again."); return

        # Step 1: Ask for email
        email, ok = QInputDialog.getText(self, "Forgot Password", "Enter your registered email:")
        if not ok or email.strip() != cfg["local_email"]:
            QMessageBox.critical(self, "Error", "Email not found."); return

        # Step 2: Send OTP
        from desktop.email_utils import generate_otp, send_otp_email
        otp = generate_otp()
        if not send_otp_email(email, otp):
            QMessageBox.critical(self, "Error", "Failed to send OTP email."); return

        # Step 3: Ask for OTP
        entered, ok = QInputDialog.getText(self, "Verify OTP", f"Enter the 6-digit code sent to {email}:")
        if not ok or entered.strip() != otp:
            QMessageBox.critical(self, "Error", "Invalid code."); return

        # Step 4: Ask for new password
        new_pw, ok = QInputDialog.getText(self, "Reset Password", "Enter new password:", QLineEdit.Password)
        if not ok or not new_pw.strip():
            return
        err = _password_error(new_pw.strip())
        if err:
            QMessageBox.warning(self, "Password", err); return

        hp = _hash_password(new_pw.strip())
        cfg["password_salt"] = hp["salt"]
        cfg["password_hash"] = hp["hash"]
        save_config(cfg)

        QMessageBox.information(self, "Success", "Password has been reset. Please sign in again.")

# --------- Main App ---------
class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Telegram Extractor App")
        self.resize(800, 600)

        self.stack = QStackedWidget()
        self.account = AccountPage()
        self.stack.addWidget(self.account)

        lay = QVBoxLayout(self)
        lay.addWidget(self.stack)

        self.account.signed_in.connect(self._go_dashboard)

    def _go_dashboard(self):
        dash = QLabel("✅ Dashboard Screen (placeholder)")
        dash.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(dash)
        self.stack.setCurrentWidget(dash)
class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Telegram Extractor App")
        self.resize(800, 600)

        self.stack = QStackedWidget()
        self.account = AccountPage()
        self.stack.addWidget(self.account)

        lay = QVBoxLayout(self)
        lay.addWidget(self.stack)

        self.account.signed_in.connect(self._go_dashboard)

    def _go_dashboard(self):
        dash = DashboardPage()
        self.stack.addWidget(dash)
        self.stack.setCurrentWidget(dash)
        self.stack.setCurrentWidget(dash)

if __name__ == "__main__":
    app = qasync.QApplication(sys.argv)
    app.setStyleSheet(THEME_QSS)
    w = App()
    w.show()
    print("✅ App loop starting...")
    with qasync.QEventLoop(app) as loop:
        asyncio.set_event_loop(loop)
        loop.run_forever()