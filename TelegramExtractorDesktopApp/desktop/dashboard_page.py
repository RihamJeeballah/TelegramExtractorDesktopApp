from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QMessageBox, QTextBrowser, QTabWidget, QTextEdit, QTableWidget, QTableWidgetItem,
    QListWidget, QListWidgetItem, QHBoxLayout, QInputDialog   # ⬅️ added
)
from PySide6.QtCore import Qt, QTimer  # ⬅️ QTimer added
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import UserAlreadyParticipantError, SessionPasswordNeededError, AuthKeyDuplicatedError  # ⬅️ updated
from telethon.sessions import StringSession   # kept (backward compat; unused now)
import asyncio, json, subprocess, pandas as pd
from urllib.parse import urlparse
from pathlib import Path
from desktop.config import load_config, save_config

# --- Import listener/exporter modules ---
# NOTE: kept for backward compatibility; listener now runs on Railway
# from desktop.listener_module import start_listener  # (unused in new flow)
from desktop.exporter_module import export_as_pdf, DATA_FILE

# ✅ Local extractor (LLM + regex)
from desktop.extractor_module import extract_fields, set_openai_key, set_model

# 🌐 HTTP client to talk to Railway
import httpx

SESSION_FILE = Path.home() / ".telegram_extractor" / "user_session"
GROUPS_FILE = Path.home() / ".telegram_extractor" / "groups.json"

# 🌐 Set your Railway base URL here
SERVER_URL = "http://76.13.218.208:8000"

class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        self.client = None
        self.current_chat = None
        self.group_names_cache = {}  # cache group names

        self.tabs = QTabWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

        # 🔁 When switching tabs, auto-ensure chats are there
        self.tabs.currentChanged.connect(self._on_tab_changed)  # ⬅️ NEW

        # --- Tab 1: Connect to Telegram ---
        self.connect_tab = QWidget()
        connect_layout = QVBoxLayout(self.connect_tab)

        title = QLabel("🔑 Connect your Telegram Account")
        title.setStyleSheet("font-size:18px; font-weight:600; color:#3b82f6;")
        connect_layout.addWidget(title)

        instr = QTextBrowser()
        instr.setOpenExternalLinks(True)
        instr.setHtml("""
        <h3>📌 خطوات الحصول على Telegram API ID و API Hash</h3>
        <ol>
          <li>اذهب إلى: <a href='https://my.telegram.org/auth'>https://my.telegram.org/auth</a></li>
          <li>سجّل الدخول باستخدام رقم هاتفك (سيصلك كود من Telegram).</li>
          <li>اختر <b>API Development Tools</b>.</li>
          <li>اضغط على <b>Create new application</b>.</li>
          <li>بعد الحفظ سيظهر لك:
            <ul>
              <li><b>API ID</b> → رقم</li>
              <li><b>API Hash</b> → نص طويل (مثل كلمة سر)</li>
            </ul>
          </li>
        </ol>
        <p style="color:red;"><b>⚠️ لا تشارك API ID أو API Hash مع أي شخص آخر.</b></p>
        """)
        connect_layout.addWidget(instr)

        self.phone = QLineEdit(); self.phone.setPlaceholderText("Enter your phone (+968xxxxxxxx)")
        self.api_id = QLineEdit(); self.api_id.setPlaceholderText("API ID")
        self.api_hash = QLineEdit(); self.api_hash.setPlaceholderText("API Hash")

        connect_layout.addWidget(QLabel("Phone")); connect_layout.addWidget(self.phone)
        connect_layout.addWidget(QLabel("API ID")); connect_layout.addWidget(self.api_id)
        connect_layout.addWidget(QLabel("API Hash")); connect_layout.addWidget(self.api_hash)

        self.btn_connect = QPushButton("Connect to Telegram")
        self.btn_connect.setObjectName("primary")
        self.btn_connect.clicked.connect(self._connect_telegram)
        connect_layout.addWidget(self.btn_connect)

        self.status = QLabel("")
        connect_layout.addWidget(self.status)

        self.tabs.addTab(self.connect_tab, "Connect")

        # --- Tab 2: Telegram Chats ---
        self.chats_tab = QWidget()
        chats_layout = QHBoxLayout(self.chats_tab)

        chat_list_panel = QVBoxLayout()
        self.btn_refresh_chats = QPushButton("🔄 Refresh Chats List")
        self.btn_refresh_chats.setStyleSheet("background:#10b981; color:white; padding:6px; border-radius:8px;")
        self.btn_refresh_chats.clicked.connect(self._refresh_chats_list)
        chat_list_panel.addWidget(self.btn_refresh_chats)

        self.chat_list = QListWidget()
        self.chat_list.itemClicked.connect(self._open_chat)
        chat_list_panel.addWidget(self.chat_list, 100)
        chats_layout.addLayout(chat_list_panel, 30)

        right_panel = QVBoxLayout()
        self.btn_refresh = QPushButton("🔄 Refresh Chat")
        self.btn_refresh.setStyleSheet("background:#3b82f6; color:white; padding:6px; border-radius:8px;")
        self.btn_refresh.clicked.connect(self._refresh_chat)
        right_panel.addWidget(self.btn_refresh)

        self.chats_box = QTextEdit()
        self.chats_box.setReadOnly(True)
        self.chats_box.setPlaceholderText("📨 Select a chat to see messages...")
        right_panel.addWidget(self.chats_box, 80)

        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Type a message...")
        self.btn_send = QPushButton("Send")
        self.btn_send.clicked.connect(self._send_message)

        send_layout = QHBoxLayout()
        send_layout.addWidget(self.message_input, 80)
        send_layout.addWidget(self.btn_send, 20)
        right_panel.addLayout(send_layout)
        chats_layout.addLayout(right_panel, 70)

        self.tabs.addTab(self.chats_tab, "Chats")

        # --- Tab 3: Groups ---
        self.groups_tab = QWidget()
        groups_layout = QVBoxLayout(self.groups_tab)

        self.group_input = QLineEdit()
        self.group_input.setPlaceholderText("Paste group/channel link here...")
        groups_layout.addWidget(self.group_input)

        self.btn_group_info = QPushButton("ℹ️ Get Group Info")
        self.btn_group_info.clicked.connect(self._get_group_info)
        groups_layout.addWidget(self.btn_group_info)

        self.btn_join_group = QPushButton("➕ Join Group")
        self.btn_join_group.clicked.connect(self._join_group)
        groups_layout.addWidget(self.btn_join_group)

        self.group_result = QLabel("Result will appear here...")
        groups_layout.addWidget(self.group_result)

        self.saved_groups_list = QListWidget()
        groups_layout.addWidget(QLabel("📂 Saved Groups:"))
        groups_layout.addWidget(self.saved_groups_list, 100)

        self.tabs.addTab(self.groups_tab, "Groups")

        # --- Tab 4: Listener ---
        self.listener_tab = QWidget()
        listener_layout = QVBoxLayout(self.listener_tab)
        listener_layout.addWidget(QLabel("🎧 اختر القروبات التي تريد استخراج المعلومات منها:"))

        self.listener_groups_list = QListWidget()
        listener_layout.addWidget(self.listener_groups_list, 100)

        self.btn_load_listener_groups = QPushButton("🔄 تحميل القروبات")
        self.btn_load_listener_groups.clicked.connect(self._load_groups_for_listener)
        listener_layout.addWidget(self.btn_load_listener_groups)

        self.btn_start_listener = QPushButton("▶️ Start Listening")
        self.btn_start_listener.setStyleSheet("background:#22c55e; color:white; padding:6px; border-radius:8px;")
        self.btn_start_listener.clicked.connect(self._start_listener)
        listener_layout.addWidget(self.btn_start_listener)

        # Optional: reset server session
        self.btn_reset_server = QPushButton("♻️ Reset Server Session")
        self.btn_reset_server.clicked.connect(lambda: asyncio.create_task(self._reset_server_session()))
        listener_layout.addWidget(self.btn_reset_server)

        self.listener_output = QTextEdit()
        self.listener_output.setReadOnly(True)
        listener_layout.addWidget(self.listener_output, 100)

        self.tabs.addTab(self.listener_tab, "Listener")

        # --- Tab 5: Data Table ---
        self.table_tab = QWidget()
        table_layout = QVBoxLayout(self.table_tab)

        self.btn_reload_table = QPushButton("🔄 Reload Extracted Data")
        # New: fetch raw messages from server, extract locally, then reload table
        self.btn_reload_table.clicked.connect(lambda: asyncio.create_task(self._process_all_server_messages()))
        table_layout.addWidget(self.btn_reload_table)

        self.data_table = QTableWidget()
        table_layout.addWidget(self.data_table)

        self.btn_export_excel = QPushButton("📊 Export as Excel")
        self.btn_export_excel.clicked.connect(self._export_excel_file)
        table_layout.addWidget(self.btn_export_excel)

        self.btn_export_pdf = QPushButton("📄 Export as PDF")
        self.btn_export_pdf.clicked.connect(self._export_pdf)
        table_layout.addWidget(self.btn_export_pdf)

        self.tabs.addTab(self.table_tab, "Table")

        # ✅ Try auto-login if a session file exists
        if SESSION_FILE.with_suffix(".session").exists():
            self._auto_login()

        self._load_saved_groups()

        # 🔌 Keep local Telegram connection alive while browsing other tabs
        self._keepalive = QTimer(self)                 # ⬅️ NEW
        self._keepalive.setInterval(30000)             # 30s
        self._keepalive.timeout.connect(lambda: asyncio.create_task(self._keep_client_alive()))
        self._keepalive.start()

    # -------- NEW: when user switches tabs, make sure Chats is populated --------
    def _on_tab_changed(self, index: int):
        try:
            if self.tabs.widget(index) is self.chats_tab:
                # If chats are empty, auto-load; if client disconnected, reconnect first.
                if not self.client:
                    return
                async def ensure():
                    try:
                        if not self.client.is_connected():
                            await self.client.connect()
                        if await self.client.is_user_authorized():
                            if self.chat_list.count() == 0:
                                await self._load_chats(force=True)
                            # If a chat was previously selected, refresh its messages
                            if self.current_chat:
                                self._refresh_chat()
                        else:
                            self.status.setText("⚠️ Local session not authorized. Please Connect again.")
                    except Exception as e:
                        self.status.setText(f"⚠️ Chats reload failed: {e}")
                asyncio.create_task(ensure())
        except Exception:
            pass

    # -------- NEW: lightweight keep-alive so the local client stays connected ----
    async def _keep_client_alive(self):
        if not self.client:
            return
        try:
            if not self.client.is_connected():
                await self.client.connect()
            # quick no-op check; avoid heavy calls
            await self.client.get_me()
        except Exception:
            # don't spam popups; a silent reconnect will happen on demand
            pass

    # ============ LOGIN ============
    def _auto_login(self):
        cfg = load_config()
        api_id = cfg.get("telegram_api_id")
        api_hash = cfg.get("telegram_api_hash")
        if not api_id or not api_hash:
            self.status.setText("⚠️ Auto login failed: Missing API ID/Hash in config")
            return

        async def do_auto():
            try:
                self.client = TelegramClient(str(SESSION_FILE), int(api_id), api_hash)
                await self.client.connect()
                if not await self.client.is_user_authorized():
                    self.status.setText("⚠️ Session expired, please re-login.")
                    return
                me = await self.client.get_me()
                self.chats_box.setText(f"✅ Auto-connected as {me.first_name} (@{me.username})")
                await self._load_chats(force=True)

                # ✅ Jump directly to Chats tab
                self.tabs.setCurrentWidget(self.chats_tab)
                QMessageBox.information(self, "Auto Login", f"Welcome back {me.first_name}!")

            except AuthKeyDuplicatedError:
                # Local session invalidated by Telegram (used from two IPs)
                try:
                    bad = Path(str(SESSION_FILE) + ".session")
                    if bad.exists():
                        bad.unlink()
                except Exception:
                    pass
                self.status.setText("♻️ Local session was invalidated. Please connect again.")
            except Exception as e:
                self.status.setText(f"❌ Auto login failed: {e}")

        asyncio.create_task(do_auto())

    def _connect_telegram(self):
        # Prevent re-entry / double-clicks
        if getattr(self, "_connecting", False):
            return

        phone = self.phone.text().strip()
        api_id = self.api_id.text().strip()
        api_hash = self.api_hash.text().strip()
        if not (phone and api_id and api_hash):
            QMessageBox.warning(self, "Missing Data", "Please fill all fields.")
            return

        self._connecting = True
        self.btn_connect.setEnabled(False)
        self.status.setText("⏳ Connecting to Telegram...")

        async def do_connect():
            try:
                # Dispose previous client if any
                if self.client:
                    try:
                        if self.client.is_connected():
                            await self.client.disconnect()
                    except Exception:
                        pass
                    self.client = None

                # Fresh client using local session file
                self.client = TelegramClient(str(SESSION_FILE), int(api_id), api_hash)
                await self.client.connect()

                # If not authorized, run explicit GUI login (no console prompts)
                if not await self.client.is_user_authorized():
                    # 1) Send code
                    await self.client.send_code_request(phone)

                    # 2) Ask for the code
                    code, ok = QInputDialog.getText(self, "Telegram Code", "Enter the code you received:")
                    if not ok or not code.strip():
                        self.status.setText("❌ Login cancelled.")
                        return

                    # 3) Try sign-in; handle 2FA if needed
                    try:
                        await self.client.sign_in(phone, code.strip())
                    except SessionPasswordNeededError:
                        pw, ok = QInputDialog.getText(self, "Two-Step Password",
                                                      "Enter your Telegram password:",
                                                      QLineEdit.Password)
                        if not ok or not pw.strip():
                            self.status.setText("❌ Login cancelled (2FA).")
                            return
                        await self.client.sign_in(password=pw.strip())

                # Final check
                if not await self.client.is_user_authorized():
                    raise RuntimeError("Unable to authorize this session.")

                me = await self.client.get_me()
                self.chats_box.setText(f"✅ Connected as {getattr(me, 'first_name', '')} (@{getattr(me, 'username', None)})")
                QMessageBox.information(self, "Success", f"Connected as {getattr(me, 'first_name', '')}")

                # Save credentials
                cfg = load_config()
                cfg["telegram_api_id"] = api_id
                cfg["telegram_api_hash"] = api_hash
                if not cfg.get("local_phone"):
                    cfg["local_phone"] = phone  # used as unique user id on the server
                save_config(cfg)

                await self._load_chats(force=True)
                self.tabs.setCurrentWidget(self.chats_tab)
                self.status.setText("✅ Ready.")

            except AuthKeyDuplicatedError:
                # Local session became invalid (used from two IPs). Reset file and ask to retry.
                try:
                    bad = Path(str(SESSION_FILE) + ".session")
                    if bad.exists():
                        bad.unlink()
                except Exception:
                    pass
                QMessageBox.information(
                    self,
                    "Session Reset",
                    ("Your previous Telegram session was invalidated by Telegram "
                     "(used from two IPs). I reset the local session.\n\n"
                     "Please press 'Connect to Telegram' again.")
                )
                self.status.setText("♻️ Session reset. Press Connect again.")
            except Exception as e:
                QMessageBox.critical(self, "Connection Failed", str(e))
                self.status.setText("❌ Connection failed.")
            finally:
                self._connecting = False
                self.btn_connect.setEnabled(True)

        asyncio.create_task(do_connect())

    # ============ CHATS ============
    def _refresh_chats_list(self):
        if not self.client:
            QMessageBox.warning(self, "Not Connected", "Please connect to Telegram first.")
            return
        asyncio.create_task(self._load_chats(force=True))

    async def _load_chats(self, force=False):
        try:
            if not self.client.is_connected():
                await self.client.connect()
            self.chat_list.clear()
            dialogs = await self.client.get_dialogs()
            for d in dialogs:
                self.chat_list.addItem(f"{d.name} ({d.id})")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load chats: {e}")

    def _open_chat(self, item):
        chat_id = int(item.text().split("(")[-1][:-1])
        self.current_chat = chat_id
        self._refresh_chat()

    def _refresh_chat(self):
        if not self.current_chat:
            QMessageBox.warning(self, "No Chat", "Select a chat first!")
            return

        async def fetch_messages():
            self.chats_box.clear()
            messages = []
            async for msg in self.client.iter_messages(self.current_chat, limit=50):
                sender = "Me" if msg.out else getattr(msg.sender, "first_name", "Unknown")
                messages.append(f"<b>{sender}:</b> {msg.text or ''}")
            for m in reversed(messages):
                self.chats_box.append(m)

        asyncio.create_task(fetch_messages())

    def _send_message(self):
        if not self.current_chat:
            QMessageBox.warning(self, "No Chat", "Select a chat first!")
            return
        text = self.message_input.text().strip()
        if not text:
            return

        async def send():
            await self.client.send_message(self.current_chat, text)
            self.chats_box.append(f"<b>Me:</b> {text}")
            self.message_input.clear()

        asyncio.create_task(send())

    # ============ GROUPS ============
    def _get_group_info(self):
        link = self.group_input.text().strip()
        if not link:
            QMessageBox.warning(self, "Missing", "Enter group/channel link")
            return

        async def fetch():
            try:
                if "/+" in link:
                    invite_hash = link.split("+")[-1]
                    try:
                        result = await self.client(ImportChatInviteRequest(invite_hash))
                        entity = result.chats[0]
                    except UserAlreadyParticipantError:
                        entity = await self.client.get_entity(link)
                        QMessageBox.information(self, "Info", "✅ You are already a member of this group")
                else:
                    username = urlparse(link).path.strip("/")
                    entity = await self.client.get_entity(username)

                name = getattr(entity, "title", "Unknown")
                gid = entity.id
                self.group_result.setText(f"✅ Group: {name}\n🆔 ID: {gid}")

                # Save with name+id
                groups = []
                if GROUPS_FILE.exists():
                    groups = json.loads(GROUPS_FILE.read_text())
                entry = {"id": gid, "name": name}
                if entry not in groups:
                    groups.append(entry)
                    GROUPS_FILE.write_text(json.dumps(groups, indent=2))
                self._load_saved_groups()

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed: {e}")

        asyncio.create_task(fetch())

    def _join_group(self):
        link = self.group_input.text().strip()
        if not link:
            QMessageBox.warning(self, "Missing", "Enter group/channel link")
            return

        async def join():
            try:
                entity = None
                if "/+" in link:
                    invite_hash = link.split("+")[-1]
                    try:
                        result = await self.client(ImportChatInviteRequest(invite_hash))
                        entity = result.chats[0]
                    except UserAlreadyParticipantError:
                        entity = await self.client.get_entity(link)
                        QMessageBox.information(self, "Info", "✅ You are already a member of this group")
                else:
                    username = urlparse(link).path.strip("/")
                    entity = await self.client.get_entity(username)
                    await self.client(JoinChannelRequest(entity))

                if entity:
                    QMessageBox.information(self, "Success", f"✅ Joined or confirmed membership in {entity.title}")
                    await self._safe_reload_chats()
                    gid = entity.id
                    name = getattr(entity, "title", "Unknown")
                    groups = []
                    if GROUPS_FILE.exists():
                        groups = json.loads(GROUPS_FILE.read_text())
                    entry = {"id": gid, "name": name}
                    if entry not in groups:
                        groups.append(entry)
                        GROUPS_FILE.write_text(json.dumps(groups, indent=2))
                    self._load_saved_groups()

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Join failed: {e}")

        asyncio.create_task(join())

    async def _safe_reload_chats(self):
        try:
            await self._load_chats()
        except Exception as e:
            print(f"[WARN] Chat reload failed: {e}")

    def _load_saved_groups(self):
        self.saved_groups_list.clear()
        if GROUPS_FILE.exists():
            groups = json.loads(GROUPS_FILE.read_text())
            for g in groups:
                if isinstance(g, dict):
                    self.saved_groups_list.addItem(f"{g['name']} ({g['id']})")
                else:
                    self.saved_groups_list.addItem(str(g))

    # ============ LISTENER ============
    def _load_groups_for_listener(self):
        self.listener_groups_list.clear()
        if GROUPS_FILE.exists():
            groups = json.loads(GROUPS_FILE.read_text())
            for g in groups:
                if isinstance(g, dict):
                    gid = g.get("id")
                    name = g.get("name", f"Group {gid}")
                else:
                    gid = g
                    name = f"Group {gid}"
                self.group_names_cache[str(gid)] = name
                item = QListWidgetItem(f"{name} ({gid})")
                item.setCheckState(Qt.Unchecked)
                self.listener_groups_list.addItem(item)
        self.listener_output.append("✅ Loaded groups.")

    def _get_selected_listener_ids(self):
        ids = []
        for i in range(self.listener_groups_list.count()):
            item = self.listener_groups_list.item(i)
            if item.checkState() == Qt.Checked:
                gid = item.text().split("(")[-1].replace(")", "")
                ids.append(int(gid))
        return ids

    def _start_listener(self):
        """
        Start 24/7 listening on Railway using a **server-owned session**.
        Flow:
          - Ensure server has a session for this phone; if not, run /session/init (send code) + ask user for code + /session/complete
          - Then POST /start_listener with only {phone, groups}
        """
        ids = self._get_selected_listener_ids()
        if not ids:
            QMessageBox.warning(self, "Error", "Select at least one group.")
            return

        async def run():
            try:
                cfg = load_config()
                phone = (cfg.get("local_phone") or self.phone.text().strip())
                api_id = (cfg.get("telegram_api_id") or self.api_id.text().strip())
                api_hash = (cfg.get("telegram_api_hash") or self.api_hash.text().strip())

                if not (phone and api_id and api_hash):
                    QMessageBox.warning(self, "Missing", "Phone / API ID / API Hash are required.")
                    return

                # 1) Does the server already have a session?
                async with httpx.AsyncClient(timeout=30) as c:
                    r = await c.get(f"{SERVER_URL}/session/status/{phone}")
                has = (r.status_code == 200 and (r.json() or {}).get("has_session"))

                # 2) If not, create server session (send code) + complete with user input
                if not has:
                    async with httpx.AsyncClient(timeout=30) as c:
                        r = await c.post(f"{SERVER_URL}/session/init", json={
                            "phone": phone,
                            "api_id": str(api_id),
                            "api_hash": str(api_hash),
                        })
                    if r.status_code != 200:
                        QMessageBox.critical(self, "Server", f"Init failed: {r.text}")
                        return

                    code, ok = QInputDialog.getText(self, "Telegram Code", "Enter the code you received in Telegram:")
                    if not ok or not code.strip():
                        self.listener_output.append("❌ Pairing cancelled.")
                        return

                    async with httpx.AsyncClient(timeout=30) as c:
                        r = await c.post(f"{SERVER_URL}/session/complete", json={
                            "phone": phone,
                            "code": code.strip(),
                        })
                    if r.status_code != 200:
                        QMessageBox.critical(self, "Server", f"Complete failed: {r.text}")
                        return
                    self.listener_output.append("🔐 Server session paired successfully.")

                # 3) Start (or keep) the listener — NOTE: no session_string is sent
                async with httpx.AsyncClient(timeout=30) as c:
                    r = await c.post(f"{SERVER_URL}/start_listener", json={
                        "phone": phone,
                        "groups": ids,
                    })
                if r.status_code == 200:
                    self.listener_output.append("✅ Listener started on vps (24/7).")
                    await self._show_server_status()
                else:
                    self.listener_output.append(f"❌ Failed: {r.status_code} - {r.text}")

            except Exception as e:
                self.listener_output.append(f"⚠️ Error: {e}")

        asyncio.create_task(run())

    async def _reset_server_session(self):
        try:
            cfg = load_config()
            phone = cfg.get("local_phone") or self.phone.text().strip()
            if not phone:
                QMessageBox.warning(self, "Missing", "Enter your phone first.")
                return
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(f"{SERVER_URL}/session/logout/{phone}")
            if r.status_code == 200:
                self.listener_output.append("♻️ Server session cleared.")
            else:
                self.listener_output.append(f"❌ Failed to clear: {r.status_code} - {r.text}")
        except Exception as e:
            self.listener_output.append(f"⚠️ Reset error: {e}")

    async def _show_server_status(self):
        """Helper: show a quick status from server (messages count)"""
        try:
            cfg = load_config()
            phone = cfg.get("local_phone") or self.phone.text().strip()
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(f"{SERVER_URL}/get_data/{phone}")
                if r.status_code == 200:
                    data = r.json() or []
                    self.listener_output.append(f"📡 Server has {len(data)} collected messages so far.")
        except Exception as e:
            self.listener_output.append(f"ℹ️ Status fetch failed: {e}")

    # ============ EXTRACTION / TABLE ============
    async def _process_all_server_messages(self):
        try:
            from desktop.exporter_module import DATA_FILE, initialize_data_file

            cfg = load_config()
            phone = cfg.get("local_phone") or self.phone.text().strip()

            if not phone:
                QMessageBox.warning(self, "Missing", "Phone number not found.")
                return

            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(f"{SERVER_URL}/get_data/{phone}")

            if r.status_code != 200:
                QMessageBox.critical(self, "Server Error", f"Failed to fetch data:\n{r.text}")
                return

            messages = r.json() or []

            if not messages:
                QMessageBox.information(self, "No Data", "No messages found on the server yet.")
                return

            initialize_data_file()

            try:
                existing_df = pd.read_excel(DATA_FILE)
            except Exception:
                existing_df = pd.DataFrame()

            existing_ids = set()
            if not existing_df.empty and "message_id" in existing_df.columns:
                existing_ids = set(existing_df["message_id"].astype(str).tolist())

            rows = []

            for msg in messages:
                message_id = str(msg.get("message_id", ""))

                if message_id and message_id in existing_ids:
                    continue

                raw_text = msg.get("text", "")
                extracted = extract_fields(raw_text)

                rows.append({
                    "timestamp": msg.get("timestamp", ""),
                    "chat_id": msg.get("chat_id", ""),
                    "message_id": message_id,
                    "account_number": extracted.get("account_number", ""),
                    "name": extracted.get("name", ""),
                    "amount": extracted.get("amount", ""),
                    "currency": extracted.get("currency", ""),
                    "machinery": extracted.get("machinery", ""),
                    "project": extracted.get("project", ""),
                    "details": extracted.get("details", ""),
                    "raw_message": raw_text,
                })

            if rows:
                new_df = pd.DataFrame(rows)
                final_df = pd.concat([existing_df, new_df], ignore_index=True)
                final_df.to_excel(DATA_FILE, index=False)
            else:
                final_df = existing_df

            self.data_table.setRowCount(len(final_df))
            self.data_table.setColumnCount(len(final_df.columns))
            self.data_table.setHorizontalHeaderLabels(final_df.columns)

            for i in range(len(final_df)):
                for j in range(len(final_df.columns)):
                    self.data_table.setItem(i, j, QTableWidgetItem(str(final_df.iat[i, j])))

            QMessageBox.information(self, "Done", f"✅ Extracted {len(rows)} new messages.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to process server messages: {e}")

    def _load_extracted_data(self):
        try:
            df = pd.read_excel(DATA_FILE)
            self.data_table.setRowCount(len(df))
            self.data_table.setColumnCount(len(df.columns))
            self.data_table.setHorizontalHeaderLabels(df.columns)
            for i, row in df.iterrows():
                for j, val in enumerate(row):
                    self.data_table.setItem(i, j, QTableWidgetItem(str(val)))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load data: {e}")

    def _open_excel(self):
        try:
            subprocess.Popen(["explorer", str(DATA_FILE)])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Excel: {e}")

    def _export_pdf(self):
        pdf = export_as_pdf()
        if pdf:
            QMessageBox.information(self, "Exported", f"✅ PDF saved at:\n{pdf}")

    def _reload_table(self):
        try:
            from desktop.exporter_module import load_data
            df = load_data()
            self.data_table.setRowCount(len(df))
            self.data_table.setColumnCount(len(df.columns))
            self.data_table.setHorizontalHeaderLabels(df.columns)

            for i in range(len(df)):
                for j in range(len(df.columns)):
                    self.data_table.setItem(i, j, QTableWidgetItem(str(df.iat[i, j])))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load table: {e}")

    def _export_excel_file(self):
        from desktop.exporter_module import export_as_excel
        try:
            path = export_as_excel()
            QMessageBox.information(self, "Exported", f"✅ Excel saved at:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export Excel: {e}")