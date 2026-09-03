"""
ANTI VIEW-ONCE MODULE
Simpan media view-once dari private chat.
"""

import logging
from pathlib import Path

from telethon import TelegramClient, events

from config import (
    ANTI_VIEWONCE_ENABLED,
    FORWARD_CHAT_ID,
    SAVE_TO_SAVED_MESSAGES,
    SAVED_MESSAGES_TARGET,
)
from modules.helpers import inspect_message_extended_media

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path("downloads")


def _is_view_once(message) -> bool:
    # Paid Media selalu diprioritaskan ke paid_media_guard agar tidak salah
    # diklasifikasikan sebagai view-once hanya karena atribut media/TTL.
    if inspect_message_extended_media(message):
        return False

    if not getattr(message, "media", None):
        return False

    if getattr(message, "ttl_seconds", None):
        return True

    if getattr(message.media, "ttl_seconds", None):
        return True

    message_repr = repr(message).lower()
    return "ttl_seconds" in message_repr or "ttl_period" in message_repr


async def _save_media(client: TelegramClient, message, sender_name: str):
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    file_path = await client.download_media(message, file=DOWNLOAD_DIR)
    if not file_path:
        logger.error("Failed to download view-once media")
        return

    caption = f"View-Once dari {sender_name}"
    if message.text:
        caption += f"\n\nCaption: {message.text}"

    try:
        if SAVE_TO_SAVED_MESSAGES:
            await client.send_file(SAVED_MESSAGES_TARGET, file_path, caption=caption)
            logger.info("View-once dari %s disimpan ke Saved Messages", sender_name)

        if FORWARD_CHAT_ID > 0:
            await client.send_file(FORWARD_CHAT_ID, file_path, caption=caption)
            logger.info("View-once dari %s dikirim ke chat tujuan", sender_name)

    finally:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass


async def setup_plugin(client: TelegramClient):
    """Setup anti-viewonce handler."""

    if not ANTI_VIEWONCE_ENABLED:
        logger.info("Anti-viewonce module loaded (DISABLED)")
        return

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def anti_viewonce_handler(event):
        try:
            message = event.message
            if not _is_view_once(message):
                return

            sender = await event.get_sender()
            sender_name = sender.first_name or sender.username or "Unknown"
            logger.info("Menangkap view-once dari %s", sender_name)

            await _save_media(client, message, sender_name)

        except Exception as e:
            logger.error("Error di anti-viewonce handler: %s", e)
            logger.exception(e)

    logger.info("Anti-viewonce module loaded")
