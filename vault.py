"""Manual API key vault: store labeled keys, manually activate one at a time.

No rotation, no failover, no automated switching — a human clicks Activate.
Values are encrypted at rest with a locally-held Fernet key (SHAD_VAULT_SECRET,
never checked into git) and only ever decrypted server-side to write ACTIVE_*
into the env file, never echoed back to the browser after creation.
"""
import os
import sqlite3
import time
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

DB_PATH = Path(os.environ.get("SHAD_DB_PATH", "/data/shad.db"))
ENV_PATH = Path(os.environ.get("SHAD_ACTIVE_ENV_PATH", "/data/active.env"))

_secret = os.environ.get("SHAD_VAULT_SECRET")
if not _secret:
    raise RuntimeError("SHAD_VAULT_SECRET is not set — refusing to start without an encryption key")
_fernet = Fernet(_secret.encode())


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute(
        """CREATE TABLE IF NOT EXISTS keys (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            label TEXT NOT NULL,
            value_enc BLOB NOT NULL,
            tail TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        )"""
    )
    return c


def list_keys(provider: str = "elevenlabs"):
    with _conn() as c:
        rows = c.execute(
            "SELECT id, label, tail, active, created_at FROM keys WHERE provider=? ORDER BY created_at",
            (provider,),
        ).fetchall()
    return [
        {"id": r[0], "label": r[1], "tail": r[2], "active": bool(r[3]), "created_at": r[4]}
        for r in rows
    ]


def add_key(provider: str, label: str, value: str) -> str:
    kid = uuid.uuid4().hex[:12]
    enc = _fernet.encrypt(value.encode())
    tail = value[-4:] if len(value) >= 4 else value
    with _conn() as c:
        c.execute(
            "INSERT INTO keys (id, provider, label, value_enc, tail, active, created_at) VALUES (?,?,?,?,?,0,?)",
            (kid, provider, label, enc, tail, time.time()),
        )
    return kid


def edit_key(kid: str, label: str | None = None, value: str | None = None):
    with _conn() as c:
        if label is not None:
            c.execute("UPDATE keys SET label=? WHERE id=?", (label, kid))
        if value is not None:
            enc = _fernet.encrypt(value.encode())
            tail = value[-4:] if len(value) >= 4 else value
            c.execute("UPDATE keys SET value_enc=?, tail=? WHERE id=?", (enc, tail, kid))


def delete_key(kid: str):
    with _conn() as c:
        row = c.execute("SELECT active, provider FROM keys WHERE id=?", (kid,)).fetchone()
        c.execute("DELETE FROM keys WHERE id=?", (kid,))
        if row and row[0]:
            _write_active_env(row[1], None)


def activate_key(kid: str) -> dict:
    with _conn() as c:
        row = c.execute("SELECT provider, label, value_enc FROM keys WHERE id=?", (kid,)).fetchone()
        if not row:
            raise KeyError(kid)
        provider, label, value_enc = row
        c.execute("UPDATE keys SET active=0 WHERE provider=?", (provider,))
        c.execute("UPDATE keys SET active=1 WHERE id=?", (kid,))
    value = _fernet.decrypt(value_enc).decode()
    _write_active_env(provider, value)
    os.environ[_env_var_name(provider)] = value
    return {"id": kid, "provider": provider, "label": label}


def get_active_value(provider: str = "elevenlabs") -> str | None:
    with _conn() as c:
        row = c.execute(
            "SELECT value_enc FROM keys WHERE provider=? AND active=1", (provider,)
        ).fetchone()
    return _fernet.decrypt(row[0]).decode() if row else None


def _env_var_name(provider: str) -> str:
    return f"ACTIVE_{provider.upper()}_API_KEY"


def _write_active_env(provider: str, value: str | None):
    """Rewrite the one line for this provider in the active-keys env file."""
    var = _env_var_name(provider)
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if ENV_PATH.exists():
        lines = [l for l in ENV_PATH.read_text().splitlines() if not l.startswith(f"{var}=")]
    if value is not None:
        lines.append(f"{var}={value}")
    ENV_PATH.write_text("\n".join(lines) + ("\n" if lines else ""))
