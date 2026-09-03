"""
PAID MEDIA GUARD

Mendeteksi Telegram paid media (Stars) tanpa mencoba membeli, membuka,
men-download, atau melewati paywall. Pesan asli dicoba di-forward secara
native ke Saved Messages sehingga aturan akses Telegram tetap berlaku.

Jika media sudah dibeli secara sah pada akun ini, media disimpan dengan caption.
Preview locked tidak dikirim otomatis; pemilik memilihnya lewat command manual.
"""

import html
import logging
import shutil
from pathlib import Path

from telethon import TelegramClient, events, utils

from config import (
    PAID_MEDIA_GUARD_ENABLED,
    PAID_MEDIA_FORWARD_TO_SAVED,
    SAVED_MESSAGES_TARGET,
)
from modules.feature_state import WATERMARK_LINE
from modules.helpers import PAID_MEDIA_MARKER, TOOK_BY_USERBOT, inspect_message_extended_media

logger = logging.getLogger(__name__)

_seen_states = set()
DOWNLOAD_ROOT = Path("downloads") / "paid_media_guard"


def _class_name(value) -> str:
    return type(value).__name__ if value is not None else ""


def _is_paid_media(message) -> bool:
    return inspect_message_extended_media(message) is not None


def _paid_state(message):
    inspection = inspect_message_extended_media(message)
    if not inspection:
        return "UNKNOWN", 0, 0, 0
    return (
        inspection["status"],
        len(inspection["preview_items"]),
        len(inspection["unlocked_items"]),
        len(inspection["unknown_items"]),
    )


def _escape(value) -> str:
    return html.escape(str(value or ""), quote=False)


def _message_link(chat_id, chat_username, msg_id):
    if chat_username:
        return f"https://t.me/{chat_username}/{msg_id}"

    chat_id_text = str(chat_id or "")
    if chat_id_text.startswith("-100"):
        return f"https://t.me/c/{chat_id_text[4:]}/{msg_id}"

    return None


def _preview_metadata(message):
    inspection = inspect_message_extended_media(message)
    rows = []
    preview_items = inspection["preview_items"] if inspection else []
    for index, item in enumerate(preview_items, 1):

        width = getattr(item, "w", None)
        height = getattr(item, "h", None)
        duration = getattr(item, "video_duration", None)
        bits = []
        if width and height:
            bits.append(f"{width}x{height}")
        if duration is not None:
            bits.append(f"video {duration}s")
        rows.append(f"Preview {index}: {', '.join(bits) if bits else 'metadata terbatas'}")

    return rows


async def _chat_info(client: TelegramClient, message):
    chat_id = None
    chat = None

    try:
        peer = getattr(message, "peer_id", None)
        if peer is not None:
            chat_id = utils.get_peer_id(peer)
            chat = await client.get_entity(peer)
    except Exception as exc:
        logger.debug("Gagal resolve chat paid media: %s", exc)

    title = (
        getattr(chat, "title", None)
        or getattr(chat, "first_name", None)
        or getattr(chat, "username", None)
        or str(chat_id or "Unknown")
    )
    username = getattr(chat, "username", None) if chat else None
    is_protected = bool(
        getattr(message, "noforwards", False)
        or (chat is not None and getattr(chat, "noforwards", False))
    )
    return chat_id, title, username, is_protected


async def _native_forward_to_saved(client: TelegramClient, message) -> bool:
    if not PAID_MEDIA_FORWARD_TO_SAVED:
        return False

    try:
        await client.forward_messages(SAVED_MESSAGES_TARGET, message)
        return True
    except Exception as exc:
        logger.info("Native forward paid media ke Saved Messages ditolak/gagal: %s", exc)
        return False


def _unlocked_paid_media(message):
    inspection = inspect_message_extended_media(message)
    return list(inspection["unlocked_media"]) if inspection else []


def _paid_media_caption(chat_title, stars, state, link) -> str:
    lines = [
        "⭐ PAID MEDIA / TELEGRAM STARS",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💬 Sumber: {chat_title}",
        f"⭐ Harga: {stars if stars is not None else '?'} Stars",
        f"🔐 Status: {state}",
    ]
    if link:
        lines.append(f"🔗 Link: {link}")
    lines.extend([f"📥 {TOOK_BY_USERBOT}", "", WATERMARK_LINE, PAID_MEDIA_MARKER])
    return "\n".join(lines)[:1024]


async def _save_unlocked_paid_to_saved(client: TelegramClient, message, caption: str) -> int:
    if not PAID_MEDIA_FORWARD_TO_SAVED:
        return 0

    unlocked_media = _unlocked_paid_media(message)
    if not unlocked_media:
        return 0

    saved_count = 0
    job_dir = DOWNLOAD_ROOT / f"message_{getattr(message, 'id', 'unknown')}"
    try:
        for index, media in enumerate(unlocked_media, start=1):
            try:
                await client.send_file(SAVED_MESSAGES_TARGET, media, caption=caption)
                saved_count += 1
                continue
            except Exception as exc:
                logger.info("Reuse paid media ke Saved Messages gagal: %s", exc)

            try:
                job_dir.mkdir(parents=True, exist_ok=True)
                file_path = await client.download_media(
                    media,
                    file=str(job_dir / f"item_{index}_"),
                )
                if not file_path:
                    continue
                await client.send_file(SAVED_MESSAGES_TARGET, file_path, caption=caption)
                saved_count += 1
            except Exception as exc:
                logger.info("Re-upload paid media unlocked ke Saved Messages gagal: %s", exc)
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)

    return saved_count


async def _handle_paid_message(client: TelegramClient, message, source: str):
    if not message or not _is_paid_media(message):
        return

    state, preview_count, unlocked_count, unknown_count = _paid_state(message)
    chat_id, chat_title, chat_username, is_protected = await _chat_info(client, message)
    msg_id = getattr(message, "id", None)
    key = (chat_id, msg_id, state)
    if key in _seen_states:
        return
    _seen_states.add(key)

    media = getattr(message, "media", None)
    stars = getattr(media, "stars_amount", None)
    link = None if is_protected else _message_link(chat_id, chat_username, msg_id)
    caption = _paid_media_caption(chat_title, stars, state, link)
    saved_count = await _save_unlocked_paid_to_saved(client, message, caption)
    forwarded = False
    if not saved_count:
        forwarded = await _native_forward_to_saved(client, message)

    if state == "LOCKED":
        explanation = (
            "Konten masih terkunci. Userbot tidak mencoba membuka atau mengunduh media berbayar; "
            "yang tersedia sebelum pembelian hanyalah preview/metadata yang Telegram berikan."
        )
    elif state == "UNLOCKED":
        explanation = (
            "Telegram menandai media ini sudah terbuka untuk akun saat ini. "
            "Userbot menyimpannya ke Saved Messages dengan penanda; tidak ada upaya membuka paywall."
        )
    else:
        explanation = "Status paid media tidak dapat dipastikan sepenuhnya dari update ini."

    lines = [
        "⭐ <b>PAID MEDIA TERDETEKSI</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💬 Sumber: {_escape(chat_title)}",
        f"🆔 Chat ID: <code>{_escape(chat_id)}</code>",
        f"✉️ Message ID: <code>{_escape(msg_id)}</code>",
        f"⭐ Harga: {_escape(stars if stars is not None else '?')} Stars",
        f"🔐 Status: <b>{_escape(state)}</b>",
        f"🖼️ Preview locked: {preview_count}",
        f"✅ Media unlocked: {unlocked_count}",
    ]

    if unknown_count:
        lines.append(f"❔ Item lain: {unknown_count}")

    if link:
        lines.append(f'🔗 Pesan: <a href="{_escape(link)}">{_escape(link)}</a>')

    if saved_count:
        lines.append(f"📥 Saved Messages dengan caption: {saved_count} media")
    else:
        lines.append(
            f"📥 Native forward ke Saved Messages: {'berhasil' if forwarded else 'tidak tersedia/gagal'}"
        )

    preview_rows = _preview_metadata(message)
    if preview_rows:
        lines.extend(["", "Preview metadata:", *[_escape(row) for row in preview_rows]])

    lines.extend(
        [
            "",
            _escape(explanation),
            f"Sumber deteksi: {_escape(source)}",
            f"📥 {_escape(TOOK_BY_USERBOT)}",
            "",
            _escape(WATERMARK_LINE),
            PAID_MEDIA_MARKER,
        ]
    )

    try:
        await client.send_message(SAVED_MESSAGES_TARGET, "\n".join(lines), parse_mode="html", link_preview=False)
    except Exception:
        logger.exception("Gagal mengirim log paid media")


async def setup_plugin(client: TelegramClient):
    """Setup paid-media detector yang tidak melewati paywall."""

    if not PAID_MEDIA_GUARD_ENABLED:
        logger.info("Paid media guard module loaded (DISABLED)")
        return

    @client.on(events.NewMessage(incoming=True))
    async def paid_media_new_message(event):
        try:
            await _handle_paid_message(client, event.message, "new_message")
        except Exception:
            logger.exception("Paid media new-message handler gagal")

    @client.on(events.Raw)
    async def paid_media_update(update):
        # Telegram mengirim UpdateMessageExtendedMedia setelah paid media
        # berhasil dibeli. Kita hanya bereaksi terhadap update tersebut.
        if _class_name(update) != "UpdateMessageExtendedMedia":
            return

        try:
            peer = getattr(update, "peer", None)
            msg_id = getattr(update, "msg_id", None)
            if peer is None or msg_id is None:
                return

            message = await client.get_messages(peer, ids=msg_id)
            await _handle_paid_message(client, message, "update_after_unlock")
        except Exception as exc:
            logger.info("Gagal memproses update paid media: %s", exc)

    logger.info("Paid media guard module loaded")
