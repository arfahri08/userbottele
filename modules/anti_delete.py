"""
ANTI DELETE MODULE
Simpan teks dan media pesan private yang dihapus.
"""

import asyncio
import html
import logging
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.types import UpdateDeleteChannelMessages, UpdateDeleteMessages

from config import (
    ANTI_DELETE_ENABLED,
    FORWARD_CHAT_ID,
    SAVE_TO_SAVED_MESSAGES,
    SAVED_MESSAGES_TARGET,
)
from modules.helpers import inspect_message_extended_media

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path("downloads") / "deleted_messages"
MAX_CACHE_SIZE = 1000
MAX_CACHE_AGE_SECONDS = 6 * 3600
TEXT_PREVIEW_LIMIT = 1800
CAPTION_TEXT_LIMIT = 450

deleted_message_cache = {}


def _safe_text(value) -> str:
    return str(value or "").strip()


def _clip(value: str, limit: int = TEXT_PREVIEW_LIMIT) -> str:
    value = _safe_text(value)
    if len(value) <= limit:
        return value
    return f"{value[:limit]}... [dipotong]"


def _escape(value) -> str:
    return html.escape(str(value or ""), quote=False)


def _display_name(entity, fallback="Unknown") -> str:
    if not entity:
        return fallback

    title = getattr(entity, "title", None)
    if title:
        return title

    first_name = getattr(entity, "first_name", None) or ""
    last_name = getattr(entity, "last_name", None) or ""
    name = f"{first_name} {last_name}".strip()
    if name:
        return name

    username = getattr(entity, "username", None)
    return f"@{username}" if username else fallback


def _user_link(sender_id, username=None):
    if username:
        return f"https://t.me/{username}"
    if sender_id:
        return f"tg://user?id={sender_id}"
    return None


def _message_link(chat_id, chat_username, msg_id):
    if chat_username:
        return f"https://t.me/{chat_username}/{msg_id}"

    chat_id_text = str(chat_id or "")
    if chat_id_text.startswith("-100"):
        return f"https://t.me/c/{chat_id_text[4:]}/{msg_id}"

    return None


def _build_link(label: str, url: str):
    if not url:
        return None
    escaped_url = _escape(url)
    return f"{label}: <a href=\"{escaped_url}\">{escaped_url}</a>"


def _is_paid_media(message) -> bool:
    return inspect_message_extended_media(message) is not None


def _media_label(message) -> str:
    checks = (
        ("sticker", "Sticker"),
        ("gif", "GIF"),
        ("video_note", "Video Note"),
        ("voice", "Voice Note"),
        ("photo", "Foto"),
        ("video", "Video"),
        ("audio", "Audio"),
        ("document", "Dokumen"),
    )
    for attr, label in checks:
        try:
            if getattr(message, attr, None):
                return label
        except Exception:
            continue

    return type(getattr(message, "media", None)).__name__ if getattr(message, "media", None) else "Tidak ada"


def _build_sender_line(snapshot) -> str:
    sender_name = _escape(snapshot.get("sender_name") or snapshot.get("sender_id") or "Unknown")
    username = snapshot.get("sender_username")
    user_link = snapshot.get("user_link")

    if user_link:
        mention = f'<a href="{_escape(user_link)}">{sender_name}</a>'
    else:
        mention = sender_name

    if username:
        return f"{mention} (@{_escape(username)})"
    return mention


def _plain_sender_line(snapshot) -> str:
    sender_name = _escape(snapshot.get("sender_name") or snapshot.get("sender_id") or "Unknown")
    username = snapshot.get("sender_username")
    if username:
        return f"{sender_name} (@{_escape(username)})"
    return sender_name


async def _snapshot_message(client: TelegramClient, event):
    message = event.message
    sender = None
    chat = None
    file_path = None

    try:
        sender = await event.get_sender()
    except Exception as e:
        logger.debug("Gagal ambil sender untuk anti-delete: %s", e)

    try:
        chat = await event.get_chat()
    except Exception as e:
        logger.debug("Gagal ambil chat untuk anti-delete: %s", e)

    text = message.raw_text or message.text or ""
    has_media = bool(getattr(message, "media", None))

    if has_media and not _is_paid_media(message):
        try:
            DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            file_path = await client.download_media(message, file=DOWNLOAD_DIR)
            if not file_path:
                logger.warning("Media pesan %s gagal diunduh untuk anti-delete", message.id)
        except Exception as e:
            logger.warning("Gagal download media pesan %s untuk anti-delete: %s", message.id, e)

    sender_username = getattr(sender, "username", None)
    chat_username = getattr(chat, "username", None)

    return {
        "id": message.id,
        "chat_id": event.chat_id,
        "chat_title": _display_name(chat, str(event.chat_id)),
        "chat_username": chat_username,
        "sender_id": event.sender_id,
        "sender_name": _display_name(sender, str(event.sender_id or "Unknown")),
        "sender_username": sender_username,
        "text": text,
        "has_media": has_media,
        "media_type": _media_label(message),
        "file_path": str(file_path) if file_path else None,
        "message_link": _message_link(event.chat_id, chat_username, message.id),
        "user_link": _user_link(event.sender_id, sender_username),
        "timestamp": datetime.now(),
    }


def _delete_cached_file(snapshot):
    file_path = snapshot.get("file_path") if snapshot else None
    if not file_path:
        return

    try:
        Path(file_path).unlink(missing_ok=True)
    except Exception as e:
        logger.debug("Gagal hapus file cache anti-delete %s: %s", file_path, e)


def _put_cache(snapshot):
    chat_id = snapshot["chat_id"]
    msg_id = snapshot["id"]

    if chat_id not in deleted_message_cache:
        deleted_message_cache[chat_id] = {}

    old_snapshot = deleted_message_cache[chat_id].get(msg_id)
    if old_snapshot:
        _delete_cached_file(old_snapshot)

    deleted_message_cache[chat_id][msg_id] = snapshot
    _trim_cache()


def _trim_cache():
    total_messages = sum(len(v) for v in deleted_message_cache.values())

    while total_messages > MAX_CACHE_SIZE and deleted_message_cache:
        oldest_chat_id = next(iter(deleted_message_cache))
        oldest_msg_id = next(iter(deleted_message_cache[oldest_chat_id]))
        old_snapshot = deleted_message_cache[oldest_chat_id].pop(oldest_msg_id)
        _delete_cached_file(old_snapshot)

        if not deleted_message_cache[oldest_chat_id]:
            del deleted_message_cache[oldest_chat_id]

        total_messages -= 1


def _pop_cached(update, deleted_id):
    if isinstance(update, UpdateDeleteChannelMessages):
        chat_id = int(f"-100{update.channel_id}")
        snapshot = deleted_message_cache.get(chat_id, {}).pop(deleted_id, None)
        if snapshot and not deleted_message_cache[chat_id]:
            del deleted_message_cache[chat_id]
        return snapshot

    for chat_id in list(deleted_message_cache.keys()):
        snapshot = deleted_message_cache[chat_id].pop(deleted_id, None)
        if not snapshot:
            continue
        if not deleted_message_cache[chat_id]:
            del deleted_message_cache[chat_id]
        return snapshot

    return None


def _build_deleted_log(snapshot, deleted_id, text_limit=TEXT_PREVIEW_LIMIT) -> str:
    text = _clip(snapshot.get("text"), text_limit)
    deleted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cached_at = snapshot["timestamp"].strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "🗑️ <b>Pesan dihapus</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👤 Dari: {_build_sender_line(snapshot)}",
        f"💬 Chat: {_escape(snapshot.get('chat_title') or snapshot.get('chat_id'))}",
        f"🆔 User ID: <code>{_escape(snapshot.get('sender_id'))}</code>",
        f"✉️ Message ID: <code>{_escape(deleted_id)}</code>",
        f"🧩 Media: {_escape(snapshot.get('media_type') or 'Tidak ada')}",
        f"🕒 Masuk: {_escape(cached_at)}",
        f"🗑️ Dihapus: {_escape(deleted_at)}",
    ]

    for line in (
        _build_link("🔗 Profil", snapshot.get("user_link")),
        _build_link("🔗 Pesan", snapshot.get("message_link")),
    ):
        if line:
            lines.append(line)

    if text:
        lines.extend(["", "📝 <b>Teks:</b>", f"<pre>{_escape(text)}</pre>"])

    if snapshot.get("has_media") and not snapshot.get("file_path"):
        lines.extend(["", "⚠️ Media ada, tapi gagal disimpan sebelum pesan dihapus."])

    return "\n".join(lines)


def _build_media_caption(snapshot, deleted_id) -> str:
    text = _clip(snapshot.get("text"), CAPTION_TEXT_LIMIT)
    lines = [
        "🗑️ <b>Pesan dihapus</b>",
        f"👤 Dari: {_plain_sender_line(snapshot)}",
        f"🧩 Media: {_escape(snapshot.get('media_type') or 'Tidak ada')}",
        f"✉️ ID: <code>{_escape(deleted_id)}</code>",
    ]

    if text:
        lines.extend(["", f"📝 {_escape(text)}"])

    return "\n".join(lines)


async def _send_deleted_snapshot(client: TelegramClient, target, snapshot, deleted_id):
    file_path = snapshot.get("file_path")
    file_exists = bool(file_path and Path(file_path).exists())

    if file_exists:
        caption = _build_media_caption(snapshot, deleted_id)
        try:
            await client.send_file(target, file_path, caption=caption, parse_mode="html")
        except Exception as e:
            logger.warning("Kirim media anti-delete dengan caption gagal: %s", e)
            await client.send_file(target, file_path)
            text_log = _build_deleted_log(snapshot, deleted_id)
            await client.send_message(target, text_log, parse_mode="html", link_preview=False)
            return

        if len(_safe_text(snapshot.get("text"))) > CAPTION_TEXT_LIMIT:
            text_log = _build_deleted_log(snapshot, deleted_id)
            await client.send_message(target, text_log, parse_mode="html", link_preview=False)
        return

    text_log = _build_deleted_log(snapshot, deleted_id)
    await client.send_message(target, text_log, parse_mode="html", link_preview=False)


def _target_chats():
    targets = []
    if SAVE_TO_SAVED_MESSAGES:
        targets.append(SAVED_MESSAGES_TARGET)
    if FORWARD_CHAT_ID > 0:
        targets.append(FORWARD_CHAT_ID)
    return targets


async def setup_plugin(client: TelegramClient):
    """Setup anti-delete handler."""

    if not ANTI_DELETE_ENABLED:
        logger.info("Anti-delete module loaded (DISABLED)")
        return

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def cache_deleted_candidates(event):
        try:
            message = event.message
            if not (getattr(message, "media", None) or _safe_text(message.raw_text or message.text)):
                return

            snapshot = await _snapshot_message(client, event)
            _put_cache(snapshot)
        except Exception as e:
            logger.debug("Error caching anti-delete message: %s", e)

    @client.on(events.Raw)
    async def deleted_message_handler(update):
        try:
            if not isinstance(update, (UpdateDeleteMessages, UpdateDeleteChannelMessages)):
                return

            targets = _target_chats()
            if not targets:
                return

            for deleted_id in getattr(update, "messages", []):
                snapshot = _pop_cached(update, deleted_id)
                if not snapshot:
                    continue

                try:
                    sent = False
                    for target in targets:
                        try:
                            await _send_deleted_snapshot(client, target, snapshot, deleted_id)
                            sent = True
                        except Exception as e:
                            logger.error("Gagal kirim anti-delete %s ke %s: %s", deleted_id, target, e)

                    if sent:
                        logger.info("Pesan dihapus %s tersimpan oleh anti-delete", deleted_id)
                finally:
                    _delete_cached_file(snapshot)

        except Exception as e:
            logger.error("Error di anti-delete handler: %s", e)
            logger.exception(e)

    async def cleanup_old_messages():
        while True:
            try:
                await asyncio.sleep(3600)
                current_time = datetime.now()
                removed = 0

                for chat_id in list(deleted_message_cache.keys()):
                    for msg_id in list(deleted_message_cache[chat_id].keys()):
                        msg_age = (
                            current_time - deleted_message_cache[chat_id][msg_id]["timestamp"]
                        ).total_seconds()

                        if msg_age > MAX_CACHE_AGE_SECONDS:
                            snapshot = deleted_message_cache[chat_id].pop(msg_id)
                            _delete_cached_file(snapshot)
                            removed += 1

                    if not deleted_message_cache[chat_id]:
                        del deleted_message_cache[chat_id]

                if removed:
                    logger.info("Anti-delete cleanup removed %s cached messages", removed)

            except Exception as e:
                logger.error("Error di anti-delete cleanup: %s", e)

    asyncio.create_task(cleanup_old_messages())
    logger.info("Anti-delete module loaded")
