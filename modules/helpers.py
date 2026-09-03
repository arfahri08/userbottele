"""
HELPER FUNCTIONS
Utility functions untuk module Telethon.
"""

import logging

from telethon import utils

logger = logging.getLogger(__name__)

TOOK_BY_USERBOT = "Took by Userbot"
PAID_MEDIA_MARKER = "#paid_media"
SAVED_CONTENT_MARKER = "#saved_by_userbot"


def inspect_message_extended_media(message):
    """Classifier pusat untuk Telegram MessageMediaPaidMedia/MessageExtendedMedia."""

    media = getattr(message, "media", None)
    if type(media).__name__ != "MessageMediaPaidMedia":
        return None

    preview_items = []
    unlocked_items = []
    unlocked_media = []
    unknown_items = []

    for item in getattr(media, "extended_media", None) or []:
        item_type = type(item).__name__
        if item_type == "MessageExtendedMediaPreview":
            preview_items.append(item)
        elif item_type == "MessageExtendedMedia":
            unlocked_items.append(item)
            item_media = getattr(item, "media", None)
            if item_media is not None:
                unlocked_media.append(item_media)
        else:
            unknown_items.append(item)

    if preview_items and not unlocked_items:
        status = "LOCKED"
    elif unlocked_items and not preview_items:
        status = "UNLOCKED"
    elif preview_items or unlocked_items:
        status = "MIXED"
    else:
        status = "UNKNOWN"

    return {
        "status": status,
        "stars_amount": getattr(media, "stars_amount", None),
        "preview_items": preview_items,
        "unlocked_items": unlocked_items,
        "unlocked_media": unlocked_media,
        "unknown_items": unknown_items,
        "item_count": len(preview_items) + len(unlocked_items) + len(unknown_items),
    }


def is_message_extended_media(message) -> bool:
    return inspect_message_extended_media(message) is not None


def has_downloadable_message_media(message) -> bool:
    """True hanya untuk foto/dokumen Telegram, bukan teks atau web-page link preview."""

    if message is None:
        return False
    if getattr(message, "photo", None) or getattr(message, "document", None):
        return True
    return type(getattr(message, "media", None)).__name__ in {
        "MessageMediaPhoto",
        "MessageMediaDocument",
    }


def format_message_extended_media(inspection: dict) -> str:
    return (
        "⭐ Telegram MessageExtendedMedia terdeteksi\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔐 Status: {inspection['status']}\n"
        f"⭐ Harga: {inspection['stars_amount'] if inspection['stars_amount'] is not None else '?'} Stars\n"
        f"🖼️ Preview: {len(inspection['preview_items'])}\n"
        f"✅ Full unlocked: {len(inspection['unlocked_items'])}\n"
        f"📦 Total item: {inspection['item_count']}\n\n"
        "Gunakan .paidfull <link> untuk full yang sudah unlocked, atau "
        ".paidpreview <link> untuk preview manual."
    )


def extract_paid_preview_images(message):
    """Ambil byte thumbnail preview yang memang diberikan Telegram sebelum pembelian."""

    previews = []
    inspection = inspect_message_extended_media(message)
    if not inspection:
        return previews

    for index, item in enumerate(inspection["preview_items"], start=1):
        thumb = getattr(item, "thumb", None)
        raw = getattr(thumb, "bytes", None)
        if not raw:
            continue

        thumb_type = type(thumb).__name__
        if thumb_type == "PhotoStrippedSize":
            data = utils.stripped_photo_to_jpg(bytes(raw))
            extension = ".jpg"
        else:
            data = bytes(raw)
            if data.startswith(b"\x89PNG\r\n\x1a\n"):
                extension = ".png"
            elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
                extension = ".webp"
            else:
                extension = ".jpg"

        previews.append(
            {
                "data": data,
                "filename": f"paid_preview_{index}{extension}",
                "width": getattr(item, "w", None),
                "height": getattr(item, "h", None),
                "video_duration": getattr(item, "video_duration", None),
            }
        )

    return previews


def get_chat_id_from_event(event):
    return event.chat_id


def format_message_log(event) -> str:
    try:
        sender = event.sender
        sender_name = sender.first_name or sender.username or "Unknown"
        text = event.message.text or "[media]"
        return f"{sender_name}: {text[:50]}"
    except Exception as e:
        logger.error("Error formatting message log: %s", e)
        return "Message"


async def check_permissions(client, chat_id: int) -> bool:
    try:
        await client.get_entity(chat_id)
        return True
    except Exception:
        return False


async def get_display_name(client, user_id: int) -> str:
    try:
        user = await client.get_entity(user_id)
        return user.first_name or user.username or str(user_id)
    except Exception:
        return str(user_id)
