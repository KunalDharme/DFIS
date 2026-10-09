"""Small SQLite-backed authentication store for DFIS Pro accounts."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ITERATIONS = 240_000
SESSION_DAYS = 30


def _db_path():
    configured = os.getenv("DFIS_AUTH_DB", "").strip()
    return Path(configured) if configured else Path(__file__).with_name("dfis_auth.sqlite3")


def _connect():
    connection = sqlite3.connect(_db_path())
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with _connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at)")
        db.execute("""CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            query_label TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS history_user_created ON history(user_id, created_at DESC)")


def _password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS).hex()


def _validate(email, password, name):
    email = email.strip().lower()
    if not EMAIL.fullmatch(email):
        raise ValueError("Enter a valid email address")
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters")
    if len(password) > 128:
        raise ValueError("Password must be 128 characters or fewer")
    name = name.strip()
    if len(name) > 100:
        raise ValueError("Name must be 100 characters or fewer")
    return email, name


def create_user(email, password, name=""):
    email, name = _validate(email, password, name)
    salt = secrets.token_bytes(16)
    try:
        with _connect() as db:
            cursor = db.execute(
                "INSERT INTO users (email,name,password_hash,password_salt,created_at) VALUES (?,?,?,?,?)",
                (email, name, _password_hash(password, salt), salt.hex(), int(time.time())),
            )
            return {"id": cursor.lastrowid, "email": email, "name": name}
    except sqlite3.IntegrityError as exc:
        raise ValueError("An account with this email already exists") from exc


def authenticate(email, password):
    email = email.strip().lower()
    with _connect() as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user:
        raise ValueError("Email or password is incorrect")
    expected = _password_hash(password, bytes.fromhex(user["password_salt"]))
    if not hmac.compare_digest(expected, user["password_hash"]):
        raise ValueError("Email or password is incorrect")
    return {"id": user["id"], "email": user["email"], "name": user["name"]}


def create_session(user_id):
    raw = secrets.token_urlsafe(32)
    now = int(time.time())
    with _connect() as db:
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        db.execute("INSERT INTO sessions VALUES (?,?,?,?)",
                   (hashlib.sha256(raw.encode()).hexdigest(), user_id, now + SESSION_DAYS * 86400, now))
    return raw


def get_user(raw_token):
    if not raw_token:
        return None
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    with _connect() as db:
        row = db.execute(
            """SELECT u.id,u.email,u.name FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token_hash=? AND s.expires_at>?""", (token_hash, int(time.time()))
        ).fetchone()
    return dict(row) if row else None


def delete_session(raw_token):
    if raw_token:
        with _connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(raw_token.encode()).hexdigest(),))


def change_password(user_id, current_password, new_password):
    with _connect() as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user or not hmac.compare_digest(
            _password_hash(current_password, bytes.fromhex(user["password_salt"])), user["password_hash"]
        ):
            raise ValueError("Current password is incorrect")
        if len(new_password) < 10 or len(new_password) > 128:
            raise ValueError("New password must be between 10 and 128 characters")
        salt = secrets.token_bytes(16)
        db.execute("UPDATE users SET password_hash=?, password_salt=? WHERE id=?",
                   (_password_hash(new_password, salt), salt.hex(), user_id))
        db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash!=?", (user_id, ""))


def verify_password(user_id, password):
    with _connect() as db:
        user = db.execute("SELECT password_hash,password_salt FROM users WHERE id=?", (user_id,)).fetchone()
    return bool(user and hmac.compare_digest(
        _password_hash(password, bytes.fromhex(user["password_salt"])), user["password_hash"]
    ))


def delete_user(user_id):
    with _connect() as db:
        db.execute("DELETE FROM history WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM users WHERE id=?", (user_id,))


def add_history(user_id, kind, query_label, summary):
    with _connect() as db:
        db.execute(
            "INSERT INTO history (user_id,kind,query_label,summary,created_at) VALUES (?,?,?,?,?)",
            (user_id, kind[:40], query_label[:160], summary[:240], int(time.time())),
        )


def get_history(user_id):
    with _connect() as db:
        rows = db.execute(
            "SELECT id,kind,query_label,summary,created_at FROM history WHERE user_id=? ORDER BY created_at DESC LIMIT 100",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_history(user_id):
    with _connect() as db:
        db.execute("DELETE FROM history WHERE user_id=?", (user_id,))
