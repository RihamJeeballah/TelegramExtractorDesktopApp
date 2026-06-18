# desktop/telegram_worker.py
from __future__ import annotations
import asyncio, os
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd

from PySide6.QtCore import QObject, QThread, Signal

from desktop.config import load_config, save_config

# optional OpenAI extractor (if your shared/extractor.py exists)
try:
    from shared.extractor import extract_fields
except Exception:
    def extract_fields(text: str):
        # fallback: minimal fields
        return {
            "account_number": "",
            "name": "",
            "amount": "",
            "currency": "",
            "machinery": "",
            "project": "",
            "details": ""
        }

class TelegramWorker(QThread):
    status      = Signal(str)
    error       = Signal(str)
    code_sent   = Signal()
    signed_in   = Signal()
    groups_ready= Signal(list)     # [{'id': int, 'title': str}]
    new_dataframe = Signal(pd.DataFrame)
    tick        = Signal()

    def __init__(self):
        super().__init__()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.client = None
        self.api_id: int | None = None
        self.api_hash: str | None = None
        self.phone: str | None = None
        self.running = False
        self.interval = 60
        self.selected_ids: List[int] = []
        self.df = pd.DataFrame(columns=[
            "timestamp","chat_title","chat_id","message_id",
            "account_number","name","amount","currency","project","details","raw_message"
        ])
        self.last_id: Dict[int,int] = {}  # chat_id -> last seen id

    # ---------- thread loop ----------
    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._idle())

    async def _idle(self):
        while True:
            await asyncio.sleep(0.2)

    # ---------- public API ----------
    def set_interval(self, seconds: int): self.interval = max(1, int(seconds))
    def set_selected_groups(self, ids: List[int]): self.selected_ids = list(ids)

    def request_code(self, api_id: int, api_hash: str, phone: str):
        self.api_id = api_id; self.api_hash = api_hash; self.phone = phone
        fut = asyncio.run_coroutine_threadsafe(self._async_request_code(), self.loop)
        return fut.result()

    def sign_in(self, code: str):
        fut = asyncio.run_coroutine_threadsafe(self._async_sign_in(code), self.loop)
        return fut.result()

    def fetch_groups(self):
        fut = asyncio.run_coroutine_threadsafe(self._async_fetch_groups(), self.loop)
        return fut.result()

    def start_extraction(self):
        if not self.running:
            self.running = True
            asyncio.run_coroutine_threadsafe(self._async_extract_loop(), self.loop)

    def stop_extraction(self):
        self.running = False

    def logout(self):
        # disconnect but keep the session file so user remains logged in unless they want to delete it
        try:
            if self.client:
                asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop).result(5)
        except Exception:
            pass

    # ---------- helper ----------
    def _session_path(self) -> str:
        cfg = load_config()
        base = Path(cfg.get("telegram_session_dir", Path.home()/".telegram_extractor"/"sessions"))
        base.mkdir(parents=True, exist_ok=True)
        tag = (self.phone or "default").replace("+","plus")
        return str(base / f"{tag}.session")

    async def _ensure_client(self):
        if self.client: return
        if not (self.api_id and self.api_hash and self.phone):
            self.error.emit("Telegram credentials missing. Enter API ID, API Hash, and phone.")
            raise RuntimeError("missing creds")
        from telethon import TelegramClient
        self.client = TelegramClient(self._session_path(), self.api_id, self.api_hash)
        await self.client.connect()

    # ---------- coroutines ----------
    async def _async_request_code(self):
        try:
            await self._ensure_client()
            from telethon.errors import ApiIdInvalidError
            self.status.emit("Connecting to Telegram…")
            sent = await self.client.send_code_request(self.phone)
            self.code_sent.emit()
            self.status.emit("Code sent. Check Telegram app.")
        except Exception as e:
            self.error.emit(f"Send code failed: {e}")

    async def _async_sign_in(self, code: str):
        try:
            await self._ensure_client()
            from telethon.errors import SessionPasswordNeededError
            await self.client.sign_in(self.phone, code)
            cfg = load_config()
            cfg["telegram_api_id"] = str(self.api_id)
            cfg["telegram_api_hash"] = self.api_hash
            cfg["telegram_phone"] = self.phone
            cfg["telegram_session_path"] = self._session_path()
            save_config(cfg)
            self.signed_in.emit()
            self.status.emit("Signed in to Telegram.")
        except Exception as e:
            self.error.emit(f"Sign in failed: {e}")

    async def _async_fetch_groups(self):
        try:
            await self._ensure_client()
            groups = []
            async for d in self.client.iter_dialogs():
                ent = d.entity
                # only groups/channels
                if getattr(ent, "megagroup", False) or getattr(ent, "broadcast", False):
                    groups.append({"id": int(ent.id), "title": d.name})
            self.groups_ready.emit(groups)
            self.status.emit(f"Loaded {len(groups)} groups/channels.")
        except Exception as e:
            self.error.emit(f"Fetch groups failed: {e}")

    async def _async_extract_loop(self):
        if not self.client:
            try:
                await self._ensure_client()
            except Exception:
                return
        self.status.emit("Extractor started.")
        from telethon.tl.types import PeerChannel, PeerChat
        while self.running:
            try:
                for gid in list(self.selected_ids):
                    # handle both small groups and channels
                    try:
                        entity = await self.client.get_entity(gid)
                    except Exception:
                        continue
                    last_id = self.last_id.get(gid, 0)
                    added = 0
                    async for msg in self.client.iter_messages(entity, limit=100):
                        if msg.id <= last_id: break
                        text = (msg.message or "").strip()
                        if not text: continue
                        data = extract_fields(text) or {}
                        row = {
                            "timestamp": (msg.date or None),
                            "chat_title": getattr(entity, "title", getattr(entity, "username", str(gid))),
                            "chat_id": int(gid),
                            "message_id": int(msg.id),
                            "account_number": data.get("account_number",""),
                            "name": data.get("name",""),
                            "amount": data.get("amount",""),
                            "currency": data.get("currency",""),
                            "project": data.get("project",""),
                            "details": data.get("details",""),
                            "raw_message": text
                        }
                        self.df.loc[len(self.df)] = row
                        added += 1
                        self.last_id[gid] = max(self.last_id.get(gid, 0), msg.id)
                    if added:
                        self.new_dataframe.emit(self.df.copy())
                self.tick.emit()
                await asyncio.sleep(self.interval)
            except Exception as e:
                self.error.emit(f"Extraction loop error: {e}")
                await asyncio.sleep(self.interval)
        self.status.emit("Extractor stopped.")
