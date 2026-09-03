"""
RESTRICTED CHANNEL MODULE
Copy atau re-upload pesan dari chat restricted/no-forward.
"""

import asyncio
import logging
from pathlib import Path

from telethon import TelegramClient, events

from config import RESTRICTED_CHANNEL_ENABLED
from config import SAVED_MESSAGES_TARGET
from modules.feature_state import WATERMARK_LINE
from modules.helpers import (
    SAVED_CONTENT_MARKER,
    TOOK_BY_USERBOT,
    has_downloadable_message_media,
    inspect_message_extended_media,
)

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path("downloads")
ALBUM_WAIT_SECONDS = 0.8


def _is_restricted_message(message) -> bool:
    return bool(getattr(message, "noforwards", False))


def _is_paid_media(message) -> bool:
    # Paid media ditangani oleh paid_media_guard agar modul restricted
    # tidak mencoba mengunduh atau membuka konten Stars yang terkunci.
    return inspect_message_extended_media(message) is not None


def _saved_caption(source_title: str) -> str:
    lines = [
        "🔒 ANTI-FORWARD / PROTECTED CONTENT",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💬 Sumber: {source_title}",
    ]
    lines.extend(["", f"📥 {TOOK_BY_USERBOT}", WATERMARK_LINE, SAVED_CONTENT_MARKER])
    return "\n".join(lines)[:1024]


async def save_restricted_message_to_saved(
    client: TelegramClient,
    message,
    source_title: str,
) -> bool:
    """Simpan media protected saja ke Saved Messages milik akun."""

    if not has_downloadable_message_media(message) or _is_paid_media(message):
        return False

    caption = _saved_caption(source_title)

    DOWNLOAD_DIR.mkdir(exist_ok=True)
    file_path = await client.download_media(message, file=DOWNLOAD_DIR)
    if not file_path:
        logger.warning("Media protected dari %s tidak dapat di-download", source_title)
        return False

    try:
        await client.send_file(SAVED_MESSAGES_TARGET, file_path, caption=caption)
        return True
    finally:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            logger.debug("Gagal menghapus file sementara restricted: %s", file_path)


async def save_restricted_album_to_saved(
    client: TelegramClient,
    messages: list,
    source_title: str,
) -> bool:
    """Simpan semua media dalam satu album sebagai satu pesan ke Saved Messages."""

    messages = [
        message
        for message in messages
        if has_downloadable_message_media(message) and not _is_paid_media(message)
    ]
    if not messages:
        return False

    downloaded_files = []
    try:
        for message in messages:
            file_path = await client.download_media(message, file=DOWNLOAD_DIR)
            if file_path:
                downloaded_files.append(file_path)

        if not downloaded_files:
            logger.warning("Media album protected dari %s tidak dapat di-download", source_title)
            return False

        await client.send_file(
            SAVED_MESSAGES_TARGET,
            downloaded_files,
            caption=_saved_caption(source_title),
        )
        return True
    finally:
        for file_path in downloaded_files:
            try:
                Path(file_path).unlink(missing_ok=True)
            except Exception:
                logger.debug("Gagal menghapus file sementara album restricted: %s", file_path)


async def setup_plugin(client: TelegramClient):
    """Setup restricted channel handler."""

    if not RESTRICTED_CHANNEL_ENABLED:
        logger.info("Restricted channel module loaded (DISABLED)")
        return

    DOWNLOAD_DIR.mkdir(exist_ok=True)
    pending_albums = {}
    album_tasks = {}
    album_lock = asyncio.Lock()

    async def process_album(album_key, source_title):
        await asyncio.sleep(ALBUM_WAIT_SECONDS)
        async with album_lock:
            messages = pending_albums.pop(album_key, [])
            album_tasks.pop(album_key, None)

        saved = await save_restricted_album_to_saved(client, messages, source_title)
        if saved:
            logger.info(
                "Album restricted dari %s (%s media) disimpan ke Saved Messages",
                source_title,
                len(messages),
            )

    @client.on(events.NewMessage(incoming=True))
    async def restricted_handler(event):
        try:
            if event.is_private:
                return

            message = event.message
            if not has_downloadable_message_media(message):
                return

            if _is_paid_media(message):
                return

            chat = await event.get_chat()
            if not (
                _is_restricted_message(message)
                or bool(getattr(chat, "noforwards", False))
            ):
                return

            chat_title = getattr(chat, "title", None) or str(event.chat_id)

            grouped_id = getattr(message, "grouped_id", None)
            if grouped_id:
                album_key = (event.chat_id, grouped_id)
                async with album_lock:
                    pending_albums.setdefault(album_key, []).append(message)
                    if album_key not in album_tasks:
                        album_tasks[album_key] = asyncio.create_task(
                            process_album(album_key, chat_title)
                        )
                return

            saved = await save_restricted_message_to_saved(
                client,
                message,
                chat_title,
            )
            if saved:
                logger.info("Pesan restricted dari %s disimpan ke Saved Messages", chat_title)

        except Exception as e:
            logger.error("Error di restricted handler: %s", e)
            logger.exception(e)

    logger.info("Restricted channel module loaded")
