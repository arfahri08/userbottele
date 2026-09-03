"""
USERNAME TRACKER MODULE

Menyimpan riwayat username berdasarkan Telegram numeric User ID.
Tujuan utamanya adalah menjaga jejak identitas akun yang pernah mengirim
private message ke akun ini, termasuk jika dialog kemudian dihapus.

Tidak mencoba mencari identitas di luar akun yang sudah pernah berinteraksi.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, events, types
from telethon.errors import FloodWaitError

from config import (
    SAVED_MESSAGES_TARGET,
    USERNAME_TRACKER_ENABLED,
    USERNAME_TRACKER_SCAN_MINUTES,
)
from modules.commands import parse_event_command

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "username_history.json"
DATA_VERSION = 1
BATCH_SIZE = 50
INITIAL_SCAN_DELAY_SECONDS = 8

_store = None
_store_lock = asyncio.Lock()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _normalize_username(value):
    value = str(value or "").strip().lstrip("@")
    return value.lower() if value else None


def _display_name(entity) -> str:
    first_name = str(getattr(entity, "first_name", None) or "").strip()
    last_name = str(getattr(entity, "last_name", None) or "").strip()
    name = f"{first_name} {last_name}".strip()
    if name:
        return name

    username = _normalize_username(getattr(entity, "username", None))
    return f"@{username}" if username else str(getattr(entity, "id", "Unknown"))


def _empty_store():
    return {"version": DATA_VERSION, "users": {}}


def _load_store():
    if not DATA_FILE.exists():
        return _empty_store()

    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("users"), dict):
            raise ValueError("format data tidak valid")
        raw.setdefault("version", DATA_VERSION)
        return raw
    except Exception as exc:
        backup = DATA_FILE.with_suffix(f".corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        try:
            DATA_FILE.replace(backup)
            logger.error("Database username rusak dipindah ke %s: %s", backup, exc)
        except Exception:
            logger.exception("Database username rusak dan gagal dibackup")
        return _empty_store()


def _save_store(store):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = DATA_FILE.with_suffix(".tmp")
    temp.write_text(
        json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp.replace(DATA_FILE)


def _username_label(username) -> str:
    return f"@{username}" if username else "[tidak ada / dihapus]"


def _source_label(source: str) -> str:
    return {
        "incoming_message": "pesan private masuk",
        "periodic_scan": "scan otomatis",
        "manual_lookup": "pemeriksaan manual",
        "startup_scan": "scan saat startup",
    }.get(source, source)


def _apply_observation(store, *, user_id: int, username, display_name: str, source: str, now: str):
    """Pure state update. Return change payload jika username berubah."""

    users = store.setdefault("users", {})
    key = str(int(user_id))
    username = _normalize_username(username)
    display_name = str(display_name or key).strip() or key

    record = users.get(key)
    if not record:
        users[key] = {
            "user_id": int(user_id),
            "display_name": display_name,
            "current_username": username,
            "first_seen": now,
            "last_seen": now,
            "history": [
                {
                    "username": username,
                    "detected_at": now,
                    "source": source,
                }
            ],
        }
        return None, True

    old_username = _normalize_username(record.get("current_username"))
    record["display_name"] = display_name
    record["last_seen"] = now

    if old_username == username:
        return None, False

    record["current_username"] = username
    record.setdefault("history", []).append(
        {
            "username": username,
            "detected_at": now,
            "source": source,
        }
    )

    change = {
        "user_id": int(user_id),
        "display_name": display_name,
        "old_username": old_username,
        "new_username": username,
        "detected_at": now,
        "source": source,
    }
    return change, True


async def _observe_entity(client: TelegramClient, entity, source: str):
    global _store

    if not entity or not isinstance(entity, types.User):
        return None

    user_id = getattr(entity, "id", None)
    if not user_id:
        return None

    now = _now_iso()
    async with _store_lock:
        change, dirty = _apply_observation(
            _store,
            user_id=user_id,
            username=getattr(entity, "username", None),
            display_name=_display_name(entity),
            source=source,
            now=now,
        )
        if dirty:
            _save_store(_store)

    if change:
        text = (
            "🔎 USERNAME BERUBAH\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Nama: {change['display_name']}\n"
            f"🆔 User ID: {change['user_id']}\n"
            f"⬅️ Username lama: {_username_label(change['old_username'])}\n"
            f"➡️ Username baru: {_username_label(change['new_username'])}\n"
            f"🛰️ Terdeteksi via: {_source_label(change['source'])}\n"
            f"🕒 Waktu: {change['detected_at']}\n\n"
            "Riwayat tetap dikunci ke numeric User ID, bukan username."
        )
        try:
            await client.send_message(SAVED_MESSAGES_TARGET, text, link_preview=False)
        except Exception:
            logger.exception("Gagal mengirim notifikasi perubahan username untuk %s", user_id)

        logger.info(
            "Username user %s berubah: %s -> %s",
            user_id,
            change["old_username"],
            change["new_username"],
        )

    return change


async def _refresh_user_ids(client: TelegramClient, user_ids, source: str):
    if not user_ids:
        return 0

    changes = 0
    peers = [types.PeerUser(int(user_id)) for user_id in user_ids]

    try:
        entities = await client.get_entity(peers)
        if not isinstance(entities, (list, tuple)):
            entities = [entities]

        for entity in entities:
            if await _observe_entity(client, entity, source):
                changes += 1
        return changes

    except FloodWaitError:
        raise
    except Exception as batch_error:
        logger.debug("Batch username refresh gagal, fallback per-user: %s", batch_error)

    for user_id in user_ids:
        try:
            entity = await client.get_entity(types.PeerUser(int(user_id)))
            if await _observe_entity(client, entity, source):
                changes += 1
        except FloodWaitError:
            raise
        except Exception as exc:
            logger.debug("Gagal refresh username user %s: %s", user_id, exc)
        await asyncio.sleep(0.15)

    return changes


async def _scan_all_known_users(client: TelegramClient, source: str = "periodic_scan"):
    async with _store_lock:
        user_ids = [int(key) for key in _store.get("users", {}).keys() if str(key).isdigit()]

    total_changes = 0
    for start in range(0, len(user_ids), BATCH_SIZE):
        batch = user_ids[start:start + BATCH_SIZE]
        try:
            total_changes += await _refresh_user_ids(client, batch, source)
        except FloodWaitError as exc:
            delay = max(int(getattr(exc, "seconds", 0) or 0), 1) + 2
            logger.warning("FloodWait saat scan username. Tidur %s detik.", delay)
            await asyncio.sleep(delay)
        await asyncio.sleep(0.5)

    return len(user_ids), total_changes


async def _background_scan(client: TelegramClient):
    await asyncio.sleep(INITIAL_SCAN_DELAY_SECONDS)
    first_cycle = True

    while True:
        try:
            source = "startup_scan" if first_cycle else "periodic_scan"
            checked, changes = await _scan_all_known_users(client, source=source)
            logger.info(
                "Username tracker scan selesai: %s user diperiksa, %s perubahan",
                checked,
                changes,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Background username scan gagal")

        first_cycle = False
        await asyncio.sleep(USERNAME_TRACKER_SCAN_MINUTES * 60)


def _format_history(record) -> str:
    lines = [
        "🔎 USERNAME HISTORY",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👤 Nama terakhir: {record.get('display_name') or '-'}",
        f"🆔 User ID: {record.get('user_id')}",
        f"📌 Username sekarang: {_username_label(_normalize_username(record.get('current_username')))}",
        f"🕒 Pertama tercatat: {record.get('first_seen') or '-'}",
        f"🕒 Terakhir dicek: {record.get('last_seen') or '-'}",
        "",
        "Riwayat:",
    ]

    history = record.get("history") or []
    for idx, item in enumerate(history[-20:], 1):
        lines.append(
            f"{idx}. {_username_label(_normalize_username(item.get('username')))} | "
            f"{item.get('detected_at') or '-'} | {_source_label(item.get('source') or '-') }"
        )

    if len(history) > 20:
        lines.append(f"... {len(history) - 20} riwayat lebih lama tidak ditampilkan.")

    return "\n".join(lines)


async def _edit_or_reply(event, text: str):
    try:
        await event.edit(text)
    except Exception:
        await event.reply(text)


async def _resolve_history_target(client: TelegramClient, event, parts):
    if len(parts) > 1:
        raw = parts[1].strip()
        if raw.lstrip("-").isdigit():
            return str(abs(int(raw)))

        try:
            entity = await client.get_entity(raw)
            if isinstance(entity, types.User):
                await _observe_entity(client, entity, "manual_lookup")
                return str(entity.id)
        except Exception:
            return None

    reply = await event.get_reply_message()
    if reply:
        try:
            sender = await reply.get_sender()
            if isinstance(sender, types.User):
                await _observe_entity(client, sender, "manual_lookup")
                return str(sender.id)
        except Exception:
            pass

    return None


async def setup_plugin(client: TelegramClient):
    """Setup username-history persistence dan background refresh."""

    global _store

    if not USERNAME_TRACKER_ENABLED:
        logger.info("Username tracker module loaded (DISABLED)")
        return

    _store = _load_store()

    @client.on(events.NewMessage(incoming=True, func=lambda e: bool(getattr(e, "is_private", False))))
    async def username_tracker_incoming(event):
        try:
            sender = await event.get_sender()
            await _observe_entity(client, sender, "incoming_message")
        except Exception as exc:
            logger.debug("Username tracker incoming gagal: %s", exc)

    @client.on(events.NewMessage(outgoing=True))
    async def username_history_command(event):
        parts = parse_event_command(event)
        if not parts or parts[0] not in ("usn", "usernamehistory", "usnhistory"):
            return

        target_key = await _resolve_history_target(client, event, parts)
        if not target_key:
            async with _store_lock:
                total = len(_store.get("users", {}))
            await _edit_or_reply(
                event,
                "Format: reply pesan lalu .usn, atau .usn <user_id/@username>\n"
                f"Total akun yang sudah tercatat: {total}",
            )
            return

        async with _store_lock:
            record = (_store.get("users", {}).get(target_key) or {}).copy()

        if not record:
            await _edit_or_reply(event, f"Belum ada riwayat untuk User ID {target_key}.")
            return

        await _edit_or_reply(event, _format_history(record))

    asyncio.create_task(_background_scan(client))
    logger.info(
        "Username tracker module loaded: %s user tersimpan, scan tiap %s menit",
        len(_store.get("users", {})),
        USERNAME_TRACKER_SCAN_MINUTES,
    )
