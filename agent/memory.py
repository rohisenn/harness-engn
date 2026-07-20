import os
import json
import uuid
from datetime import datetime
from typing import Any

HARNESS_DIR = ".harness"
MEMORY_FILE = os.path.join(HARNESS_DIR, "memory.json")
SESSIONS_DIR = os.path.join(HARNESS_DIR, "sessions")

def ensure_harness_dirs() -> None:
    os.makedirs(SESSIONS_DIR, exist_ok=True)

def load_facts() -> list[str]:
    if not os.path.exists(MEMORY_FILE):
        return []
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("facts", [])
    except Exception:
        return []

def save_facts(facts: list[str]) -> None:
    ensure_harness_dirs()
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"facts": facts}, f, indent=2)
    except Exception:
        pass

def remember_fact(fact: str) -> str:
    if not fact or not fact.strip():
        return "Error: Fact content is empty."
    facts = load_facts()
    if fact not in facts:
        facts.append(fact)
        save_facts(facts)
        return f"Success: Fact remembered: '{fact}'"
    return f"Fact is already in memory: '{fact}'"

def forget_fact(fact: str) -> str:
    if not fact or not fact.strip():
        return "Error: Query is empty."
    facts = load_facts()
    fact_stripped = fact.strip().lower()
    matched = [f for f in facts if fact_stripped in f.lower()]
    if not matched:
        return f"No matching facts found for: '{fact}'"
    
    new_facts = [f for f in facts if f not in matched]
    save_facts(new_facts)
    return f"Success: Forgot the following facts:\n" + "\n".join(f"- {m}" for m in matched)

def generate_session_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:6]
    return f"session_{timestamp}_{uid}"

def list_sessions() -> list[dict[str, Any]]:
    if not os.path.exists(SESSIONS_DIR):
        return []
    sessions = []
    for fname in os.listdir(SESSIONS_DIR):
        if fname.endswith(".json"):
            fpath = os.path.join(SESSIONS_DIR, fname)
            try:
                mtime = os.path.getmtime(fpath)
                with open(fpath, "r", encoding="utf-8") as f:
                    messages = json.load(f)
                
                dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                preview = "No messages"
                for msg in messages:
                    if msg.get("role") == "user":
                        preview = msg.get("content", "")[:60]
                        break
                sessions.append({
                    "id": fname[:-5],
                    "timestamp": dt,
                    "preview": preview,
                    "mtime": mtime
                })
            except Exception:
                continue
    # Sort sessions by most recently modified
    sessions.sort(key=lambda s: s["mtime"], reverse=True)
    return sessions

def load_session(session_id: str) -> list[dict[str, str]]:
    fpath = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(fpath):
        raise FileNotFoundError(f"Session {session_id} not found.")
    with open(fpath, "r", encoding="utf-8") as f:
        return json.load(f)

def save_session(session_id: str, messages: list[dict[str, str]]) -> None:
    ensure_harness_dirs()
    fpath = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2)
