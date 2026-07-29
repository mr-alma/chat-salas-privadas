import colorsys
import datetime
import functools
import hashlib
import os
import random
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
import uuid

from flask import Flask, jsonify, render_template, request, send_from_directory, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.environ.get("CHAT_DATA_DIR", BASE_DIR))
DB_PATH = os.path.abspath(
    os.environ.get("CHAT_DB_PATH", os.path.join(DATA_DIR, "chat.db"))
)
UPLOAD_FOLDER = os.path.abspath(
    os.environ.get("CHAT_UPLOAD_FOLDER", os.path.join(DATA_DIR, "uploads"))
)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MAX_CONTENT_LENGTH = 50 * 1024 * 1024
TYPING_TTL_SECONDS = 4
ONLINE_TTL_SECONDS = 12
SESSION_ACCESS_SECONDS = 12 * 60 * 60
REMEMBER_ACCESS_SECONDS = 30 * 24 * 60 * 60
ACCESS_ATTEMPT_WINDOW = 10 * 60
MAX_ACCESS_ATTEMPTS = 5
DEVICE_COOKIE = "chat_device"
DEVICE_COOKIE_SECONDS = 365 * 24 * 60 * 60
ROLE_ORDER = {
    "guest": 0,
    "participant": 1,
    "moderator": 2,
    "admin": 3,
}
ROLE_LABELS = {
    "guest": "Invitado",
    "participant": "Participante",
    "moderator": "Moderador",
    "admin": "Admin",
}
MEDIA_MESSAGE_TYPES = ("image", "video", "audio", "file")

ALLOWED_EXT = {
    "image": {"png", "jpg", "jpeg", "gif", "webp"},
    "video": {"mp4", "mov", "webm", "avi", "mkv"},
    "audio": {"mp3", "wav", "ogg", "m4a", "aac", "webm"},
}
REPLY_LABELS = {
    "image": "📷 Imagen",
    "audio": "🎤 Nota de voz",
    "video": "🎬 Video",
    "file": "📎 Archivo",
}
SLUG_RE = re.compile(r"^[a-z0-9_-]{4,32}$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
# Ngrok termina HTTPS antes de reenviar la petición. ProxyFix permite marcar
# como Secure las cookies cuando el navegador realmente está usando HTTPS.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


# ---------------------------------------------------------------------------
# Base de datos y migraciones
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout = 8000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            access_type TEXT NOT NULL DEFAULT 'public',
            access_hash TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    room_cols = {row[1] for row in conn.execute("PRAGMA table_info(rooms)").fetchall()}
    room_columns = {
        "approval_required": "INTEGER NOT NULL DEFAULT 0",
        "pinned_message_id": "INTEGER",
    }
    for col, coltype in room_columns.items():
        if col not in room_cols:
            conn.execute(f"ALTER TABLE rooms ADD COLUMN {col} {coltype}")
    conn.execute(
        """INSERT OR IGNORE INTO rooms
           (id, slug, name, access_type, access_hash, created_at)
           VALUES (1, 'general', 'Sala general', 'public', NULL, ?)""",
        (datetime.datetime.now(datetime.timezone.utc).isoformat(),),
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL DEFAULT 1,
            name TEXT NOT NULL,
            text TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
    new_columns = {
        "room_id": "INTEGER NOT NULL DEFAULT 1",
        "author_member_id": "INTEGER",
        "type": "TEXT NOT NULL DEFAULT 'text'",
        "file_url": "TEXT",
        "file_name": "TEXT",
        "reply_to_id": "INTEGER",
        "reply_to_name": "TEXT",
        "reply_to_text": "TEXT",
        "deleted_by_member_id": "INTEGER",
        "deleted_at": "TEXT",
        "deleted_original_text": "TEXT",
        "deleted_original_type": "TEXT",
        "deleted_original_file_url": "TEXT",
        "deleted_original_file_name": "TEXT",
        "client_message_id": "TEXT",
    }
    for col, coltype in new_columns.items():
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE messages ADD COLUMN {col} {coltype}")

    conn.execute(
        """CREATE TABLE IF NOT EXISTS reactions (
            message_id INTEGER,
            name TEXT,
            emoji TEXT,
            PRIMARY KEY(message_id, name, emoji)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS room_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            device_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'participant',
            status TEXT NOT NULL DEFAULT 'approved',
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(room_id, device_hash),
            FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE
        )"""
    )
    member_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(room_members)").fetchall()
    }
    member_columns = {
        "approved_by_member_id": "INTEGER",
        "approved_by_name": "TEXT",
        "approved_by_role": "TEXT",
        "welcome_pending": "INTEGER NOT NULL DEFAULT 0",
        "profile_photo_url": "TEXT",
        "profile_banner_url": "TEXT",
        "bio": "TEXT NOT NULL DEFAULT ''",
    }
    for col, coltype in member_columns.items():
        if col not in member_cols:
            conn.execute(f"ALTER TABLE room_members ADD COLUMN {col} {coltype}")
    conn.execute("UPDATE room_members SET role = 'admin' WHERE role = 'owner'")
    conn.execute("UPDATE room_members SET role = 'participant' WHERE role = 'member'")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS reads (
            message_id INTEGER,
            name TEXT,
            PRIMARY KEY(message_id, name)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS expulsion_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            requester_member_id INTEGER NOT NULL,
            target_member_id INTEGER NOT NULL,
            requester_name TEXT NOT NULL,
            requester_role TEXT NOT NULL,
            target_name TEXT NOT NULL,
            target_role TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by_member_id INTEGER,
            decided_by_name TEXT,
            FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE,
            FOREIGN KEY(requester_member_id) REFERENCES room_members(id),
            FOREIGN KEY(target_member_id) REFERENCES room_members(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS direct_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            member_low_id INTEGER NOT NULL,
            member_high_id INTEGER NOT NULL,
            requested_by_member_id INTEGER NOT NULL,
            requested_to_member_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            responded_at TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(room_id, member_low_id, member_high_id),
            CHECK(member_low_id < member_high_id),
            FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE,
            FOREIGN KEY(member_low_id) REFERENCES room_members(id),
            FOREIGN KEY(member_high_id) REFERENCES room_members(id),
            FOREIGN KEY(requested_by_member_id) REFERENCES room_members(id),
            FOREIGN KEY(requested_to_member_id) REFERENCES room_members(id)
        )"""
    )
    direct_chat_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(direct_chats)").fetchall()
    }
    direct_chat_columns = {
        "pinned_message_id": "INTEGER",
        "version": "INTEGER NOT NULL DEFAULT 0",
    }
    for col, coltype in direct_chat_columns.items():
        if col not in direct_chat_cols:
            conn.execute(f"ALTER TABLE direct_chats ADD COLUMN {col} {coltype}")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS direct_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            author_member_id INTEGER NOT NULL,
            text TEXT,
            type TEXT NOT NULL DEFAULT 'text',
            file_url TEXT,
            file_name TEXT,
            client_message_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(chat_id) REFERENCES direct_chats(id) ON DELETE CASCADE,
            FOREIGN KEY(author_member_id) REFERENCES room_members(id),
            UNIQUE(chat_id, author_member_id, client_message_id)
        )"""
    )
    direct_message_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(direct_messages)").fetchall()
    }
    direct_message_columns = {
        "edited_at": "TEXT",
        "deleted_at": "TEXT",
        "deleted_by_member_id": "INTEGER",
        "delivered_at": "TEXT",
        "read_at": "TEXT",
        "reply_to_id": "INTEGER",
        "reply_to_name": "TEXT",
        "reply_to_text": "TEXT",
    }
    for col, coltype in direct_message_columns.items():
        if col not in direct_message_cols:
            conn.execute(f"ALTER TABLE direct_messages ADD COLUMN {col} {coltype}")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS direct_message_hides (
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(message_id, member_id),
            FOREIGN KEY(chat_id) REFERENCES direct_chats(id) ON DELETE CASCADE,
            FOREIGN KEY(message_id) REFERENCES direct_messages(id) ON DELETE CASCADE,
            FOREIGN KEY(member_id) REFERENCES room_members(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS direct_reactions (
            message_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(message_id, member_id, emoji),
            FOREIGN KEY(message_id) REFERENCES direct_messages(id) ON DELETE CASCADE,
            FOREIGN KEY(member_id) REFERENCES room_members(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS direct_stars (
            message_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(message_id, member_id),
            FOREIGN KEY(message_id) REFERENCES direct_messages(id) ON DELETE CASCADE,
            FOREIGN KEY(member_id) REFERENCES room_members(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS direct_reads (
            chat_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            last_read_message_id INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(chat_id, member_id),
            FOREIGN KEY(chat_id) REFERENCES direct_chats(id) ON DELETE CASCADE,
            FOREIGN KEY(member_id) REFERENCES room_members(id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS room_state (
            room_id INTEGER PRIMARY KEY,
            version INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS room_tokens (
            token_hash TEXT PRIMARY KEY,
            room_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE
        )"""
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_colors (name TEXT PRIMARY KEY, color TEXT NOT NULL UNIQUE)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_room_id ON messages(room_id, id)")
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_client_id
           ON messages(room_id, author_member_id, client_message_id)
           WHERE client_message_id IS NOT NULL"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_room_tokens_room_id ON room_tokens(room_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_room_members_room_id ON room_members(room_id, status)")
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_expulsion_target
           ON expulsion_requests(room_id, target_member_id)
           WHERE status = 'pending'"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_expulsion_requests_room_status
           ON expulsion_requests(room_id, status, created_at)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_direct_chats_members
           ON direct_chats(member_low_id, member_high_id, status)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_direct_messages_chat
           ON direct_messages(chat_id, id)"""
    )
    conn.execute("INSERT OR IGNORE INTO room_state (room_id, version) SELECT id, 0 FROM rooms")
    conn.commit()
    conn.close()


def get_room(slug):
    if not slug or not SLUG_RE.fullmatch(slug):
        return None
    conn = get_db()
    room = conn.execute("SELECT * FROM rooms WHERE slug = ?", (slug,)).fetchone()
    conn.close()
    return room


def generate_room_slug(conn):
    for _ in range(20):
        slug = secrets.token_urlsafe(6).lower().replace("_", "a").replace("-", "b")
        exists = conn.execute("SELECT 1 FROM rooms WHERE slug = ?", (slug,)).fetchone()
        if not exists:
            return slug
    raise RuntimeError("No se pudo generar un identificador de sala")


# ---------------------------------------------------------------------------
# Acceso a salas
# ---------------------------------------------------------------------------

_attempt_lock = threading.Lock()
_access_attempts = {}


def cookie_name(room):
    return f"room_access_{room['slug']}"


def token_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def current_device_hash():
    token = request.cookies.get(DEVICE_COOKIE, "")
    return token_digest(token) if token else None


def get_current_member(room, conn=None):
    device_hash = current_device_hash()
    if not device_hash:
        return None
    owns_connection = conn is None
    if owns_connection:
        conn = get_db()
    member = conn.execute(
        "SELECT * FROM room_members WHERE room_id = ? AND device_hash = ?",
        (room["id"], device_hash),
    ).fetchone()
    if owns_connection:
        conn.close()
    return member


def set_device_cookie(response, token):
    response.set_cookie(
        DEVICE_COOKIE,
        token,
        max_age=DEVICE_COOKIE_SECONDS,
        httponly=True,
        secure=request.is_secure,
        samesite="Lax",
        path="/",
    )
    return response


def member_error(member):
    if not member:
        return jsonify({"error": "Debes identificarte para entrar", "code": "membership_required"}), 403
    code = {
        "pending": "approval_pending",
        "rejected": "approval_rejected",
        "kicked": "member_kicked",
    }.get(member["status"], "membership_required")
    message = {
        "pending": "Tu solicitud aún está esperando aprobación",
        "rejected": "El administrador no aprobó tu entrada",
        "kicked": "El administrador decidió expulsarte de la sala",
    }.get(member["status"], "No tienes acceso como participante")
    return jsonify({"error": message, "code": code}), 403


def has_room_access(room):
    if not room["access_hash"]:
        return True
    token = request.cookies.get(cookie_name(room), "")
    if not token:
        return False
    now = int(time.time())
    conn = get_db()
    conn.execute("DELETE FROM room_tokens WHERE expires_at <= ?", (now,))
    row = conn.execute(
        """SELECT 1 FROM room_tokens
           WHERE token_hash = ? AND room_id = ? AND expires_at > ?""",
        (token_digest(token), room["id"], now),
    ).fetchone()
    conn.commit()
    conn.close()
    return bool(row)


def issue_room_token(response, room, remember):
    token = secrets.token_urlsafe(32)
    lifetime = REMEMBER_ACCESS_SECONDS if remember else SESSION_ACCESS_SECONDS
    expires_at = int(time.time()) + lifetime
    conn = get_db()
    conn.execute(
        """INSERT INTO room_tokens (token_hash, room_id, expires_at, created_at)
           VALUES (?, ?, ?, ?)""",
        (
            token_digest(token),
            room["id"],
            expires_at,
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    response.set_cookie(
        cookie_name(room),
        token,
        max_age=lifetime if remember else None,
        httponly=True,
        secure=request.is_secure,
        samesite="Lax",
        path="/",
    )
    return response


def attempt_key(room):
    forwarded = request.headers.get("X-Forwarded-For", "")
    remote = forwarded.split(",", 1)[0].strip() if forwarded else request.remote_addr
    return room["id"], remote or "unknown"


def access_rate_limit(room):
    now = time.time()
    key = attempt_key(room)
    with _attempt_lock:
        attempts = [value for value in _access_attempts.get(key, []) if now - value < ACCESS_ATTEMPT_WINDOW]
        _access_attempts[key] = attempts
        if len(attempts) >= MAX_ACCESS_ATTEMPTS:
            retry_after = max(1, int(ACCESS_ATTEMPT_WINDOW - (now - attempts[0])))
            return retry_after
    return 0


def register_failed_attempt(room):
    with _attempt_lock:
        _access_attempts.setdefault(attempt_key(room), []).append(time.time())


def clear_failed_attempts(room):
    with _attempt_lock:
        _access_attempts.pop(attempt_key(room), None)


def require_room_access(view):
    @functools.wraps(view)
    def wrapped(room_slug, *args, **kwargs):
        room = get_room(room_slug)
        if not room:
            return jsonify({"error": "La sala no existe", "code": "room_not_found"}), 404
        if not has_room_access(room):
            return (
                jsonify({"error": "Debes desbloquear la sala", "code": "room_access_required"}),
                401,
            )
        member = get_current_member(room)
        if not member or member["status"] != "approved":
            return member_error(member)
        return view(room, member, *args, **kwargs)

    return wrapped


def current_device_members(conn):
    device_hash = current_device_hash()
    if not device_hash:
        return []
    return conn.execute(
        """SELECT member.*, room.slug AS room_slug, room.name AS room_name
           FROM room_members AS member
           JOIN rooms AS room ON room.id = member.room_id
           WHERE member.device_hash = ?
             AND member.status = 'approved'
             AND member.role != 'guest'""",
        (device_hash,),
    ).fetchall()


def get_direct_chat_context(chat_id, conn):
    chat = conn.execute(
        """SELECT direct_chat.*, room.slug AS room_slug, room.name AS room_name
           FROM direct_chats AS direct_chat
           JOIN rooms AS room ON room.id = direct_chat.room_id
           WHERE direct_chat.id = ?""",
        (chat_id,),
    ).fetchone()
    if not chat or chat["status"] != "accepted":
        return None
    device_hash = current_device_hash()
    if not device_hash:
        return None
    me = conn.execute(
        """SELECT * FROM room_members
           WHERE id IN (?, ?)
             AND device_hash = ?
             AND status = 'approved'
             AND role != 'guest'""",
        (chat["member_low_id"], chat["member_high_id"], device_hash),
    ).fetchone()
    if not me:
        return None
    other_id = (
        chat["member_high_id"]
        if me["id"] == chat["member_low_id"]
        else chat["member_low_id"]
    )
    other = conn.execute(
        """SELECT * FROM room_members
           WHERE id = ? AND status = 'approved' AND role != 'guest'""",
        (other_id,),
    ).fetchone()
    if not other:
        return None
    return chat, me, other


def require_direct_chat(view):
    @functools.wraps(view)
    def wrapped(chat_id, *args, **kwargs):
        conn = get_db()
        context = get_direct_chat_context(chat_id, conn)
        conn.close()
        if not context:
            return jsonify(
                {
                    "error": "Este chat privado no está disponible",
                    "code": "direct_chat_unavailable",
                }
            ), 403
        chat, me, other = context
        return view(chat, me, other, *args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# Estado efímero y utilidades del chat
# ---------------------------------------------------------------------------

_presence_lock = threading.Lock()
_typing_users = {}
_online_users = {}


def set_typing(room_id, name, is_typing):
    if not name:
        return
    key = (room_id, name)
    with _presence_lock:
        if is_typing:
            _typing_users[key] = time.time()
        else:
            _typing_users.pop(key, None)


def touch_user(room_id, name):
    if name:
        with _presence_lock:
            _online_users[(room_id, name)] = time.time()


def get_online_users(room_id, exclude_name=""):
    now = time.time()
    with _presence_lock:
        for key, seen in list(_online_users.items()):
            if now - seen > ONLINE_TTL_SECONDS:
                _online_users.pop(key, None)
        return [
            name
            for (current_room_id, name) in _online_users
            if current_room_id == room_id and name != exclude_name
        ]


def get_typing_names(room_id, exclude_name=""):
    now = time.time()
    with _presence_lock:
        for key, seen in list(_typing_users.items()):
            if now - seen > TYPING_TTL_SECONDS:
                _typing_users.pop(key, None)
        return [
            name
            for (current_room_id, name) in _typing_users
            if current_room_id == room_id and name != exclude_name
        ]


def clean_display_name(value):
    return " ".join((value or "").strip().split())[:40]


def display_name_in_use(conn, room_id, display_name, exclude_id=-1):
    wanted = unicodedata.normalize("NFKC", display_name).casefold()
    rows = conn.execute(
        """SELECT id, display_name FROM room_members
           WHERE room_id = ? AND status IN ('approved', 'pending') AND id != ?""",
        (room_id, exclude_id),
    ).fetchall()
    return any(
        unicodedata.normalize("NFKC", row["display_name"]).casefold() == wanted
        for row in rows
    )


def role_label(role):
    return ROLE_LABELS.get(role, "Participante")


def member_payload(member):
    payload = {
        "id": member["id"],
        "name": member["display_name"],
        "role": member["role"],
        "role_label": role_label(member["role"]),
        "status": member["status"],
        "photo_url": member["profile_photo_url"] if "profile_photo_url" in member.keys() else None,
        "banner_url": member["profile_banner_url"] if "profile_banner_url" in member.keys() else None,
        "bio": member["bio"] if "bio" in member.keys() else "",
    }
    if (
        member["status"] == "approved"
        and "welcome_pending" in member.keys()
        and member["welcome_pending"]
    ):
        payload["welcome"] = {
            "approved_by_name": member["approved_by_name"],
            "approved_by_role": member["approved_by_role"] or "admin",
            "approved_by_role_label": role_label(member["approved_by_role"] or "admin"),
            "assigned_role": member["role"],
            "assigned_role_label": role_label(member["role"]),
        }
    return payload


def direct_member_payload(member):
    """Expose equal peer permissions inside a two-person private chat."""
    return {
        "id": member["id"],
        "name": member["display_name"],
        "role": "participant",
        "role_label": "Participante",
        "status": member["status"],
        "photo_url": member["profile_photo_url"] if "profile_photo_url" in member.keys() else None,
        "banner_url": member["profile_banner_url"] if "profile_banner_url" in member.keys() else None,
        "bio": member["bio"] if "bio" in member.keys() else "",
    }


def bump_direct_version(conn, chat_id):
    conn.execute(
        "UPDATE direct_chats SET version = version + 1, updated_at = ? WHERE id = ?",
        (datetime.datetime.now(datetime.timezone.utc).isoformat(), chat_id),
    )


def bump_member_direct_versions(conn, member_id):
    """Refresh every accepted private chat that displays this room profile."""
    conn.execute(
        """UPDATE direct_chats
           SET version = version + 1, updated_at = ?
           WHERE status = 'accepted'
             AND (member_low_id = ? OR member_high_id = ?)""",
        (
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
            member_id,
            member_id,
        ),
    )


def direct_message_payload(conn, row, viewer_member_id):
    message = dict(row)
    if row["reply_to_id"]:
        reply_author = conn.execute(
            """SELECT author.display_name
               FROM direct_messages AS replied
               JOIN room_members AS author ON author.id = replied.author_member_id
               WHERE replied.id = ? AND replied.chat_id = ?""",
            (row["reply_to_id"], row["chat_id"]),
        ).fetchone()
        if reply_author:
            message["reply_to_name"] = reply_author["display_name"]
    reactions = conn.execute(
        """SELECT reaction.emoji, member.id AS member_id,
                  member.display_name AS name
           FROM direct_reactions AS reaction
           JOIN room_members AS member ON member.id = reaction.member_id
           WHERE reaction.message_id = ?
           ORDER BY reaction.created_at""",
        (row["id"],),
    ).fetchall()
    message["reactions"] = [dict(item) for item in reactions]
    message["starred"] = bool(
        conn.execute(
            """SELECT 1 FROM direct_stars
               WHERE message_id = ? AND member_id = ?""",
            (row["id"], viewer_member_id),
        ).fetchone()
    )
    if row["author_member_id"] == viewer_member_id:
        message["delivery_status"] = (
            "seen"
            if row["read_at"]
            else "delivered"
            if row["delivered_at"]
            else "sent"
        )
    else:
        message["delivery_status"] = None
    message["author_role"] = "participant"
    message["author_role_label"] = "Participante"
    return message


def requested_media_type():
    media_type = (request.args.get("type") or "all").strip().lower()
    return media_type if media_type in {"all", *MEDIA_MESSAGE_TYPES} else None


def media_page_args():
    limit = min(max(request.args.get("limit", 80, type=int), 1), 200)
    before_id = max(request.args.get("before_id", 0, type=int), 0)
    return limit, before_id


def media_counts(conn, table, owner_column, owner_id):
    counts = {kind: 0 for kind in MEDIA_MESSAGE_TYPES}
    for row in conn.execute(
        f"""SELECT type, COUNT(*) AS total
            FROM {table}
            WHERE {owner_column} = ?
              AND type IN ('image', 'video', 'audio', 'file')
              AND file_url IS NOT NULL
            GROUP BY type""",
        (owner_id,),
    ).fetchall():
        counts[row["type"]] = row["total"]
    counts["all"] = sum(counts.values())
    return counts


def guest_write_error(member):
    if member["role"] == "guest":
        return (
            jsonify(
                {
                    "error": "El modo Invitado es de solo lectura",
                    "code": "read_only_role",
                }
            ),
            403,
        )
    return None


def classify_ext(filename, kind_hint=None):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if kind_hint in ALLOWED_EXT or kind_hint == "file":
        return kind_hint, ext
    for kind, extensions in ALLOWED_EXT.items():
        if ext in extensions:
            return kind, ext
    return "file", ext


def bump_version(conn, room_id):
    conn.execute("UPDATE room_state SET version = version + 1 WHERE room_id = ?", (room_id,))


def insert_system_message(conn, room_id, text):
    conn.execute(
        """INSERT INTO messages
           (room_id, author_member_id, name, text, type, created_at)
           VALUES (?, NULL, 'Sistema', ?, 'system', ?)""",
        (
            room_id,
            text[:300],
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ),
    )
    bump_version(conn, room_id)


def user_color(conn, name):
    row = conn.execute("SELECT color FROM user_colors WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    while True:
        red, green, blue = colorsys.hsv_to_rgb(random.random(), 0.62, 0.76)
        color = "#{:02x}{:02x}{:02x}".format(
            int(red * 255), int(green * 255), int(blue * 255)
        )
        conn.execute(
            "INSERT OR IGNORE INTO user_colors (name, color) VALUES (?, ?)",
            (name, color),
        )
        row = conn.execute(
            "SELECT color FROM user_colors WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row[0]


# ---------------------------------------------------------------------------
# Páginas y administración de salas
# ---------------------------------------------------------------------------

@app.route("/")
def lobby():
    return render_template("lobby.html")


@app.route("/room/<room_slug>")
def room_page(room_slug):
    room = get_room(room_slug)
    if not room:
        return render_template("room_not_found.html"), 404
    return render_template("index.html", room=room)


@app.route("/direct/<int:chat_id>")
def direct_chat_page(chat_id):
    conn = get_db()
    context = get_direct_chat_context(chat_id, conn)
    conn.close()
    if not context:
        return render_template("room_not_found.html"), 404
    chat, me, other = context
    return render_template(
        "direct.html",
        direct_chat=chat,
        current_member=me,
        other_member=other,
    )


@app.route("/api/rooms", methods=["POST"])
def create_room():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    access_type = data.get("access_type") or "public"
    secret = str(data.get("secret") or "")
    approval_required = bool(data.get("approval_required"))

    if not name or len(name) > 60:
        return jsonify({"error": "Escribe un nombre de sala de hasta 60 caracteres"}), 400
    if access_type not in {"public", "password", "code"}:
        return jsonify({"error": "El tipo de acceso no es válido"}), 400
    if access_type == "password" and not 6 <= len(secret) <= 128:
        return jsonify({"error": "La contraseña debe tener entre 6 y 128 caracteres"}), 400
    if access_type == "code" and not re.fullmatch(r"\d{6}", secret):
        return jsonify({"error": "El código debe tener exactamente 6 dígitos"}), 400

    access_hash = generate_password_hash(secret) if access_type != "public" else None
    conn = get_db()
    slug = generate_room_slug(conn)
    cursor = conn.execute(
        """INSERT INTO rooms
           (slug, name, access_type, access_hash, approval_required, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            slug,
            name,
            access_type,
            access_hash,
            int(approval_required),
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ),
    )
    room_id = cursor.lastrowid
    device_token = request.cookies.get(DEVICE_COOKIE) or secrets.token_urlsafe(32)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO room_members
           (room_id, device_hash, display_name, role, status, created_at, last_seen_at)
           VALUES (?, ?, '', 'admin', 'approved', ?, ?)""",
        (room_id, token_digest(device_token), now_iso, now_iso),
    )
    conn.execute("INSERT INTO room_state (room_id, version) VALUES (?, 0)", (room_id,))
    conn.commit()
    room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    conn.close()

    response = jsonify(
        {
            "slug": slug,
            "name": name,
            "approval_required": approval_required,
            "url": url_for("room_page", room_slug=slug, _external=True),
        }
    )
    response.status_code = 201
    set_device_cookie(response, device_token)
    if access_hash:
        issue_room_token(response, room, remember=True)
    return response


@app.route("/api/rooms/<room_slug>/config")
def room_config(room_slug):
    room = get_room(room_slug)
    if not room:
        return jsonify({"error": "La sala no existe", "code": "room_not_found"}), 404
    authorized = has_room_access(room)
    member = get_current_member(room) if authorized else None
    response = jsonify(
        {
            "name": room["name"],
            "access_type": room["access_type"],
            "approval_required": bool(room["approval_required"]),
            "requires_access": bool(room["access_hash"] and not authorized),
            "member": (
                member_payload(member)
                if member
                else None
            ),
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/rooms/<room_slug>/access", methods=["POST"])
def unlock_room(room_slug):
    room = get_room(room_slug)
    if not room:
        return jsonify({"error": "La sala no existe", "code": "room_not_found"}), 404
    if not room["access_hash"]:
        return jsonify({"ok": True})

    retry_after = access_rate_limit(room)
    if retry_after:
        response = jsonify(
            {
                "error": "Demasiados intentos. Espera unos minutos antes de volver a probar.",
                "code": "too_many_attempts",
            }
        )
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response

    data = request.get_json(silent=True) or {}
    secret = str(data.get("secret") or "")
    if not secret or not check_password_hash(room["access_hash"], secret):
        register_failed_attempt(room)
        return (
            jsonify({"error": "La contraseña o el código no es correcto", "code": "invalid_secret"}),
            401,
        )

    clear_failed_attempts(room)
    response = jsonify({"ok": True})
    return issue_room_token(response, room, remember=bool(data.get("remember")))


@app.route("/api/rooms/<room_slug>/membership", methods=["GET", "POST"])
def room_membership(room_slug):
    room = get_room(room_slug)
    if not room:
        return jsonify({"error": "La sala no existe", "code": "room_not_found"}), 404
    if not has_room_access(room):
        return jsonify({"error": "Debes desbloquear la sala", "code": "room_access_required"}), 401

    conn = get_db()
    member = get_current_member(room, conn)
    if request.method == "GET":
        payload = member_payload(member) if member else None
        conn.close()
        return jsonify({"member": payload})

    data = request.get_json(silent=True) or {}
    display_name = clean_display_name(data.get("name"))
    if not display_name:
        conn.close()
        return jsonify({"error": "Escribe el nombre que quieres mostrar"}), 400

    if member and member["status"] in {"kicked", "rejected"}:
        conn.close()
        return member_error(member)

    if (
        member
        and member["status"] == "approved"
        and member["display_name"]
        and display_name != member["display_name"]
    ):
        conn.close()
        return jsonify(
            {
                "error": "Usa la opción de cambiar nombre dentro de la sala",
                "code": "use_name_change",
            }
        ), 409

    if display_name_in_use(
        conn, room["id"], display_name, member["id"] if member else -1
    ):
        conn.close()
        return jsonify({"error": "Ese nombre ya está siendo usado en esta sala"}), 409

    device_token = request.cookies.get(DEVICE_COOKIE) or secrets.token_urlsafe(32)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if member:
        conn.execute(
            "UPDATE room_members SET display_name = ?, last_seen_at = ? WHERE id = ?",
            (display_name, now_iso, member["id"]),
        )
        member_id = member["id"]
        role = member["role"]
        status = member["status"]
    else:
        owner_exists = conn.execute(
            "SELECT 1 FROM room_members WHERE room_id = ? AND role = 'admin'",
            (room["id"],),
        ).fetchone()
        role = "participant" if owner_exists else "admin"
        status = "pending" if owner_exists and room["approval_required"] else "approved"
        cursor = conn.execute(
            """INSERT INTO room_members
               (room_id, device_hash, display_name, role, status, created_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                room["id"],
                token_digest(device_token),
                display_name,
                role,
                status,
                now_iso,
                now_iso,
            ),
        )
        member_id = cursor.lastrowid
        if status == "approved" and role == "participant":
            insert_system_message(conn, room["id"], f"{display_name} se unió a la sala")

    conn.commit()
    conn.close()
    response = jsonify(
        {
            "member": {
                "id": member_id,
                "name": display_name,
                "role": role,
                "role_label": role_label(role),
                "status": status,
            }
        }
    )
    response.status_code = 202 if status == "pending" else 200
    return set_device_cookie(response, device_token)


@app.route("/api/rooms/<room_slug>/membership/name", methods=["PATCH"])
@require_room_access
def change_display_name(room, member):
    read_only = guest_write_error(member)
    if read_only:
        return read_only
    data = request.get_json(silent=True) or {}
    display_name = clean_display_name(data.get("name"))
    if not display_name:
        return jsonify({"error": "Escribe el nombre que quieres mostrar"}), 400

    old_name = member["display_name"]
    if display_name == old_name:
        return jsonify(
            {
                "member": {
                    "id": member["id"],
                    "name": old_name,
                    "role": member["role"],
                    "status": member["status"],
                }
            }
        )

    conn = get_db()
    if display_name_in_use(conn, room["id"], display_name, member["id"]):
        conn.close()
        return jsonify({"error": "Ese nombre ya está siendo usado en esta sala"}), 409

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn.execute(
        "UPDATE room_members SET display_name = ?, last_seen_at = ? WHERE id = ?",
        (display_name, now_iso, member["id"]),
    )
    conn.execute(
        """UPDATE OR IGNORE reads SET name = ?
           WHERE name = ? AND message_id IN
             (SELECT id FROM messages WHERE room_id = ?)""",
        (display_name, old_name, room["id"]),
    )
    conn.execute(
        """DELETE FROM reads
           WHERE name = ? AND message_id IN
             (SELECT id FROM messages WHERE room_id = ?)""",
        (old_name, room["id"]),
    )
    conn.execute(
        """UPDATE OR IGNORE reactions SET name = ?
           WHERE name = ? AND message_id IN
             (SELECT id FROM messages WHERE room_id = ?)""",
        (display_name, old_name, room["id"]),
    )
    conn.execute(
        """DELETE FROM reactions
           WHERE name = ? AND message_id IN
             (SELECT id FROM messages WHERE room_id = ?)""",
        (old_name, room["id"]),
    )
    color = conn.execute(
        "SELECT color FROM user_colors WHERE name = ?", (old_name,)
    ).fetchone()
    if color:
        conn.execute(
            "INSERT OR IGNORE INTO user_colors (name, color) VALUES (?, ?)",
            (display_name, color["color"]),
        )
    insert_system_message(
        conn,
        room["id"],
        f'"{old_name}" ha tenido una crisis de identidad y ahora es "{display_name}"',
    )
    bump_member_direct_versions(conn, member["id"])
    conn.commit()
    conn.close()

    with _presence_lock:
        online_seen = _online_users.pop((room["id"], old_name), None)
        typing_seen = _typing_users.pop((room["id"], old_name), None)
        if online_seen is not None:
            _online_users[(room["id"], display_name)] = online_seen
        if typing_seen is not None:
            _typing_users[(room["id"], display_name)] = typing_seen

    return jsonify(
        {
            "member": {
                "id": member["id"],
                "name": display_name,
                "role": member["role"],
                "role_label": role_label(member["role"]),
                "status": member["status"],
            }
        }
    )


@app.route("/api/rooms/<room_slug>/membership/welcome-seen", methods=["POST"])
@require_room_access
def mark_welcome_seen(room, member):
    conn = get_db()
    conn.execute(
        "UPDATE room_members SET welcome_pending = 0 WHERE id = ? AND room_id = ?",
        (member["id"], room["id"]),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/rooms/<room_slug>/members/<int:member_id>/profile", methods=["GET"])
@require_room_access
def get_member_profile(room, member, member_id):
    conn = get_db()
    target = conn.execute(
        """SELECT * FROM room_members
           WHERE id = ? AND room_id = ? AND status = 'approved'""",
        (member_id, room["id"]),
    ).fetchone()
    conn.close()
    if not target:
        return jsonify({"error": "Este perfil ya no está disponible"}), 404
    return jsonify({"profile": member_payload(target), "editable": target["id"] == member["id"] and member["role"] != "guest"})


@app.route("/api/rooms/<room_slug>/profile", methods=["PATCH"])
@require_room_access
def update_own_profile(room, member):
    read_only = guest_write_error(member)
    if read_only:
        return read_only
    data = request.get_json(silent=True) or {}
    bio = " ".join(str(data.get("bio") or "").strip().splitlines())[:180]
    conn = get_db()
    conn.execute(
        "UPDATE room_members SET bio = ?, last_seen_at = ? WHERE id = ? AND room_id = ?",
        (
            bio,
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
            member["id"],
            room["id"],
        ),
    )
    bump_version(conn, room["id"])
    bump_member_direct_versions(conn, member["id"])
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM room_members WHERE id = ?", (member["id"],)
    ).fetchone()
    conn.close()
    return jsonify({"profile": member_payload(updated)})


@app.route("/api/rooms/<room_slug>/profile/photo", methods=["POST"])
@require_room_access
def update_profile_photo(room, member):
    read_only = guest_write_error(member)
    if read_only:
        return read_only
    uploaded = request.files.get("photo")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Selecciona una foto"}), 400
    extension = (
        uploaded.filename.rsplit(".", 1)[-1].lower()
        if "." in uploaded.filename
        else ""
    )
    if extension not in ALLOWED_EXT["image"]:
        return jsonify({"error": "Usa una imagen PNG, JPG, GIF o WebP"}), 400
    unique_name = f"{member['id']}_{uuid.uuid4().hex}.{extension}"
    profile_folder = os.path.join(UPLOAD_FOLDER, f"profiles_{room['id']}")
    os.makedirs(profile_folder, exist_ok=True)
    uploaded.save(os.path.join(profile_folder, unique_name))
    photo_url = url_for(
        "download_profile_photo",
        room_slug=room["slug"],
        filename=unique_name,
    )
    conn = get_db()
    conn.execute(
        "UPDATE room_members SET profile_photo_url = ? WHERE id = ? AND room_id = ?",
        (photo_url, member["id"], room["id"]),
    )
    bump_version(conn, room["id"])
    bump_member_direct_versions(conn, member["id"])
    conn.commit()
    conn.close()
    return jsonify({"photo_url": photo_url})


@app.route("/api/rooms/<room_slug>/profile/banner", methods=["POST"])
@require_room_access
def update_profile_banner(room, member):
    read_only = guest_write_error(member)
    if read_only:
        return read_only
    uploaded = request.files.get("banner")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Selecciona una imagen para el banner"}), 400
    extension = (
        uploaded.filename.rsplit(".", 1)[-1].lower()
        if "." in uploaded.filename
        else ""
    )
    if extension not in ALLOWED_EXT["image"]:
        return jsonify({"error": "Usa una imagen PNG, JPG, GIF o WebP"}), 400
    unique_name = f"banner_{member['id']}_{uuid.uuid4().hex}.{extension}"
    profile_folder = os.path.join(UPLOAD_FOLDER, f"profiles_{room['id']}")
    os.makedirs(profile_folder, exist_ok=True)
    uploaded.save(os.path.join(profile_folder, unique_name))
    banner_url = url_for(
        "download_profile_photo",
        room_slug=room["slug"],
        filename=unique_name,
    )
    conn = get_db()
    conn.execute(
        "UPDATE room_members SET profile_banner_url = ? WHERE id = ? AND room_id = ?",
        (banner_url, member["id"], room["id"]),
    )
    bump_version(conn, room["id"])
    bump_member_direct_versions(conn, member["id"])
    conn.commit()
    conn.close()
    return jsonify({"banner_url": banner_url})


@app.route("/api/rooms/<room_slug>/profiles/<path:filename>")
@require_room_access
def download_profile_photo(room, member, filename):
    return send_from_directory(
        os.path.join(UPLOAD_FOLDER, f"profiles_{room['id']}"),
        filename,
    )


# ---------------------------------------------------------------------------
# Chats privados de dos personas
# ---------------------------------------------------------------------------

@app.route("/api/direct-chats", methods=["GET"])
def list_direct_chats():
    conn = get_db()
    members = current_device_members(conn)
    if not members:
        conn.close()
        return jsonify({"chats": [], "requests": []})

    member_by_id = {member["id"]: member for member in members}
    member_ids = list(member_by_id)
    placeholders = ",".join("?" for _ in member_ids)
    chats = []
    accepted_rows = conn.execute(
        f"""SELECT direct_chat.*, room.slug AS room_slug, room.name AS room_name
            FROM direct_chats AS direct_chat
            JOIN rooms AS room ON room.id = direct_chat.room_id
            WHERE direct_chat.status = 'accepted'
              AND (
                direct_chat.member_low_id IN ({placeholders})
                OR direct_chat.member_high_id IN ({placeholders})
              )
            ORDER BY direct_chat.updated_at DESC""",
        (*member_ids, *member_ids),
    ).fetchall()
    for direct_chat in accepted_rows:
        me_id = (
            direct_chat["member_low_id"]
            if direct_chat["member_low_id"] in member_by_id
            else direct_chat["member_high_id"]
        )
        other_id = (
            direct_chat["member_high_id"]
            if me_id == direct_chat["member_low_id"]
            else direct_chat["member_low_id"]
        )
        other = conn.execute(
            """SELECT * FROM room_members
               WHERE id = ? AND status = 'approved' AND role != 'guest'""",
            (other_id,),
        ).fetchone()
        if not other:
            continue
        conn.execute(
            """UPDATE direct_messages
               SET delivered_at = COALESCE(delivered_at, ?)
               WHERE chat_id = ? AND author_member_id != ? AND delivered_at IS NULL""",
            (
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
                direct_chat["id"],
                me_id,
            ),
        )
        last_message = conn.execute(
            """SELECT message.* FROM direct_messages AS message
               LEFT JOIN direct_message_hides AS hidden
                 ON hidden.message_id = message.id AND hidden.member_id = ?
               WHERE message.chat_id = ? AND hidden.message_id IS NULL
               ORDER BY message.id DESC LIMIT 1""",
            (me_id, direct_chat["id"]),
        ).fetchone()
        read_row = conn.execute(
            """SELECT last_read_message_id FROM direct_reads
               WHERE chat_id = ? AND member_id = ?""",
            (direct_chat["id"], me_id),
        ).fetchone()
        last_read = read_row["last_read_message_id"] if read_row else 0
        unread_count = conn.execute(
            """SELECT COUNT(*) FROM direct_messages AS message
               LEFT JOIN direct_message_hides AS hidden
                 ON hidden.message_id = message.id AND hidden.member_id = ?
               WHERE message.chat_id = ? AND message.id > ?
                 AND message.author_member_id != ? AND hidden.message_id IS NULL""",
            (me_id, direct_chat["id"], last_read, me_id),
        ).fetchone()[0]
        if last_message:
            preview = (
                (last_message["text"] or "")[:70]
                if last_message["type"] in {"text", "deleted"}
                else REPLY_LABELS.get(last_message["type"], "Archivo")
            )
            last_message_id = last_message["id"]
        else:
            preview = "Chat privado listo"
            last_message_id = 0
        chats.append(
            {
                "id": direct_chat["id"],
                "url": url_for("direct_chat_page", chat_id=direct_chat["id"]),
                "room_slug": direct_chat["room_slug"],
                "room_name": direct_chat["room_name"],
                "other_id": other["id"],
                "other_name": other["display_name"],
                "other_role": "participant",
                "other_role_label": "Participante",
                "other_photo_url": other["profile_photo_url"],
                "preview": preview,
                "last_message_id": last_message_id,
                "unread_count": min(unread_count, 99),
            }
        )

    incoming_requests = []
    request_rows = conn.execute(
        f"""SELECT direct_chat.*, room.name AS room_name,
                   requester.display_name AS requester_name,
                   requester.role AS requester_role
            FROM direct_chats AS direct_chat
            JOIN rooms AS room ON room.id = direct_chat.room_id
            JOIN room_members AS requester
              ON requester.id = direct_chat.requested_by_member_id
            WHERE direct_chat.status = 'pending'
              AND direct_chat.requested_to_member_id IN ({placeholders})
              AND requester.status = 'approved'
              AND requester.role != 'guest'
            ORDER BY direct_chat.created_at""",
        member_ids,
    ).fetchall()
    for direct_request in request_rows:
        incoming_requests.append(
            {
                "id": direct_request["id"],
                "requester_id": direct_request["requested_by_member_id"],
                "requester_name": direct_request["requester_name"],
                "requester_role": direct_request["requester_role"],
                "requester_role_label": role_label(direct_request["requester_role"]),
                "room_name": direct_request["room_name"],
            }
        )
    conn.commit()
    conn.close()
    return jsonify({"chats": chats, "requests": incoming_requests})


@app.route(
    "/api/rooms/<room_slug>/members/<int:member_id>/direct-request",
    methods=["POST"],
)
@require_room_access
def request_direct_chat(room, actor, member_id):
    if actor["role"] == "guest":
        return jsonify({"error": "El modo Invitado no permite iniciar chats privados"}), 403
    if actor["id"] == member_id:
        return jsonify({"error": "No puedes iniciar un chat privado contigo"}), 400
    conn = get_db()
    target = conn.execute(
        """SELECT * FROM room_members
           WHERE id = ? AND room_id = ? AND status = 'approved'""",
        (member_id, room["id"]),
    ).fetchone()
    if not target:
        conn.close()
        return jsonify({"error": "La persona ya no está disponible"}), 404
    if target["role"] == "guest":
        conn.close()
        return jsonify(
            {"error": "Un Invitado no puede participar en chats privados"}
        ), 403

    member_low_id, member_high_id = sorted((actor["id"], target["id"]))
    existing = conn.execute(
        """SELECT * FROM direct_chats
           WHERE room_id = ? AND member_low_id = ? AND member_high_id = ?""",
        (room["id"], member_low_id, member_high_id),
    ).fetchone()
    now = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now.isoformat()
    if existing and existing["status"] == "accepted":
        conn.close()
        return jsonify(
            {
                "ok": True,
                "status": "accepted",
                "chat_id": existing["id"],
                "url": url_for("direct_chat_page", chat_id=existing["id"]),
            }
        )
    if existing and existing["status"] == "pending":
        conn.close()
        if existing["requested_to_member_id"] == actor["id"]:
            return jsonify(
                {
                    "ok": True,
                    "status": "incoming_pending",
                    "request_id": existing["id"],
                    "message": "Esta persona ya te envió una solicitud. Puedes decidirla desde el icono de chats privados.",
                }
            )
        return jsonify(
            {
                "ok": True,
                "status": "pending",
                "request_id": existing["id"],
                "message": "La solicitud de chat privado sigue esperando respuesta.",
            }
        )
    if existing and existing["status"] == "rejected":
        created_at = datetime.datetime.fromisoformat(existing["created_at"])
        if now - created_at < datetime.timedelta(seconds=60):
            conn.close()
            return jsonify(
                {
                    "error": "Espera un minuto antes de volver a enviar la solicitud",
                    "code": "direct_request_cooldown",
                }
            ), 429
        conn.execute(
            """UPDATE direct_chats
               SET requested_by_member_id = ?, requested_to_member_id = ?,
                   status = 'pending', created_at = ?, responded_at = NULL,
                   updated_at = ?
               WHERE id = ?""",
            (actor["id"], target["id"], now_iso, now_iso, existing["id"]),
        )
        request_id = existing["id"]
    else:
        try:
            cursor = conn.execute(
                """INSERT INTO direct_chats
                   (room_id, member_low_id, member_high_id,
                    requested_by_member_id, requested_to_member_id,
                    status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (
                    room["id"],
                    member_low_id,
                    member_high_id,
                    actor["id"],
                    target["id"],
                    now_iso,
                    now_iso,
                ),
            )
            request_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            # Dos personas pueden pulsar la acción al mismo tiempo. La pareja
            # tiene una restricción UNIQUE; recuperamos la solicitud ganadora
            # para evitar un error 500 y mantener una única conversación.
            conn.rollback()
            concurrent = conn.execute(
                """SELECT * FROM direct_chats
                   WHERE room_id = ? AND member_low_id = ? AND member_high_id = ?""",
                (room["id"], member_low_id, member_high_id),
            ).fetchone()
            conn.close()
            if not concurrent:
                return jsonify(
                    {"error": "No se pudo crear la solicitud. Inténtalo de nuevo."}
                ), 409
            if concurrent["status"] == "accepted":
                return jsonify(
                    {
                        "ok": True,
                        "status": "accepted",
                        "chat_id": concurrent["id"],
                        "url": url_for(
                            "direct_chat_page",
                            chat_id=concurrent["id"],
                        ),
                    }
                )
            return jsonify(
                {
                    "ok": True,
                    "status": (
                        "incoming_pending"
                        if concurrent["requested_to_member_id"] == actor["id"]
                        else "pending"
                    ),
                    "request_id": concurrent["id"],
                    "message": "Ya existe una solicitud de chat privado entre ustedes.",
                }
            )
    conn.commit()
    conn.close()
    return jsonify(
        {
            "ok": True,
            "status": "pending",
            "request_id": request_id,
            "message": f"Solicitud de chat privado enviada a {target['display_name']}.",
        }
    ), 202


@app.route(
    "/api/direct-chat-requests/<int:request_id>/decision",
    methods=["POST"],
)
def decide_direct_chat_request(request_id):
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in {"accept", "reject"}:
        return jsonify({"error": "Decisión no válida"}), 400
    conn = get_db()
    members = current_device_members(conn)
    member_by_id = {member["id"]: member for member in members}
    direct_request = conn.execute(
        """SELECT * FROM direct_chats
           WHERE id = ? AND status = 'pending'""",
        (request_id,),
    ).fetchone()
    if (
        not direct_request
        or direct_request["requested_to_member_id"] not in member_by_id
    ):
        conn.close()
        return jsonify({"error": "La solicitud ya no está disponible"}), 404
    requester = conn.execute(
        """SELECT * FROM room_members
           WHERE id = ? AND status = 'approved' AND role != 'guest'""",
        (direct_request["requested_by_member_id"],),
    ).fetchone()
    if not requester:
        conn.execute(
            """UPDATE direct_chats SET status = 'rejected', responded_at = ?
               WHERE id = ?""",
            (datetime.datetime.now(datetime.timezone.utc).isoformat(), request_id),
        )
        conn.commit()
        conn.close()
        return jsonify({"error": "La persona que envió la solicitud ya no está disponible"}), 409

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if action == "reject":
        conn.execute(
            """UPDATE direct_chats
               SET status = 'rejected', responded_at = ?, updated_at = ?
               WHERE id = ?""",
            (now_iso, now_iso, request_id),
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "status": "rejected"})

    conn.execute(
        """UPDATE direct_chats
           SET status = 'accepted', responded_at = ?, updated_at = ?
           WHERE id = ?""",
        (now_iso, now_iso, request_id),
    )
    conn.execute(
        """INSERT OR IGNORE INTO direct_reads
           (chat_id, member_id, last_read_message_id)
           VALUES (?, ?, 0), (?, ?, 0)""",
        (
            request_id,
            direct_request["member_low_id"],
            request_id,
            direct_request["member_high_id"],
        ),
    )
    conn.commit()
    conn.close()
    return jsonify(
        {
            "ok": True,
            "status": "accepted",
            "chat_id": request_id,
            "url": url_for("direct_chat_page", chat_id=request_id),
        }
    )


@app.route("/api/direct-chats/<int:chat_id>/config", methods=["GET"])
@require_direct_chat
def direct_chat_config(direct_chat, member, other):
    return jsonify(
        {
            "id": direct_chat["id"],
            "room_slug": direct_chat["room_slug"],
            "room_name": direct_chat["room_name"],
            "member": direct_member_payload(member),
            "other": direct_member_payload(other),
        }
    )


@app.route("/api/direct-chats/<int:chat_id>/updates", methods=["GET"])
@require_direct_chat
def direct_chat_updates(direct_chat, member, other):
    since_id = request.args.get("since", 0, type=int)
    touch_user(direct_chat["room_id"], member["display_name"])
    conn = get_db()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn.execute(
        """UPDATE direct_messages
           SET delivered_at = COALESCE(delivered_at, ?), read_at = COALESCE(read_at, ?)
           WHERE chat_id = ? AND author_member_id != ?""",
        (now_iso, now_iso, direct_chat["id"], member["id"]),
    )
    rows = conn.execute(
        """SELECT direct_message.*, author.display_name AS author_name,
                  author.profile_photo_url AS author_photo_url
           FROM direct_messages AS direct_message
           JOIN room_members AS author
             ON author.id = direct_message.author_member_id
           LEFT JOIN direct_message_hides AS hidden
             ON hidden.message_id = direct_message.id AND hidden.member_id = ?
           WHERE direct_message.chat_id = ? AND direct_message.id > ?
             AND hidden.message_id IS NULL
           ORDER BY direct_message.id""",
        (member["id"], direct_chat["id"], since_id),
    ).fetchall()
    messages = [
        direct_message_payload(conn, row, member["id"])
        for row in rows
    ]
    latest_id = conn.execute(
        """SELECT COALESCE(MAX(id), 0) FROM direct_messages WHERE chat_id = ?""",
        (direct_chat["id"],),
    ).fetchone()[0]
    read_row = conn.execute(
        """SELECT last_read_message_id FROM direct_reads
           WHERE chat_id = ? AND member_id = ?""",
        (direct_chat["id"], member["id"]),
    ).fetchone()
    if latest_id > (read_row["last_read_message_id"] if read_row else 0):
        conn.execute(
            """INSERT INTO direct_reads (chat_id, member_id, last_read_message_id)
               VALUES (?, ?, ?)
               ON CONFLICT(chat_id, member_id)
               DO UPDATE SET last_read_message_id = excluded.last_read_message_id""",
            (direct_chat["id"], member["id"], latest_id),
        )
    receipt_rows = conn.execute(
        """SELECT id, delivered_at, read_at
           FROM direct_messages
           WHERE chat_id = ? AND author_member_id = ?""",
        (direct_chat["id"], member["id"]),
    ).fetchall()
    receipts = {
        str(item["id"]): (
            "seen" if item["read_at"] else "delivered" if item["delivered_at"] else "sent"
        )
        for item in receipt_rows
    }
    pinned = None
    current_chat = conn.execute(
        "SELECT pinned_message_id, version FROM direct_chats WHERE id = ?",
        (direct_chat["id"],),
    ).fetchone()
    if current_chat["pinned_message_id"]:
        pinned_row = conn.execute(
            """SELECT message.*, author.display_name AS author_name,
                      author.profile_photo_url AS author_photo_url
               FROM direct_messages AS message
               JOIN room_members AS author ON author.id = message.author_member_id
               LEFT JOIN direct_message_hides AS hidden
                 ON hidden.message_id = message.id AND hidden.member_id = ?
               WHERE message.id = ? AND message.chat_id = ?
                 AND message.type != 'deleted' AND hidden.message_id IS NULL""",
            (
                member["id"],
                current_chat["pinned_message_id"],
                direct_chat["id"],
            ),
        ).fetchone()
        if pinned_row:
            pinned = direct_message_payload(conn, pinned_row, member["id"])
    starred_rows = conn.execute(
        """SELECT message.*, author.display_name AS author_name,
                  author.profile_photo_url AS author_photo_url
           FROM direct_stars AS star
           JOIN direct_messages AS message ON message.id = star.message_id
           JOIN room_members AS author ON author.id = message.author_member_id
           LEFT JOIN direct_message_hides AS hidden
             ON hidden.message_id = message.id AND hidden.member_id = ?
           WHERE star.member_id = ? AND message.chat_id = ?
             AND message.type != 'deleted' AND hidden.message_id IS NULL
           ORDER BY star.created_at DESC
           LIMIT 50""",
        (member["id"], member["id"], direct_chat["id"]),
    ).fetchall()
    starred = [
        direct_message_payload(conn, row, member["id"]) for row in starred_rows
    ]
    conn.commit()
    conn.close()
    return jsonify(
        {
            "messages": messages,
            "member": direct_member_payload(member),
            "other": direct_member_payload(other),
            "receipts": receipts,
            "pinned_message": pinned,
            "starred_messages": starred,
            "version": current_chat["version"],
        }
    )


@app.route("/api/direct-chats/<int:chat_id>/media", methods=["GET"])
@require_direct_chat
def direct_chat_media(direct_chat, member, other):
    media_type = requested_media_type()
    if not media_type:
        return jsonify({"error": "Tipo de archivo no válido"}), 400
    limit, before_id = media_page_args()
    filters = [
        "direct_message.chat_id = ?",
        "direct_message.type IN ('image', 'video', 'audio', 'file')",
        "direct_message.file_url IS NOT NULL",
        "hidden.message_id IS NULL",
    ]
    params = [member["id"], direct_chat["id"]]
    if media_type != "all":
        filters.append("direct_message.type = ?")
        params.append(media_type)
    if before_id:
        filters.append("direct_message.id < ?")
        params.append(before_id)
    params.append(limit + 1)
    conn = get_db()
    rows = conn.execute(
        f"""SELECT direct_message.id, direct_message.type,
                   direct_message.file_url, direct_message.file_name,
                   direct_message.created_at,
                   author.display_name AS author_name
            FROM direct_messages AS direct_message
            JOIN room_members AS author
              ON author.id = direct_message.author_member_id
            LEFT JOIN direct_message_hides AS hidden
              ON hidden.message_id = direct_message.id AND hidden.member_id = ?
            WHERE {' AND '.join(filters)}
            ORDER BY direct_message.id DESC
            LIMIT ?""",
        params,
    ).fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    counts = {kind: 0 for kind in MEDIA_MESSAGE_TYPES}
    for count_row in conn.execute(
        """SELECT message.type, COUNT(*) AS total
           FROM direct_messages AS message
           LEFT JOIN direct_message_hides AS hidden
             ON hidden.message_id = message.id AND hidden.member_id = ?
           WHERE message.chat_id = ? AND hidden.message_id IS NULL
             AND message.type IN ('image', 'video', 'audio', 'file')
             AND message.file_url IS NOT NULL
           GROUP BY message.type""",
        (member["id"], direct_chat["id"]),
    ).fetchall():
        counts[count_row["type"]] = count_row["total"]
    counts["all"] = sum(counts.values())
    conn.close()
    return jsonify(
        {
            "items": [dict(row) for row in page],
            "counts": counts,
            "has_more": has_more,
            "next_before_id": page[-1]["id"] if has_more and page else None,
        }
    )


@app.route("/api/direct-chats/<int:chat_id>/messages", methods=["POST"])
@require_direct_chat
def post_direct_message(direct_chat, member, other):
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()[:2000]
    message_type = data.get("type") or "text"
    if message_type not in {"text", "image", "audio", "video", "file"}:
        message_type = "text"
    file_url = data.get("file_url")
    file_name = data.get("file_name")
    reply_to_id = data.get("reply_to_id")
    client_message_id = str(data.get("client_message_id") or "").strip() or None
    if message_type == "text" and not text:
        return jsonify({"error": "El mensaje está vacío"}), 400
    if message_type != "text" and not file_url:
        return jsonify({"error": "Falta el archivo adjunto"}), 400
    expected_prefix = f"/api/direct-chats/{direct_chat['id']}/files/"
    if file_url and not file_url.startswith(expected_prefix):
        return jsonify({"error": "El archivo no pertenece a este chat privado"}), 400
    if client_message_id and not re.fullmatch(
        r"[A-Za-z0-9._:-]{1,80}", client_message_id
    ):
        return jsonify({"error": "Identificador de mensaje no válido"}), 400

    conn = get_db()
    reply_to_name = None
    reply_to_text = None
    if reply_to_id is not None:
        try:
            reply_to_id = int(reply_to_id)
        except (TypeError, ValueError):
            conn.close()
            return jsonify({"error": "La referencia del mensaje no es válida"}), 400
        replied = conn.execute(
            """SELECT message.*, author.display_name AS author_name
               FROM direct_messages AS message
               JOIN room_members AS author ON author.id = message.author_member_id
               LEFT JOIN direct_message_hides AS hidden
                 ON hidden.message_id = message.id AND hidden.member_id = ?
               WHERE message.id = ? AND message.chat_id = ?
                 AND message.type != 'deleted' AND hidden.message_id IS NULL""",
            (member["id"], reply_to_id, direct_chat["id"]),
        ).fetchone()
        if not replied:
            conn.close()
            return jsonify(
                {"error": "El mensaje al que intentas responder ya no está disponible"}
            ), 404
        reply_to_name = replied["author_name"]
        reply_to_text = (
            (replied["text"] or "")[:180]
            if replied["type"] == "text"
            else {
                "image": "Imagen",
                "audio": "Nota de voz",
                "video": "Video",
                "file": replied["file_name"] or "Archivo",
            }.get(replied["type"], "Mensaje")
        )
    if client_message_id:
        existing = conn.execute(
            """SELECT * FROM direct_messages
               WHERE chat_id = ? AND author_member_id = ? AND client_message_id = ?""",
            (direct_chat["id"], member["id"], client_message_id),
        ).fetchone()
        if existing:
            conn.close()
            return jsonify(dict(existing)), 200
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        cursor = conn.execute(
            """INSERT INTO direct_messages
               (chat_id, author_member_id, text, type, file_url, file_name,
                reply_to_id, reply_to_name, reply_to_text,
                client_message_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                direct_chat["id"],
                member["id"],
                text,
                message_type,
                file_url,
                file_name,
                reply_to_id,
                reply_to_name,
                reply_to_text,
                client_message_id,
                now_iso,
            ),
        )
    except sqlite3.IntegrityError:
        existing = conn.execute(
            """SELECT * FROM direct_messages
               WHERE chat_id = ? AND author_member_id = ? AND client_message_id = ?""",
            (direct_chat["id"], member["id"], client_message_id),
        ).fetchone()
        if not existing:
            conn.close()
            raise
        conn.close()
        return jsonify(dict(existing)), 200
    conn.execute(
        "UPDATE direct_chats SET updated_at = ? WHERE id = ?",
        (now_iso, direct_chat["id"]),
    )
    conn.commit()
    result = conn.execute(
        "SELECT * FROM direct_messages WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    conn.close()
    return jsonify(dict(result)), 201


@app.route(
    "/api/direct-chats/<int:chat_id>/messages/<int:message_id>",
    methods=["PATCH", "DELETE"],
)
@require_direct_chat
def change_direct_message(direct_chat, member, other, message_id):
    data = request.get_json(silent=True) or {}
    conn = get_db()
    message = conn.execute(
        "SELECT * FROM direct_messages WHERE id = ? AND chat_id = ?",
        (message_id, direct_chat["id"]),
    ).fetchone()
    if not message:
        conn.close()
        return jsonify({"error": "El mensaje no existe en este chat"}), 404
    is_author = message["author_member_id"] == member["id"]
    if request.method == "PATCH":
        if not is_author:
            conn.close()
            return jsonify({"error": "Solo puedes editar los mensajes que enviaste"}), 403
        text = (data.get("text") or "").strip()[:2000]
        if message["type"] != "text" or message["deleted_at"] or not text:
            conn.close()
            return jsonify({"error": "Solo puedes editar mensajes de texto activos"}), 400
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute(
            "UPDATE direct_messages SET text = ?, edited_at = ? WHERE id = ?",
            (text, now_iso, message_id),
        )
        bump_direct_version(conn, direct_chat["id"])
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "text": text, "edited_at": now_iso})

    scope = data.get("scope") or "me"
    if scope not in {"me", "everyone"}:
        conn.close()
        return jsonify({"error": "Selecciona una opción de borrado válida"}), 400
    if scope == "everyone" and not is_author:
        conn.close()
        return jsonify(
            {"error": "Los mensajes de la otra persona solo se pueden borrar para ti"}
        ), 403
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if scope == "me":
        conn.execute(
            """INSERT OR IGNORE INTO direct_message_hides
               (chat_id, message_id, member_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (direct_chat["id"], message_id, member["id"], now_iso),
        )
    else:
        if message["deleted_at"]:
            conn.close()
            return jsonify({"error": "Este mensaje ya fue eliminado"}), 409
        conn.execute(
            """UPDATE direct_messages
               SET type = 'deleted', text = 'Este mensaje fue eliminado',
                   file_url = NULL, file_name = NULL, deleted_at = ?,
                   deleted_by_member_id = ?, reply_to_id = NULL,
                   reply_to_name = NULL, reply_to_text = NULL
               WHERE id = ?""",
            (now_iso, member["id"], message_id),
        )
        conn.execute("DELETE FROM direct_reactions WHERE message_id = ?", (message_id,))
        conn.execute("DELETE FROM direct_stars WHERE message_id = ?", (message_id,))
        conn.execute(
            """UPDATE direct_chats SET pinned_message_id = NULL
               WHERE id = ? AND pinned_message_id = ?""",
            (direct_chat["id"], message_id),
        )
    bump_direct_version(conn, direct_chat["id"])
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "scope": scope})


@app.route(
    "/api/direct-chats/<int:chat_id>/messages/<int:message_id>/reactions",
    methods=["POST"],
)
@require_direct_chat
def toggle_direct_reaction(direct_chat, member, other, message_id):
    data = request.get_json(silent=True) or {}
    emoji = data.get("emoji")
    if emoji not in {"👍", "❤️", "😂", "😮", "😢", "🎉"}:
        return jsonify({"error": "Reacción no válida"}), 400
    conn = get_db()
    message = conn.execute(
        """SELECT 1 FROM direct_messages
           WHERE id = ? AND chat_id = ? AND type != 'deleted'""",
        (message_id, direct_chat["id"]),
    ).fetchone()
    if not message:
        conn.close()
        return jsonify({"error": "El mensaje ya no está disponible"}), 404
    existing = conn.execute(
        """SELECT 1 FROM direct_reactions
           WHERE message_id = ? AND member_id = ? AND emoji = ?""",
        (message_id, member["id"], emoji),
    ).fetchone()
    if existing:
        conn.execute(
            """DELETE FROM direct_reactions
               WHERE message_id = ? AND member_id = ? AND emoji = ?""",
            (message_id, member["id"], emoji),
        )
    else:
        conn.execute(
            """INSERT INTO direct_reactions
               (message_id, member_id, emoji, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                message_id,
                member["id"],
                emoji,
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ),
        )
    bump_direct_version(conn, direct_chat["id"])
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "active": not bool(existing)})


@app.route("/api/direct-chats/<int:chat_id>/pin", methods=["POST"])
@require_direct_chat
def pin_direct_message(direct_chat, member, other):
    data = request.get_json(silent=True) or {}
    message_id = data.get("message_id")
    conn = get_db()
    if message_id is not None:
        message = conn.execute(
            """SELECT 1 FROM direct_messages
               WHERE id = ? AND chat_id = ? AND type != 'deleted'""",
            (message_id, direct_chat["id"]),
        ).fetchone()
        if not message:
            conn.close()
            return jsonify({"error": "El mensaje no pertenece a este chat"}), 404
    conn.execute(
        "UPDATE direct_chats SET pinned_message_id = ? WHERE id = ?",
        (message_id, direct_chat["id"]),
    )
    bump_direct_version(conn, direct_chat["id"])
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message_id": message_id})


@app.route(
    "/api/direct-chats/<int:chat_id>/messages/<int:message_id>/star",
    methods=["POST"],
)
@require_direct_chat
def toggle_direct_star(direct_chat, member, other, message_id):
    conn = get_db()
    message = conn.execute(
        """SELECT 1 FROM direct_messages
           WHERE id = ? AND chat_id = ? AND type != 'deleted'""",
        (message_id, direct_chat["id"]),
    ).fetchone()
    if not message:
        conn.close()
        return jsonify({"error": "El mensaje ya no está disponible"}), 404
    existing = conn.execute(
        "SELECT 1 FROM direct_stars WHERE message_id = ? AND member_id = ?",
        (message_id, member["id"]),
    ).fetchone()
    if existing:
        conn.execute(
            "DELETE FROM direct_stars WHERE message_id = ? AND member_id = ?",
            (message_id, member["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO direct_stars (message_id, member_id, created_at)
               VALUES (?, ?, ?)""",
            (
                message_id,
                member["id"],
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ),
        )
    bump_direct_version(conn, direct_chat["id"])
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "starred": not bool(existing)})


@app.route("/api/direct-chats/<int:chat_id>/search", methods=["GET"])
@require_direct_chat
def search_direct_messages(direct_chat, member, other):
    query = " ".join((request.args.get("q") or "").strip().split())[:80]
    if not query:
        return jsonify({"matches": [], "count": 0})
    conn = get_db()
    rows = conn.execute(
        """SELECT message.id, message.text, message.type, message.file_name,
                  message.created_at, author.display_name AS author_name
           FROM direct_messages AS message
           JOIN room_members AS author ON author.id = message.author_member_id
           LEFT JOIN direct_message_hides AS hidden
             ON hidden.message_id = message.id AND hidden.member_id = ?
           WHERE message.chat_id = ? AND hidden.message_id IS NULL
             AND message.type != 'deleted'
             AND (
               instr(lower(COALESCE(message.text, '')), lower(?)) > 0
               OR instr(lower(COALESCE(message.file_name, '')), lower(?)) > 0
             )
           ORDER BY message.id
           LIMIT 200""",
        (member["id"], direct_chat["id"], query, query),
    ).fetchall()
    conn.close()
    matches = [
        {
            "id": row["id"],
            "author_name": row["author_name"],
            "preview": (row["text"] or row["file_name"] or "Mensaje")[:100],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return jsonify({"matches": matches, "count": len(matches)})


@app.route("/api/direct-chats/<int:chat_id>/upload", methods=["POST"])
@require_direct_chat
def upload_direct_file(direct_chat, member, other):
    if "file" not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"error": "Nombre de archivo vacío"}), 400
    kind, _extension = classify_ext(uploaded.filename, request.form.get("kind"))
    safe_name = secure_filename(uploaded.filename) or "archivo"
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    direct_folder = os.path.join(UPLOAD_FOLDER, f"direct_{direct_chat['id']}")
    os.makedirs(direct_folder, exist_ok=True)
    uploaded.save(os.path.join(direct_folder, unique_name))
    return jsonify(
        {
            "url": url_for(
                "download_direct_file",
                chat_id=direct_chat["id"],
                filename=unique_name,
            ),
            "type": kind,
            "filename": safe_name,
        }
    )


@app.route("/api/direct-chats/<int:chat_id>/files/<path:filename>")
@require_direct_chat
def download_direct_file(direct_chat, member, other, filename):
    return send_from_directory(
        os.path.join(UPLOAD_FOLDER, f"direct_{direct_chat['id']}"),
        filename,
    )


# ---------------------------------------------------------------------------
# API del chat (todas estas rutas validan la sala en el servidor)
# ---------------------------------------------------------------------------

@app.route("/api/rooms/<room_slug>/updates", methods=["GET"])
@require_room_access
def get_updates(room, member):
    since_id = request.args.get("since", 0, type=int)
    me = member["display_name"]
    touch_user(room["id"], me)

    conn = get_db()
    member_rows = conn.execute(
        """SELECT id, display_name, role, status, profile_photo_url,
                  profile_banner_url, bio
           FROM room_members
           WHERE room_id = ? AND display_name != ''
           ORDER BY lower(display_name)""",
        (room["id"],),
    ).fetchall()
    roles_by_member_id = {item["id"]: item["role"] for item in member_rows}
    participants = [
        {
            "id": item["id"],
            "name": item["display_name"],
            "role": item["role"],
            "role_label": role_label(item["role"]),
            "photo_url": item["profile_photo_url"],
            "banner_url": item["profile_banner_url"],
            "bio": item["bio"],
        }
        for item in member_rows
        if item["status"] == "approved"
    ]
    rows = conn.execute(
        """SELECT message.*,
                  author.display_name AS current_author_name,
                  reply_author.display_name AS current_reply_name
           FROM messages AS message
           LEFT JOIN room_members AS author
             ON author.id = message.author_member_id
           LEFT JOIN messages AS replied
             ON replied.id = message.reply_to_id
           LEFT JOIN room_members AS reply_author
             ON reply_author.id = replied.author_member_id
           WHERE message.room_id = ? AND message.id > ?
           ORDER BY message.id ASC""",
        (room["id"], since_id),
    ).fetchall()
    messages = []
    for row in rows:
        message = dict(row)
        for private_field in (
            "deleted_by_member_id",
            "deleted_at",
            "deleted_original_text",
            "deleted_original_type",
            "deleted_original_file_url",
            "deleted_original_file_name",
            "current_author_name",
            "current_reply_name",
        ):
            message.pop(private_field, None)
        if row["current_author_name"] and row["type"] not in {"system", "deleted"}:
            message["name"] = row["current_author_name"]
        if row["current_reply_name"] and row["reply_to_id"]:
            message["reply_to_name"] = row["current_reply_name"]
        author_role = roles_by_member_id.get(row["author_member_id"])
        message["author_role"] = author_role
        message["author_role_label"] = role_label(author_role) if author_role else None
        author = next(
            (item for item in member_rows if item["id"] == row["author_member_id"]),
            None,
        )
        message["author_photo_url"] = author["profile_photo_url"] if author else None
        message["color"] = (
            user_color(conn, row["name"])
            if row["type"] not in {"system", "deleted"}
            else None
        )
        message["reactions"] = (
            [
                dict(item)
                for item in conn.execute(
                    "SELECT name, emoji FROM reactions WHERE message_id = ?", (row["id"],)
                ).fetchall()
            ]
            if row["type"] != "deleted"
            else []
        )
        message["read_count"] = conn.execute(
            "SELECT COUNT(*) FROM reads WHERE message_id = ? AND name != ?",
            (row["id"], me),
        ).fetchone()[0]
        messages.append(message)
    if me and since_id:
        unread_message_ids = [
            item["id"]
            for item in conn.execute(
                """SELECT message.id
                   FROM messages AS message
                   LEFT JOIN reads AS receipt
                     ON receipt.message_id = message.id AND receipt.name = ?
                   WHERE message.room_id = ?
                     AND message.id <= ?
                     AND message.name != ?
                     AND receipt.message_id IS NULL""",
                (me, room["id"], since_id, me),
            ).fetchall()
        ]
        if unread_message_ids:
            conn.executemany(
                "INSERT OR IGNORE INTO reads (message_id, name) VALUES (?, ?)",
                ((message_id, me) for message_id in unread_message_ids),
            )
    join_requests = []
    expulsion_requests = []
    pending_expulsion_target_ids = []
    if member["role"] == "admin":
        join_requests = [
            {"id": item["id"], "name": item["display_name"]}
            for item in conn.execute(
                """SELECT id, display_name FROM room_members
                   WHERE room_id = ? AND status = 'pending'
                   ORDER BY created_at""",
                (room["id"],),
            ).fetchall()
        ]
        expulsion_requests = [
            {
                "id": item["id"],
                "requester_id": item["requester_member_id"],
                "requester_name": item["requester_name"],
                "requester_role": item["requester_role"],
                "requester_role_label": role_label(item["requester_role"]),
                "target_id": item["target_member_id"],
                "target_name": item["target_name"],
                "target_role": item["target_role"],
                "target_role_label": role_label(item["target_role"]),
            }
            for item in conn.execute(
                """SELECT er.id,
                          requester.id AS requester_member_id,
                          requester.display_name AS requester_name,
                          requester.role AS requester_role,
                          target.id AS target_member_id,
                          target.display_name AS target_name,
                          target.role AS target_role
                   FROM expulsion_requests AS er
                   JOIN room_members AS requester
                     ON requester.id = er.requester_member_id
                   JOIN room_members AS target
                     ON target.id = er.target_member_id
                   WHERE er.room_id = ?
                     AND er.status = 'pending'
                     AND requester.status = 'approved'
                     AND requester.role = 'moderator'
                     AND target.status = 'approved'
                     AND target.role IN ('participant', 'guest')
                   ORDER BY er.created_at""",
                (room["id"],),
            ).fetchall()
        ]
    elif member["role"] == "moderator":
        pending_expulsion_target_ids = [
            item["target_member_id"]
            for item in conn.execute(
                """SELECT target_member_id FROM expulsion_requests
                   WHERE room_id = ? AND requester_member_id = ?
                     AND status = 'pending'""",
                (room["id"], member["id"]),
            ).fetchall()
        ]
    online_names = set(get_online_users(room["id"], exclude_name=me))
    online_members = [
        item for item in participants if item["name"] in online_names
    ]
    pinned = None
    if room["pinned_message_id"]:
        pinned_row = conn.execute(
            """SELECT message.id,
                      COALESCE(author.display_name, message.name) AS name,
                      message.text, message.type
               FROM messages AS message
               LEFT JOIN room_members AS author
                 ON author.id = message.author_member_id
               WHERE message.id = ? AND message.room_id = ?""",
            (room["pinned_message_id"], room["id"]),
        ).fetchone()
        if pinned_row:
            pinned = dict(pinned_row)
    version = conn.execute(
        "SELECT version FROM room_state WHERE room_id = ?", (room["id"],)
    ).fetchone()[0]
    conn.commit()
    conn.close()
    return jsonify(
        {
            "messages": messages,
            "typing": get_typing_names(room["id"], exclude_name=me),
            "online": online_members,
            "participants": participants,
            "join_requests": join_requests,
            "expulsion_requests": expulsion_requests,
            "pending_expulsion_target_ids": pending_expulsion_target_ids,
            "is_owner": member["role"] == "admin",
            "is_admin": member["role"] == "admin",
            "member_id": member["id"],
            "member_role": member["role"],
            "member_role_label": role_label(member["role"]),
            "pinned_message": pinned,
            "version": version,
        }
    )


@app.route("/api/rooms/<room_slug>/search", methods=["GET"])
@require_room_access
def search_room_messages(room, member):
    query = " ".join((request.args.get("q") or "").strip().split())[:80]
    if not query:
        return jsonify({"matches": [], "count": 0})
    conn = get_db()
    rows = conn.execute(
        """SELECT message.id,
                  COALESCE(author.display_name, message.name) AS author_name,
                  message.text, message.type, message.file_name, message.created_at
           FROM messages AS message
           LEFT JOIN room_members AS author
             ON author.id = message.author_member_id
           WHERE message.room_id = ? AND message.type NOT IN ('deleted', 'system')
              AND (
               instr(lower(COALESCE(message.text, '')), lower(?)) > 0
               OR instr(lower(COALESCE(message.file_name, '')), lower(?)) > 0
              )
           ORDER BY message.id
           LIMIT 200""",
        (room["id"], query, query),
    ).fetchall()
    conn.close()
    matches = [
        {
            "id": row["id"],
            "author_name": row["author_name"],
            "preview": (row["text"] or row["file_name"] or "Mensaje")[:100],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return jsonify({"matches": matches, "count": len(matches)})


@app.route("/api/rooms/<room_slug>/media", methods=["GET"])
@require_room_access
def room_media(room, member):
    media_type = requested_media_type()
    if not media_type:
        return jsonify({"error": "Tipo de archivo no válido"}), 400
    limit, before_id = media_page_args()
    filters = [
        "message.room_id = ?",
        "message.type IN ('image', 'video', 'audio', 'file')",
        "message.file_url IS NOT NULL",
    ]
    params = [room["id"]]
    if media_type != "all":
        filters.append("message.type = ?")
        params.append(media_type)
    if before_id:
        filters.append("message.id < ?")
        params.append(before_id)
    params.append(limit + 1)
    conn = get_db()
    rows = conn.execute(
        f"""SELECT message.id, message.type, message.file_url,
                   message.file_name, message.created_at,
                   COALESCE(author.display_name, message.name) AS author_name
            FROM messages AS message
            LEFT JOIN room_members AS author
              ON author.id = message.author_member_id
            WHERE {' AND '.join(filters)}
            ORDER BY message.id DESC
            LIMIT ?""",
        params,
    ).fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    counts = media_counts(conn, "messages", "room_id", room["id"])
    conn.close()
    return jsonify(
        {
            "items": [dict(row) for row in page],
            "counts": counts,
            "has_more": has_more,
            "next_before_id": page[-1]["id"] if has_more and page else None,
        }
    )


@app.route("/api/rooms/<room_slug>/typing", methods=["POST"])
@require_room_access
def post_typing(room, member):
    read_only = guest_write_error(member)
    if read_only:
        return read_only
    data = request.get_json(silent=True) or {}
    name = member["display_name"]
    touch_user(room["id"], name)
    set_typing(room["id"], name, bool(data.get("is_typing")))
    return jsonify({"ok": True})


@app.route("/api/rooms/<room_slug>/messages", methods=["POST"])
@require_room_access
def post_message(room, member):
    read_only = guest_write_error(member)
    if read_only:
        return read_only
    data = request.get_json(silent=True) or {}
    name = member["display_name"]
    text = (data.get("text") or "").strip()[:2000]
    msg_type = data.get("type", "text")
    if msg_type not in ("text", "image", "audio", "video", "file"):
        msg_type = "text"
    file_url = data.get("file_url")
    file_name = data.get("file_name")
    reply_to_id = data.get("reply_to_id")
    client_message_id = str(data.get("client_message_id") or "").strip() or None

    if msg_type == "text" and not text:
        return jsonify({"error": "El mensaje está vacío"}), 400
    if msg_type != "text" and not file_url:
        return jsonify({"error": "Falta el archivo adjunto"}), 400
    if file_url and not file_url.startswith(f"/api/rooms/{room['slug']}/files/"):
        return jsonify({"error": "El archivo no pertenece a esta sala"}), 400
    if client_message_id and not re.fullmatch(r"[A-Za-z0-9._:-]{1,80}", client_message_id):
        return jsonify({"error": "Identificador de mensaje no válido"}), 400

    conn = get_db()
    if client_message_id:
        existing = conn.execute(
            """SELECT * FROM messages
               WHERE room_id = ? AND author_member_id = ? AND client_message_id = ?""",
            (room["id"], member["id"], client_message_id),
        ).fetchone()
        if existing:
            result = dict(existing)
            result["color"] = user_color(conn, name)
            conn.commit()
            conn.close()
            return jsonify(result), 200
    reply_to_name = None
    reply_to_text = None
    if reply_to_id:
        replied = conn.execute(
            "SELECT * FROM messages WHERE id = ? AND room_id = ?",
            (reply_to_id, room["id"]),
        ).fetchone()
        if replied:
            reply_to_name = replied["name"]
            reply_to_text = (
                (replied["text"] or "")[:120]
                if replied["type"] == "text"
                else REPLY_LABELS.get(replied["type"], "")
            )
        else:
            reply_to_id = None

    try:
        cursor = conn.execute(
            """INSERT INTO messages
               (room_id, author_member_id, name, text, type, file_url, file_name,
                reply_to_id, reply_to_name, reply_to_text, client_message_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                room["id"],
                member["id"],
                name,
                text,
                msg_type,
                file_url,
                file_name,
                reply_to_id,
                reply_to_name,
                reply_to_text,
                client_message_id,
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ),
        )
    except sqlite3.IntegrityError:
        existing = (
            conn.execute(
                """SELECT * FROM messages
                   WHERE room_id = ? AND author_member_id = ?
                     AND client_message_id = ?""",
                (room["id"], member["id"], client_message_id),
            ).fetchone()
            if client_message_id
            else None
        )
        if not existing:
            conn.close()
            raise
        result = dict(existing)
        result["color"] = user_color(conn, name)
        conn.commit()
        conn.close()
        return jsonify(result), 200
    user_color(conn, name)
    conn.commit()
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,)).fetchone()
    set_typing(room["id"], name, False)
    result = dict(row)
    result["color"] = user_color(conn, name)
    conn.close()
    return jsonify(result), 201


@app.route("/api/rooms/<room_slug>/messages/<int:message_id>", methods=["PATCH", "DELETE"])
@require_room_access
def change_message(room, member, message_id):
    read_only = guest_write_error(member)
    if read_only:
        return read_only
    data = request.get_json(silent=True) or {}
    conn = get_db()
    message = conn.execute(
        "SELECT * FROM messages WHERE id = ? AND room_id = ?", (message_id, room["id"])
    ).fetchone()
    if not message:
        conn.close()
        return jsonify({"error": "El mensaje no existe"}), 404
    if message["type"] == "deleted":
        conn.close()
        return jsonify({"error": "Este mensaje ya fue borrado"}), 409
    if message["type"] == "system":
        conn.close()
        return jsonify({"error": "Los avisos del sistema no se pueden borrar"}), 403
    is_author = message["author_member_id"] == member["id"]
    can_moderate_messages = member["role"] in {"admin", "moderator"}
    if request.method == "DELETE" and not (is_author or can_moderate_messages):
        conn.close()
        return jsonify(
            {"error": "Tu rol no permite borrar mensajes ajenos para todos"}
        ), 403
    if request.method == "PATCH" and not is_author:
        conn.close()
        return jsonify({"error": "No puedes modificar este mensaje"}), 403
    if request.method == "DELETE":
        conn.execute(
            "UPDATE rooms SET pinned_message_id = NULL WHERE id = ? AND pinned_message_id = ?",
            (room["id"], message_id),
        )
        conn.execute("DELETE FROM reactions WHERE message_id = ?", (message_id,))
        author = conn.execute(
            "SELECT role FROM room_members WHERE id = ? AND room_id = ?",
            (message["author_member_id"], room["id"]),
        ).fetchone()
        author_role = author["role"] if author else "participant"
        audit_text = (
            f"El mensaje de {message['name']} ({role_label(author_role)}) "
            f"fue borrado por {member['display_name']} "
            f"({role_label(member['role'])})"
        )
        conn.execute(
            """UPDATE messages
               SET deleted_original_text = text,
                   deleted_original_type = type,
                   deleted_original_file_url = file_url,
                   deleted_original_file_name = file_name,
                   deleted_by_member_id = ?,
                   deleted_at = ?,
                   text = ?,
                   type = 'deleted',
                   file_url = NULL,
                   file_name = NULL,
                   reply_to_id = NULL,
                   reply_to_name = NULL,
                   reply_to_text = NULL
               WHERE id = ?""",
            (
                member["id"],
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
                audit_text,
                message_id,
            ),
        )
    else:
        text = (data.get("text") or "").strip()[:2000]
        if message["type"] != "text" or not text:
            conn.close()
            return jsonify({"error": "Solo se editan mensajes de texto"}), 400
        conn.execute("UPDATE messages SET text = ? WHERE id = ?", (text, message_id))
    bump_version(conn, room["id"])
    conn.commit()
    conn.close()
    return jsonify(
        {
            "ok": True,
            "type": "deleted" if request.method == "DELETE" else message["type"],
            "text": audit_text if request.method == "DELETE" else None,
        }
    )


@app.route("/api/rooms/<room_slug>/reactions", methods=["POST"])
@require_room_access
def toggle_reaction(room, member):
    read_only = guest_write_error(member)
    if read_only:
        return read_only
    data = request.get_json(silent=True) or {}
    message_id = data.get("message_id")
    name = member["display_name"]
    emoji = data.get("emoji")
    if not message_id or not name or emoji not in ("👍", "❤️", "😂", "😮"):
        return jsonify({"error": "Reacción inválida"}), 400
    conn = get_db()
    message = conn.execute(
        """SELECT 1 FROM messages
           WHERE id = ? AND room_id = ? AND type != 'deleted'""",
        (message_id, room["id"]),
    ).fetchone()
    if not message:
        conn.close()
        return jsonify({"error": "El mensaje no pertenece a esta sala"}), 404
    exists = conn.execute(
        "SELECT 1 FROM reactions WHERE message_id=? AND name=? AND emoji=?",
        (message_id, name, emoji),
    ).fetchone()
    if exists:
        conn.execute(
            "DELETE FROM reactions WHERE message_id=? AND name=? AND emoji=?",
            (message_id, name, emoji),
        )
    else:
        conn.execute(
            "INSERT OR IGNORE INTO reactions VALUES (?,?,?)", (message_id, name, emoji)
        )
    bump_version(conn, room["id"])
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/rooms/<room_slug>/members/<int:member_id>/decision", methods=["POST"])
@require_room_access
def decide_membership(room, actor, member_id):
    if actor["role"] != "admin":
        return jsonify({"error": "Solo un Admin puede decidir quién entra"}), 403
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in {"approve", "reject"}:
        return jsonify({"error": "Decisión no válida"}), 400
    assigned_role = data.get("role") or "participant"
    if action == "approve" and assigned_role not in ROLE_ORDER:
        return jsonify({"error": "Selecciona un rol válido"}), 400
    conn = get_db()
    target = conn.execute(
        """SELECT * FROM room_members
           WHERE id = ? AND room_id = ? AND status = 'pending'""",
        (member_id, room["id"]),
    ).fetchone()
    if not target:
        conn.close()
        return jsonify({"error": "La solicitud ya no está pendiente"}), 404
    status = "approved" if action == "approve" else "rejected"
    if status == "approved":
        conn.execute(
            """UPDATE room_members
               SET status = 'approved',
                   role = ?,
                   approved_by_member_id = ?,
                   approved_by_name = ?,
                   approved_by_role = ?,
                   welcome_pending = 1
               WHERE id = ?""",
            (
                assigned_role,
                actor["id"],
                actor["display_name"],
                actor["role"],
                member_id,
            ),
        )
        insert_system_message(conn, room["id"], f"{target['display_name']} se unió a la sala")
    else:
        conn.execute(
            "UPDATE room_members SET status = 'rejected', welcome_pending = 0 WHERE id = ?",
            (member_id,),
        )
    conn.commit()
    conn.close()
    return jsonify(
        {
            "ok": True,
            "status": status,
            "role": assigned_role if status == "approved" else None,
            "role_label": role_label(assigned_role) if status == "approved" else None,
        }
    )


@app.route("/api/rooms/<room_slug>/members/<int:member_id>/kick", methods=["POST"])
@require_room_access
def kick_member(room, actor, member_id):
    if actor["role"] not in {"admin", "moderator"}:
        return jsonify({"error": "Tu rol no permite expulsar participantes"}), 403
    if actor["id"] == member_id:
        return jsonify({"error": "No puedes expulsarte a ti mismo"}), 400
    conn = get_db()
    target = conn.execute(
        """SELECT * FROM room_members
           WHERE id = ? AND room_id = ? AND status = 'approved'""",
        (member_id, room["id"]),
    ).fetchone()
    if not target:
        conn.close()
        return jsonify({"error": "No se puede expulsar a esa persona"}), 404
    if actor["role"] == "moderator" and target["role"] == "admin":
        conn.close()
        return jsonify({"error": "Un Moderador no puede expulsar a un Admin"}), 403
    if actor["role"] == "moderator" and target["role"] in {"participant", "guest"}:
        existing = conn.execute(
            """SELECT id, requester_member_id FROM expulsion_requests
               WHERE room_id = ? AND target_member_id = ? AND status = 'pending'""",
            (room["id"], member_id),
        ).fetchone()
        if existing:
            conn.close()
            message = (
                "Ya enviaste una solicitud de expulsión para esta persona"
                if existing["requester_member_id"] == actor["id"]
                else "Ya existe una solicitud de expulsión pendiente para esta persona"
            )
            return jsonify({"error": message, "code": "expulsion_request_exists"}), 409
        try:
            cursor = conn.execute(
                """INSERT INTO expulsion_requests
                   (room_id, requester_member_id, target_member_id,
                    requester_name, requester_role, target_name, target_role,
                    status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    room["id"],
                    actor["id"],
                    target["id"],
                    actor["display_name"],
                    actor["role"],
                    target["display_name"],
                    target["role"],
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                ),
            )
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify(
                {
                    "error": "Ya existe una solicitud de expulsión pendiente para esta persona",
                    "code": "expulsion_request_exists",
                }
            ), 409
        bump_version(conn, room["id"])
        conn.commit()
        conn.close()
        return jsonify(
            {
                "ok": True,
                "status": "pending_approval",
                "request_id": cursor.lastrowid,
                "message": "Solicitud de expulsión enviada. Un Admin debe aprobarla.",
            }
        ), 202
    conn.execute(
        """UPDATE expulsion_requests
           SET status = 'cancelled', decided_at = ?
           WHERE room_id = ? AND status = 'pending'
             AND (requester_member_id = ? OR target_member_id = ?)""",
        (
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
            room["id"],
            member_id,
            member_id,
        ),
    )
    conn.execute("UPDATE room_members SET status = 'kicked' WHERE id = ?", (member_id,))
    insert_system_message(
        conn,
        room["id"],
        f"{target['display_name']} fue expulsado por "
        f"{actor['display_name']} ({role_label(actor['role'])})",
    )
    conn.commit()
    conn.close()
    with _presence_lock:
        _typing_users.pop((room["id"], target["display_name"]), None)
        _online_users.pop((room["id"], target["display_name"]), None)
    return jsonify({"ok": True, "status": "kicked"})


@app.route(
    "/api/rooms/<room_slug>/expulsion-requests/<int:request_id>/decision",
    methods=["POST"],
)
@require_room_access
def decide_expulsion_request(room, actor, request_id):
    if actor["role"] != "admin":
        return jsonify({"error": "Solo un Admin puede decidir una expulsión"}), 403
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in {"approve", "reject"}:
        return jsonify({"error": "Decisión no válida"}), 400

    conn = get_db()
    pending = conn.execute(
        """SELECT er.*,
                  requester.display_name AS current_requester_name,
                  requester.role AS current_requester_role,
                  requester.status AS requester_status,
                  target.display_name AS current_target_name,
                  target.role AS current_target_role,
                  target.status AS target_status
           FROM expulsion_requests AS er
           LEFT JOIN room_members AS requester
             ON requester.id = er.requester_member_id
           LEFT JOIN room_members AS target
             ON target.id = er.target_member_id
           WHERE er.id = ? AND er.room_id = ? AND er.status = 'pending'""",
        (request_id, room["id"]),
    ).fetchone()
    if not pending:
        conn.close()
        return jsonify({"error": "La solicitud ya no está pendiente"}), 404

    decided_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if action == "reject":
        conn.execute(
            """UPDATE expulsion_requests
               SET status = 'rejected', decided_at = ?,
                   decided_by_member_id = ?, decided_by_name = ?
               WHERE id = ? AND status = 'pending'""",
            (decided_at, actor["id"], actor["display_name"], request_id),
        )
        bump_version(conn, room["id"])
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "status": "rejected"})

    request_is_valid = (
        pending["requester_status"] == "approved"
        and pending["current_requester_role"] == "moderator"
        and pending["target_status"] == "approved"
        and pending["current_target_role"] in {"participant", "guest"}
        and pending["requester_member_id"] != pending["target_member_id"]
    )
    if not request_is_valid:
        conn.execute(
            """UPDATE expulsion_requests
               SET status = 'cancelled', decided_at = ?,
                   decided_by_member_id = ?, decided_by_name = ?
               WHERE id = ? AND status = 'pending'""",
            (decided_at, actor["id"], actor["display_name"], request_id),
        )
        bump_version(conn, room["id"])
        conn.commit()
        conn.close()
        return jsonify(
            {
                "error": "La solicitud dejó de ser válida porque cambió el estado o rol de una persona",
                "code": "stale_expulsion_request",
            }
        ), 409

    conn.execute(
        "UPDATE room_members SET status = 'kicked' WHERE id = ?",
        (pending["target_member_id"],),
    )
    conn.execute(
        """UPDATE expulsion_requests
           SET status = 'approved', decided_at = ?,
               decided_by_member_id = ?, decided_by_name = ?
           WHERE id = ? AND status = 'pending'""",
        (decided_at, actor["id"], actor["display_name"], request_id),
    )
    conn.execute(
        """UPDATE expulsion_requests
           SET status = 'cancelled', decided_at = ?
           WHERE room_id = ? AND status = 'pending'
             AND target_member_id = ? AND id != ?""",
        (decided_at, room["id"], pending["target_member_id"], request_id),
    )
    insert_system_message(
        conn,
        room["id"],
        f"{pending['current_target_name']} fue expulsado después de que "
        f"{actor['display_name']} ({role_label(actor['role'])}) aprobara "
        f"la solicitud de {pending['current_requester_name']} "
        f"({role_label(pending['current_requester_role'])})",
    )
    conn.commit()
    conn.close()
    with _presence_lock:
        _typing_users.pop((room["id"], pending["current_target_name"]), None)
        _online_users.pop((room["id"], pending["current_target_name"]), None)
    return jsonify({"ok": True, "status": "kicked"})


@app.route("/api/rooms/<room_slug>/members/<int:member_id>/role", methods=["POST"])
@require_room_access
def change_member_role(room, actor, member_id):
    if actor["role"] != "admin":
        return jsonify({"error": "Solo un Admin puede cambiar roles"}), 403
    if actor["id"] == member_id:
        return jsonify({"error": "No puedes cambiar tu propio rol"}), 400

    data = request.get_json(silent=True) or {}
    action = data.get("action")
    new_role = data.get("role")
    if action not in {"ascend", "descend"} or new_role not in ROLE_ORDER:
        return jsonify({"error": "Cambio de jerarquía no válido"}), 400

    conn = get_db()
    target = conn.execute(
        """SELECT * FROM room_members
           WHERE id = ? AND room_id = ? AND status = 'approved'""",
        (member_id, room["id"]),
    ).fetchone()
    if not target:
        conn.close()
        return jsonify({"error": "La persona ya no está disponible"}), 404

    current_level = ROLE_ORDER[target["role"]]
    new_level = ROLE_ORDER[new_role]
    valid_direction = (
        action == "ascend" and new_level > current_level
    ) or (
        action == "descend" and new_level < current_level
    )
    if not valid_direction:
        conn.close()
        return jsonify(
            {"error": "El rol elegido no corresponde con esa dirección jerárquica"}
        ), 409

    conn.execute(
        """UPDATE expulsion_requests
           SET status = 'cancelled', decided_at = ?
           WHERE room_id = ? AND status = 'pending'
             AND (requester_member_id = ? OR target_member_id = ?)""",
        (
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
            room["id"],
            member_id,
            member_id,
        ),
    )
    conn.execute("UPDATE room_members SET role = ? WHERE id = ?", (new_role, member_id))
    verb = "ascendido" if action == "ascend" else "descendido"
    insert_system_message(
        conn,
        room["id"],
        f"Se le ha {verb} a {target['display_name']} al rango de {role_label(new_role)}",
    )
    conn.commit()
    conn.close()

    if new_role == "guest":
        set_typing(room["id"], target["display_name"], False)
    return jsonify(
        {
            "ok": True,
            "role": new_role,
            "role_label": role_label(new_role),
        }
    )


@app.route("/api/rooms/<room_slug>/pin", methods=["POST"])
@require_room_access
def set_pinned_message(room, member):
    read_only = guest_write_error(member)
    if read_only:
        return read_only
    data = request.get_json(silent=True) or {}
    message_id = data.get("message_id")
    conn = get_db()
    if message_id is not None:
        message = conn.execute(
            """SELECT 1 FROM messages
               WHERE id = ? AND room_id = ? AND type NOT IN ('system', 'deleted')""",
            (message_id, room["id"]),
        ).fetchone()
        if not message:
            conn.close()
            return jsonify({"error": "No se puede fijar ese mensaje"}), 404
    conn.execute(
        "UPDATE rooms SET pinned_message_id = ? WHERE id = ?",
        (message_id, room["id"]),
    )
    bump_version(conn, room["id"])
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "pinned_message_id": message_id})


@app.route("/api/rooms/unread", methods=["POST"])
def unread_counts():
    data = request.get_json(silent=True) or {}
    requested_rooms = data.get("rooms") or []
    if not isinstance(requested_rooms, list):
        return jsonify({"error": "Formato de salas no válido"}), 400
    results = {}
    conn = get_db()
    for item in requested_rooms[:20]:
        slug = str((item or {}).get("slug") or "")
        seen = max(0, int((item or {}).get("seen") or 0))
        room = conn.execute("SELECT * FROM rooms WHERE slug = ?", (slug,)).fetchone()
        if not room or not has_room_access(room):
            continue
        current_member = get_current_member(room, conn)
        if not current_member or current_member["status"] != "approved":
            continue
        count = conn.execute(
            """SELECT COUNT(*) FROM messages
               WHERE room_id = ? AND id > ? AND type != 'system'
                 AND (author_member_id IS NULL OR author_member_id != ?)""",
            (room["id"], seen, current_member["id"]),
        ).fetchone()[0]
        latest = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM messages WHERE room_id = ?",
            (room["id"],),
        ).fetchone()[0]
        results[slug] = {"count": min(count, 99), "latest": latest}
    conn.close()
    return jsonify({"rooms": results})


@app.route("/api/rooms/<room_slug>/upload", methods=["POST"])
@require_room_access
def upload_file(room, member):
    read_only = guest_write_error(member)
    if read_only:
        return read_only
    if "file" not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"error": "Nombre de archivo vacío"}), 400

    kind, _extension = classify_ext(uploaded.filename, request.form.get("kind"))
    safe_name = secure_filename(uploaded.filename) or "archivo"
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    room_folder = os.path.join(UPLOAD_FOLDER, room["slug"])
    os.makedirs(room_folder, exist_ok=True)
    uploaded.save(os.path.join(room_folder, unique_name))
    return jsonify(
        {
            "url": url_for("download_file", room_slug=room["slug"], filename=unique_name),
            "type": kind,
            "filename": safe_name,
        }
    )


@app.route("/api/rooms/<room_slug>/files/<path:filename>")
@require_room_access
def download_file(room, member, filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER, room["slug"]), filename)


@app.route("/api/rooms/<room_slug>/reset", methods=["POST"])
@require_room_access
def reset_chat(room, member):
    if member["role"] != "admin":
        return jsonify({"error": "Solo un Admin puede vaciar la sala"}), 403
    conn = get_db()
    message_ids = [
        row[0]
        for row in conn.execute(
            "SELECT id FROM messages WHERE room_id = ?", (room["id"],)
        ).fetchall()
    ]
    if message_ids:
        placeholders = ",".join("?" for _ in message_ids)
        conn.execute(f"DELETE FROM reactions WHERE message_id IN ({placeholders})", message_ids)
        conn.execute(f"DELETE FROM reads WHERE message_id IN ({placeholders})", message_ids)
    conn.execute("DELETE FROM messages WHERE room_id = ?", (room["id"],))
    bump_version(conn, room["id"])
    conn.commit()
    conn.close()
    with _presence_lock:
        for state in (_typing_users, _online_users):
            for key in list(state):
                if key[0] == room["id"]:
                    state.pop(key, None)
    return jsonify({"ok": True})


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "El archivo es demasiado grande (máximo 50 MB)"}), 413


@app.errorhandler(sqlite3.Error)
def database_error(error):
    app.logger.error("Error de SQLite durante una solicitud: %s", error)
    return jsonify(
        {
            "error": "El chat está ocupado. Reintentaremos el envío automáticamente.",
            "code": "chat_busy",
            "retryable": True,
        }
    ), 503


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

def start_ngrok(port):
    try:
        from pyngrok import ngrok
    except ImportError:
        print("\nAviso: pyngrok no está instalado. Instálalo con: pip install pyngrok")
        print(f"El chat solo estará disponible en local (http://127.0.0.1:{port})\n")
        return None

    token = os.environ.get("NGROK_AUTHTOKEN")
    if token:
        ngrok.set_auth_token(token)
    try:
        tunnel = ngrok.connect(port, "http")
        url = tunnel.public_url
        return "https://" + url[len("http://") :] if url.startswith("http://") else url
    except Exception as error:
        print("\nAviso: no se pudo iniciar ngrok:", error)
        print("Revisa tu authtoken en el README.md.\n")
        return None


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    use_ngrok = os.environ.get("USE_NGROK", "1") == "1"
    public_url = start_ngrok(port) if use_ngrok else None

    print("=" * 60)
    print(f"Chat corriendo en local: http://127.0.0.1:{port}")
    if public_url:
        print(f"Link público (compártelo): {public_url}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
