import json
from pathlib import Path

CFG_FILE = Path.home() / ".telegram_extractor" / "config.json"

def load_config() -> dict:
    if CFG_FILE.exists():
        return json.loads(CFG_FILE.read_text(encoding="utf-8"))
    return {}

def save_config(cfg: dict):
    CFG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CFG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
