# desktop/extractor_module.py

from __future__ import annotations
from typing import Dict, Any, List, Optional
import os
import re
import json

# -------------------- Config --------------------

_OPENAI_CLIENT = None

# You can change model here if needed
_MODEL = os.getenv("EXTRACTOR_MODEL", "gpt-4o-mini")

SCHEMA_KEYS = [
    "account_number",
    "name",
    "amount",
    "currency",
    "machinery",
    "project",
    "details",
]

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


# -------------------- Public setters --------------------

def set_openai_key(key: str) -> None:
    os.environ["OPENAI_API_KEY"] = (key or "").strip()
    global _OPENAI_CLIENT
    _OPENAI_CLIENT = None


def set_model(model: str) -> None:
    global _MODEL
    _MODEL = (model or "").strip() or "gpt-4o-mini"


# -------------------- Helpers --------------------

def _normalize_digits(s: str) -> str:
    if not isinstance(s, str):
        s = str(s or "")
    return s.translate(_ARABIC_DIGITS)


def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.replace("```json", "").replace("```", "").strip()
    return s


def _parse_json_loose(txt: str) -> Optional[dict]:
    if not txt:
        return None

    try:
        return json.loads(txt)
    except Exception:
        pass

    cleaned = _strip_code_fences(txt)

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    m = _JSON_OBJECT_RE.search(cleaned)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    return None


def _coerce_schema(d: dict) -> dict:
    out = {}

    for k in SCHEMA_KEYS:
        v = d.get(k, "")

        if v is None:
            v = ""

        if k in ("account_number", "amount"):
            v = _normalize_digits(str(v))
        else:
            v = str(v)

        out[k] = v.strip()

    return out


def _empty_schema() -> Dict[str, Any]:
    return {k: "" for k in SCHEMA_KEYS}


# -------------------- Prompt --------------------

def _build_prompt(message_text: str) -> str:
    schema = {
        "account_number": "",
        "name": "",
        "amount": "",
        "currency": "",
        "machinery": "",
        "project": "",
        "details": "",
    }

    return f"""
You are an Arabic information extraction system.

Extract ONLY the requested structured values from the message.

Return VALID JSON ONLY.
Do not add explanation.
Do not use Markdown.
Do not copy the full message into any field.
Each field must contain only the clean extracted value.

Rules:
- account_number: account number only, digits only.
- name: person name only.
- amount: amount only, digits only if possible.
- currency: currency only, such as ريال, جنيه, دولار.
- machinery: machinery/equipment/device only.
- project: project name only.
- details: short transaction description only.
- If a value is missing, return an empty string "".
- Do not add extra keys.

Return exactly this JSON structure:
{json.dumps(schema, ensure_ascii=False)}

Message:
{message_text}
""".strip()


# -------------------- OpenAI Client --------------------

def _get_openai_client():
    global _OPENAI_CLIENT

    if _OPENAI_CLIENT is not None:
        return _OPENAI_CLIENT

    # Put your OpenAI API key here before rebuilding the exe
    key = os.getenv("OPENAI_API_KEY", "").strip()

    if not key:
        key = os.getenv("OPENAI_API_KEY", "").strip()

    if not key:
        return None

    try:
        from openai import OpenAI
        _OPENAI_CLIENT = OpenAI(api_key=key)
        return _OPENAI_CLIENT
    except Exception as e:
        print("OpenAI client error:", e)
        return None


# -------------------- LLM Extraction --------------------

def _ai_extract(message_text: str) -> Dict[str, Any]:
    client = _get_openai_client()

    if client is None:
        return {}

    try:
        prompt = _build_prompt(message_text)

        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0,
        )

        content = (resp.choices[0].message.content or "").strip()
        parsed = _parse_json_loose(content)

        if isinstance(parsed, dict):
            return _coerce_schema(parsed)

    except Exception as e:
        print("LLM extraction error:", e)

    return {}


# -------------------- Public API --------------------

def extract_fields(message_text: str) -> Dict[str, Any]:
    """
    LLM-only extraction.
    No regex fallback.
    If LLM fails, return empty fields.
    """
    ai = _ai_extract(message_text)

    if ai:
        return ai

    return _empty_schema()


def extract_fields_batch(messages: List[str]) -> List[Dict[str, Any]]:
    return [extract_fields(txt or "") for txt in messages]