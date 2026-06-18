import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Union

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession

from listener_worker import start_user_listener

# ---------- Persistence ----------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = DATA_DIR / "database.json"

LISTENERS: Dict[str, asyncio.Task] = {}
PENDING: Dict[str, TelegramClient] = {}


def load_db() -> dict:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_db(data: dict):
    tmp = DB_FILE.with_suffix(DB_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(DB_FILE)


class SessionInitRequest(BaseModel):
    phone: str
    api_id: str
    api_hash: str


class SessionCompleteRequest(BaseModel):
    phone: str
    code: str


class StartRequest(BaseModel):
    phone: str
    groups: List[Union[int, str]]


async def restore_saved_listeners():
    db = load_db()
    for phone, conf in db.items():
        try:
            session_string = conf.get("session_string")
            api_id = conf.get("api_id")
            api_hash = conf.get("api_hash")
            groups = conf.get("groups", [])

            if not (session_string and api_id and api_hash and groups):
                continue

            if phone in LISTENERS and not LISTENERS[phone].done():
                continue

            task = asyncio.create_task(
                start_user_listener(
                    phone=phone,
                    api_id=int(api_id),
                    api_hash=str(api_hash),
                    session_string=str(session_string),
                    groups=groups,
                )
            )
            LISTENERS[phone] = task
            print(f"[startup] Restored listener for {phone}", flush=True)

        except Exception as e:
            print(f"[startup] Failed restoring listener for {phone}: {e}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await restore_saved_listeners()
    yield
    for phone, task in list(LISTENERS.items()):
        if task and not task.done():
            task.cancel()


app = FastAPI(title="Telegram Listener Service", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "data_dir": str(DATA_DIR),
        "running_listeners": list(LISTENERS.keys()),
    }


@app.post("/session/init")
async def session_init(req: SessionInitRequest):
    if not req.phone or not req.api_id or not req.api_hash:
        raise HTTPException(400, "phone, api_id, api_hash are required")

    if req.phone in PENDING:
        try:
            await PENDING[req.phone].disconnect()
        except Exception:
            pass
        PENDING.pop(req.phone, None)

    client = TelegramClient(StringSession(), int(req.api_id), req.api_hash)
    await client.connect()
    try:
        await client.send_code_request(req.phone)
    except Exception as e:
        await client.disconnect()
        raise HTTPException(400, f"Failed to send code: {e}")

    PENDING[req.phone] = client

    db = load_db()
    db.setdefault(req.phone, {})
    db[req.phone]["api_id"] = req.api_id
    db[req.phone]["api_hash"] = req.api_hash
    save_db(db)

    return {"status": "code_sent"}


@app.post("/session/complete")
async def session_complete(req: SessionCompleteRequest):
    client = PENDING.get(req.phone)
    if client is None:
        raise HTTPException(400, "No pending session. Call /session/init first.")

    try:
        await client.sign_in(req.phone, req.code.strip())
    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        PENDING.pop(req.phone, None)
        raise HTTPException(400, f"Sign-in failed: {e}")

    session_string = StringSession.save(client.session)
    await client.disconnect()
    PENDING.pop(req.phone, None)

    db = load_db()
    db.setdefault(req.phone, {})
    db[req.phone]["session_string"] = session_string
    save_db(db)

    return {"status": "ok"}


@app.get("/session/status/{phone}")
def session_status(phone: str):
    db = load_db()
    item = db.get(phone)
    has_session = bool(item and item.get("session_string"))
    return {"has_session": has_session}


@app.post("/session/logout/{phone}")
async def session_logout(phone: str):
    db = load_db()
    if phone in db:
        db[phone].pop("session_string", None)
        db[phone]["groups"] = []
        save_db(db)

    task = LISTENERS.pop(phone, None)
    if task and not task.done():
        task.cancel()

    return {"status": "cleared"}


@app.post("/start_listener")
async def start_listener(req: StartRequest):
    db = load_db()
    conf = db.get(req.phone)
    if not conf or not conf.get("session_string"):
        raise HTTPException(400, "No server session. Complete /session/init and /session/complete first.")

    norm_groups: List[int] = []
    for g in (req.groups or []):
        try:
            norm_groups.append(int(g))
        except Exception:
            pass

    prior_groups = conf.get("groups", [])
    conf["groups"] = norm_groups
    db[req.phone] = conf
    save_db(db)

    t = LISTENERS.get(req.phone)
    if t and not t.done() and not t.cancelled() and prior_groups == norm_groups:
        return {"status": "already_running"}

    if t and not t.done() and not t.cancelled():
        t.cancel()
        try:
            await asyncio.wait_for(t, timeout=5)
        except Exception:
            pass

    task = asyncio.create_task(
        start_user_listener(
            phone=req.phone,
            api_id=int(conf["api_id"]),
            api_hash=str(conf["api_hash"]),
            session_string=str(conf["session_string"]),
            groups=norm_groups,
        )
    )
    LISTENERS[req.phone] = task
    return {"status": "started"}


@app.post("/stop_listener/{phone}")
async def stop_listener(phone: str):
    t = LISTENERS.pop(phone, None)
    if not t:
        return {"status": "not_running"}
    if not t.done() and not t.cancelled():
        t.cancel()
        try:
            await asyncio.wait_for(t, timeout=5)
        except Exception:
            pass
    return {"status": "stopped"}


@app.get("/get_data/{phone}")
def get_data(phone: str):
    data_file = DATA_DIR / f"data_{phone}.json"
    if not data_file.exists():
        return []
    try:
        return json.loads(data_file.read_text(encoding="utf-8"))
    except Exception:
        return []