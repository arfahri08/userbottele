"""
LOGGER MODULE
Track pesan private yang diedit dan dihapus dengan cache memory.
"""

import asyncio
import html
import logging
from datetime import datetime

from telethon import TelegramClient, events
from telethon.tl.types import UpdateDeleteChannelMessages, UpdateDeleteMessages

from config import LOGGER_ENABLED, SAVED_MESSAGES_TARGET
from modules.commands import parse_event_command

logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = 1500
MAX_CACHE_AGE_SECONDS = 6 * 3600
TEXT_PREVIEW_LIMIT = 1200
message_cache = {}


def _is_private_event(event) -> bool:
    return bool(getattr(event, "is_private", False))


def _safe_text(value) -> str:
    return str(value or "").strip()


def _clip(value: str, limit: int = TEXT_PREVIEW_LIMIT) -> str:
    value = _safe_text(value)
    if len(value) <= limit:
        return value
    return f"{value[:limit]}... [dipotong]"


def _escape(value) -> str:
    return html.escape(str(value or ""), quote=False)


def _display_name(entity, fallback="Unknown"):
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


def _chat_link(chat_id, chat_username, sender_id=None, sender_username=None):
    if chat_username:
        return f"https://t.me/{chat_username}"
    if sender_username:
        return f"https://t.me/{sender_username}"
    if sender_id and (not chat_id or int(chat_id) == int(sender_id)):
        return f"tg://user?id={sender_id}"
    return None


def _media_label(message):
    media = getattr(message, "media", None)
    if not media:
        return "Tidak ada"
    return type(media).__name__


async def _snapshot_message(event):
    message = event.message
    sender = None
    chat = None

    try:
        sender = await event.get_sender()
    except Exception as e:
        logger.debug("Gagal ambil sender untuk cache: %s", e)

    try:
        chat = await event.get_chat()
    except Exception as e:
        logger.debug("Gagal ambil chat untuk cache: %s", e)

    sender_username = getattr(sender, "username", None)
    chat_username = getattr(chat, "username", None)
    sender_id = event.sender_id
    chat_id = event.chat_id
    msg_id = message.id

    return {
        "id": msg_id,
        "chat_id": chat_id,
        "chat_title": _display_name(chat, str(chat_id)),
        "chat_username": chat_username,
        "sender_id": sender_id,
        "sender_name": _display_name(sender, str(sender_id or "Unknown")),
        "sender_username": sender_username,
        "text": message.raw_text or message.text or "",
        "media": message.media is not None,
        "media_type": _media_label(message),
        "message_link": _message_link(chat_id, chat_username, msg_id),
        "chat_link": _chat_link(chat_id, chat_username, sender_id, sender_username),
        "user_link": _user_link(sender_id, sender_username),
        "timestamp": datetime.now(),
        "edited": False,
    }


def _put_cache(snapshot):
    chat_id = snapshot["chat_id"]
    msg_id = snapshot["id"]

    if chat_id not in message_cache:
        message_cache[chat_id] = {}

    message_cache[chat_id][msg_id] = snapshot

    total_messages = sum(len(v) for v in message_cache.values())
    while total_messages > MAX_CACHE_SIZE and message_cache:
        oldest_chat_id = next(iter(message_cache))
        oldest_msg_id = next(iter(message_cache[oldest_chat_id]))
        del message_cache[oldest_chat_id][oldest_msg_id]
        if not message_cache[oldest_chat_id]:
            del message_cache[oldest_chat_id]
        total_messages -= 1


def _get_cached(chat_id, msg_id):
    return message_cache.get(chat_id, {}).get(msg_id)


def _update_cached(chat_id, msg_id, snapshot):
    if chat_id not in message_cache:
        message_cache[chat_id] = {}
    message_cache[chat_id][msg_id] = snapshot


def _build_sender_line(snapshot):
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


def _build_link_line(label: str, url: str):
    if not url:
        return None
    escaped_url = _escape(url)
    return f"{label}: <a href=\"{escaped_url}\">{escaped_url}</a>"


def _build_edit_log(old_data, new_data):
    old_text = _clip(old_data.get("text")) or "[no text]"
    new_text = _clip(new_data.get("text")) or "[no text]"
    old_media = old_data.get("media_type") or "Tidak ada"
    new_media = new_data.get("media_type") or "Tidak ada"

    lines = [
        "<b>PESAN DIEDIT</b>",
        "====================",
        f"User: {_build_sender_line(new_data or old_data)}",
        f"Chat: {_escape(new_data.get('chat_title') or old_data.get('chat_title') or new_data.get('chat_id'))}",
        f"Chat ID: <code>{_escape(new_data.get('chat_id'))}</code>",
        f"User ID: <code>{_escape(new_data.get('sender_id'))}</code>",
        f"Message ID: <code>{_escape(new_data.get('id'))}</code>",
        f"Waktu edit: {_escape(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}",
    ]

    for line in (
        _build_link_line("Profil/user", new_data.get("user_link") or old_data.get("user_link")),
        _build_link_line("Chat langsung", new_data.get("chat_link") or old_data.get("chat_link")),
        _build_link_line("Link pesan", new_data.get("message_link") or old_data.get("message_link")),
    ):
        if line:
            lines.append(line)

    lines.extend(
        [
            "",
            "<b>SEBELUM EDIT:</b>",
            f"<pre>{_escape(old_text)}</pre>",
            f"Media lama: {_escape(old_media)}",
            "",
            "<b>SETELAH EDIT:</b>",
            f"<pre>{_escape(new_text)}</pre>",
            f"Media baru: {_escape(new_media)}",
        ]
    )

    if old_text == new_text and old_media == new_media:
        lines.append("")
        lines.append("Catatan: teks/media terlihat sama, kemungkinan yang berubah adalah formatting, link preview, atau metadata pesan.")

    return "\n".join(lines)


def _build_unknown_edit_log(new_data):
    new_text = _clip(new_data.get("text")) or "[no text]"
    lines = [
        "<b>PESAN DIEDIT</b>",
        "====================",
        f"User: {_build_sender_line(new_data)}",
        f"Chat: {_escape(new_data.get('chat_title') or new_data.get('chat_id'))}",
        f"Message ID: <code>{_escape(new_data.get('id'))}</code>",
        f"Waktu edit: {_escape(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}",
    ]

    for line in (
        _build_link_line("Profil/user", new_data.get("user_link")),
        _build_link_line("Chat langsung", new_data.get("chat_link")),
        _build_link_line("Link pesan", new_data.get("message_link")),
    ):
        if line:
            lines.append(line)

    lines.extend(
        [
            "",
            "<b>SEBELUM EDIT:</b>",
            "<pre>[tidak ada di cache, kemungkinan bot baru restart atau pesan terlalu lama]</pre>",
            "",
            "<b>SETELAH EDIT:</b>",
            f"<pre>{_escape(new_text)}</pre>",
            f"Media baru: {_escape(new_data.get('media_type') or 'Tidak ada')}",
        ]
    )
    return "\n".join(lines)


def _build_delete_log(deleted_msg, deleted_id):
    text = _clip(deleted_msg.get("text"), 1500) or "[no text content]"
    lines = [
        "<b>PESAN DIHAPUS</b>",
        "====================",
        f"User: {_build_sender_line(deleted_msg)}",
        f"Chat: {_escape(deleted_msg.get('chat_title') or deleted_msg.get('chat_id'))}",
        f"Message ID: <code>{_escape(deleted_id)}</code>",
        f"Dihapus: {_escape(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}",
        f"Dicache: {_escape(deleted_msg['timestamp'].strftime('%Y-%m-%d %H:%M:%S'))}",
    ]

    for line in (
        _build_link_line("Profil/user", deleted_msg.get("user_link")),
        _build_link_line("Chat langsung", deleted_msg.get("chat_link")),
        _build_link_line("Link pesan", deleted_msg.get("message_link")),
    ):
        if line:
            lines.append(line)

    lines.extend(
        [
            "",
            "<b>KONTEN PESAN:</b>",
            f"<pre>{_escape(text)}</pre>",
            f"Media: {_escape(deleted_msg.get('media_type') or 'Tidak ada')}",
        ]
    )
    return "\n".join(lines)


async def setup_plugin(client: TelegramClient):
    """Setup message logger."""

    if not LOGGER_ENABLED:
        logger.info("Logger module loaded (DISABLED)")
        return

    @client.on(events.NewMessage(incoming=True, func=_is_private_event))
    async def cache_messages(event):
        try:
            if parse_event_command(event):
                return
            snapshot = await _snapshot_message(event)
            _put_cache(snapshot)
        except Exception as e:
            logger.debug("Error caching message: %s", e)

    @client.on(events.MessageEdited(incoming=True, func=_is_private_event))
    async def track_edited_messages(event):
        try:
            chat_id = event.chat_id
            msg_id = event.message.id
            old_data = _get_cached(chat_id, msg_id)
            new_data = await _snapshot_message(event)

            if old_data:
                edit_log = _build_edit_log(old_data, new_data)
            else:
                edit_log = _build_unknown_edit_log(new_data)

            await client.send_message(SAVED_MESSAGES_TARGET, edit_log, parse_mode="html", link_preview=False)

            new_data["edited"] = True
            _update_cached(chat_id, msg_id, new_data)
            logger.info("Edit log sent untuk message %s", msg_id)

        except Exception as e:
            logger.error("Error tracking edited message: %s", e)

    @client.on(events.Raw)
    async def track_deleted_messages(update):
        try:
            if not isinstance(update, (UpdateDeleteMessages, UpdateDeleteChannelMessages)):
                return

            deleted_ids = getattr(update, "messages", [])
            for deleted_id in deleted_ids:
                for chat_id in list(message_cache.keys()):
                    if deleted_id not in message_cache[chat_id]:
                        continue

                    deleted_msg = message_cache[chat_id][deleted_id]
                    deletion_log = _build_delete_log(deleted_msg, deleted_id)
                    await client.send_message(SAVED_MESSAGES_TARGET, deletion_log, parse_mode="html", link_preview=False)
                    logger.info("Deletion log sent untuk message %s", deleted_id)

                    del message_cache[chat_id][deleted_id]
                    if not message_cache[chat_id]:
                        del message_cache[chat_id]
                    break

        except Exception as e:
            logger.debug("Error di deleted_messages handler: %s", e)

    async def cleanup_old_messages():
        while True:
            try:
                await asyncio.sleep(3600)
                current_time = datetime.now()
                messages_removed = 0

                for chat_id in list(message_cache.keys()):
                    for msg_id in list(message_cache[chat_id].keys()):
                        msg_age = (
                            current_time - message_cache[chat_id][msg_id]["timestamp"]
                        ).total_seconds()

                        if msg_age > MAX_CACHE_AGE_SECONDS:
                            del message_cache[chat_id][msg_id]
                            messages_removed += 1

                    if not message_cache[chat_id]:
                        del message_cache[chat_id]

                logger.info("Cleanup removed %s old cached messages", messages_removed)

            except Exception as e:
                logger.error("Error di cleanup: %s", e)

    asyncio.create_task(cleanup_old_messages())
    logger.info("Logger module loaded")


async def get_cache_stats():
    total_messages = sum(len(v) for v in message_cache.values())
    total_chats = len(message_cache)
    return {
        "total_messages": total_messages,
        "total_chats": total_chats,
        "max_cache": MAX_CACHE_SIZE,
        "usage_percent": (total_messages / MAX_CACHE_SIZE) * 100,
    }
