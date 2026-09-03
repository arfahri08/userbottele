"""
TELEGRAM MEDIA LINK FETCHER

Ketika owner mengirim link pesan Telegram yang berisi foto/video/file,
userbot mengambil media dari pesan sumber yang memang bisa diakses akun
dan mengirimkannya sebagai reply ke chat tempat link ditempel.

Tidak mencoba membuka paid media/Stars yang terkunci. Thumbnail preview yang
Telegram sediakan dapat disimpan dengan label PREVIEW. Konten dari chat yang
protected/no-forwards hanya disimpan ke Saved Messages milik akun.
"""

import io
import logging
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from telethon import TelegramClient, events, utils

from config import SAVED_MESSAGES_TARGET, TELEGRAM_MEDIA_LINK_ENABLED
from modules.commands import parse_event_command
from modules.feature_state import WATERMARK_LINE
from modules.helpers import (
    PAID_MEDIA_MARKER,
    SAVED_CONTENT_MARKER,
    TOOK_BY_USERBOT,
    extract_paid_preview_images,
    has_downloadable_message_media,
    inspect_message_extended_media,
)
from modules.restricted import save_restricted_message_to_saved

logger = logging.getLogger(__name__)

DOWNLOAD_ROOT = Path("downloads") / "telegram_media_links"
MAX_LINKS_PER_MESSAGE = 3

TELEGRAM_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:t\.me|telegram\.me)/[^\s<>()]+",
    re.IGNORECASE,
)
PUBLIC_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
RESERVED_PATHS = {
    "addstickers",
    "addemoji",
    "blog",
    "c",
    "confirmphone",
    "contact",
    "faq",
    "iv",
    "joinchat",
    "login",
    "proxy",
    "s",
    "setlanguage",
    "share",
    "socks",
}


def _clean_url(value: str) -> str:
    return str(value or "").strip().rstrip(").,!?]}>\"'")


def _parse_message_link(url: str):
    """Parse public t.me links and private /c/ links into a source target."""

    clean = _clean_url(url)
    parsed = urlparse(clean)

    host = (parsed.hostname or "").lower()
    if host not in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}:
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None

    first = parts[0]

    # Private supergroup/channel links:
    # https://t.me/c/<internal_channel_id>/<message_id>
    # Forum/topic links can contain another numeric segment; the final
    # numeric segment is treated as the actual message id.
    if first.lower() == "c":
        if len(parts) < 3 or not parts[1].isdigit():
            return None

        numeric_parts = [part for part in parts[2:] if part.isdigit()]
        if not numeric_parts:
            return None

        internal_id = parts[1]
        message_id = int(numeric_parts[-1])

        return {
            "kind": "private_channel",
            "peer": int(f"-100{internal_id}"),
            "message_id": message_id,
            "url": clean,
        }

    # Public channel/group link:
    # https://t.me/<username>/<message_id>
    if first.lower() in RESERVED_PATHS:
        return None
    if not PUBLIC_USERNAME_RE.fullmatch(first):
        return None

    numeric_parts = [part for part in parts[1:] if part.isdigit()]
    if not numeric_parts:
        return None

    return {
        "kind": "public",
        "peer": first,
        "message_id": int(numeric_parts[-1]),
        "url": clean,
    }


def _extract_targets(text: str):
    targets = []
    seen = set()

    for match in TELEGRAM_URL_RE.finditer(text or ""):
        parsed = _parse_message_link(match.group(0))
        if not parsed:
            continue

        key = (parsed["kind"], parsed["peer"], parsed["message_id"])
        if key in seen:
            continue

        seen.add(key)
        targets.append(parsed)

        if len(targets) >= MAX_LINKS_PER_MESSAGE:
            break

    return targets


async def _resolve_source_peer(client: TelegramClient, target):
    """Resolve a public username or cached private /c/ channel peer."""

    peer = target["peer"]

    try:
        return await client.get_input_entity(peer)
    except ValueError:
        # /c/ links have no username. If its entity cache is cold, refresh
        # dialogs once and match the marked Telethon peer ID.
        if target["kind"] != "private_channel":
            raise

        async for dialog in client.iter_dialogs():
            try:
                if utils.get_peer_id(dialog.entity) == peer:
                    return dialog.input_entity
            except Exception:
                continue

        raise


def _is_paid_media(message) -> bool:
    return inspect_message_extended_media(message) is not None


def _paid_media_details(message):
    inspection = inspect_message_extended_media(message)
    if not inspection:
        return "UNKNOWN", None
    return inspection["status"], inspection["stars_amount"]


def _unlocked_paid_media(message):
    inspection = inspect_message_extended_media(message)
    return list(inspection["unlocked_media"]) if inspection else []


def _build_paid_media_notice(message, source_url: str | None) -> str:
    status, stars = _paid_media_details(message)
    lines = [
        "⭐ PAID MEDIA / TELEGRAM STARS",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if stars is not None:
        lines.append(f"⭐ Harga: {stars} Stars")

    lines.append(f"🔐 Status: {status}")
    if status in {"UNLOCKED", "MIXED"}:
        lines.append("✅ Media berbayar ini sudah terbuka secara sah pada akun.")
    else:
        lines.append(
            "⚠️ Media ini ditandai sebagai konten berbayar. Bot tidak membuka atau melewati paywall Telegram."
        )

    preview_rows = []
    inspection = inspect_message_extended_media(message)
    preview_items = inspection["preview_items"] if inspection else []
    for index, item in enumerate(preview_items, start=1):
        details = []
        width = getattr(item, "w", None)
        height = getattr(item, "h", None)
        duration = getattr(item, "video_duration", None)
        if width and height:
            details.append(f"{width}x{height}")
        if duration is not None:
            details.append(f"video {duration} detik")
        preview_rows.append(f"🖼️ Preview {index}: {', '.join(details) if details else 'metadata terbatas'}")

    if preview_rows:
        lines.extend(preview_rows)
        if source_url:
            lines.append(f"🛠️ Ambil preview secara manual: .paidpreview {source_url}")

    if source_url:
        lines.append(f"🔗 Link: {source_url}")
    lines.extend([f"📥 {TOOK_BY_USERBOT}", "", WATERMARK_LINE, PAID_MEDIA_MARKER])
    return "\n".join(lines)


def _build_paid_preview_notice(message, source_url: str | None, preview: dict) -> str:
    status, stars = _paid_media_details(message)
    lines = [
        "🖼️ PREVIEW PAID MEDIA / TELEGRAM STARS",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if stars is not None:
        lines.append(f"⭐ Harga: {stars} Stars")
    lines.append(f"🔐 Status media penuh: {status}")

    width = preview.get("width")
    height = preview.get("height")
    if width and height:
        lines.append(f"📐 Preview: {width}x{height}")
    if preview.get("video_duration") is not None:
        lines.append(f"🎬 Durasi video sumber: {preview['video_duration']} detik")

    lines.append(
        "ℹ️ Ini hanya thumbnail/spoiler preview yang disediakan Telegram, bukan file penuh."
    )
    if source_url:
        lines.append(f"🔗 Link: {source_url}")
    lines.extend([f"📥 {TOOK_BY_USERBOT}", "", WATERMARK_LINE, PAID_MEDIA_MARKER])
    return "\n".join(lines)[:1024]


async def _send_paid_media_to_target(
    client: TelegramClient,
    event,
    message,
    target,
    saved_only: bool = False,
    mode: str = "full",
) -> dict:
    source_url = None if saved_only else target["url"]
    caption = _build_paid_media_notice(message, source_url)
    unlocked_media = _unlocked_paid_media(message) if mode in {"auto", "full"} else []
    preview_images = extract_paid_preview_images(message) if mode == "preview" else []
    destination = SAVED_MESSAGES_TARGET if saved_only else event.chat_id
    reply_to = None if saved_only else event.message.id

    unlocked_sent = 0
    preview_sent = 0
    job_dir = DOWNLOAD_ROOT / f"paid_{event.chat_id}_{event.message.id}"
    try:
        for item_index, media in enumerate(unlocked_media, start=1):
            try:
                await client.send_file(
                    destination,
                    media,
                    caption=caption,
                    reply_to=reply_to,
                )
                unlocked_sent += 1
                continue
            except Exception as exc:
                logger.info(
                    "Reuse paid media unlocked ditolak/gagal: %s; mencoba re-upload",
                    exc,
                )

            try:
                job_dir.mkdir(parents=True, exist_ok=True)
                file_path = await client.download_media(
                    media,
                    file=str(job_dir / f"item_{item_index}_"),
                )
                if not file_path:
                    continue

                await client.send_file(
                    destination,
                    file_path,
                    caption=caption,
                    reply_to=reply_to,
                )
                unlocked_sent += 1
            except Exception as exc:
                logger.info("Re-upload paid media unlocked ditolak/gagal: %s", exc)

        for preview in preview_images:
            preview_file = io.BytesIO(preview["data"])
            preview_file.name = preview["filename"]
            preview_caption = _build_paid_preview_notice(message, source_url, preview)
            try:
                await client.send_file(
                    destination,
                    preview_file,
                    caption=preview_caption,
                    reply_to=reply_to,
                )
                preview_sent += 1
            except Exception as exc:
                logger.info("Pengiriman thumbnail preview paid media gagal: %s", exc)
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)

    if not unlocked_sent and not preview_sent:
        status, _ = _paid_media_details(message)
        if mode == "preview":
            failure_notice = (
                f"{caption}\n\n⚠️ Telegram tidak memberikan byte thumbnail preview yang dapat dikirim."
            )
        elif status == "LOCKED":
            failure_notice = (
                f"{caption}\n\n⛔ File penuh masih LOCKED dan belum diberikan Telegram ke akun."
            )
        else:
            failure_notice = (
                f"{caption}\n\n⚠️ Media sudah terbuka, tetapi Telegram menolak pengiriman ulang."
            )
        if saved_only:
            await client.send_message(SAVED_MESSAGES_TARGET, failure_notice, link_preview=False)
        else:
            await event.reply(failure_notice, link_preview=False)

    return {"unlocked": unlocked_sent, "preview": preview_sent}


async def _is_protected_source(client: TelegramClient, source_peer, message) -> bool:
    if bool(getattr(message, "noforwards", False)):
        return True

    try:
        entity = await client.get_entity(source_peer)
        return bool(getattr(entity, "noforwards", False))
    except Exception:
        # Failure to fetch entity metadata is not itself proof that content is
        # protected. Telegram will still enforce access when media is fetched.
        return False


async def _source_title(client: TelegramClient, source_peer) -> str:
    try:
        entity = await client.get_entity(source_peer)
        return (
            getattr(entity, "title", None)
            or getattr(entity, "first_name", None)
            or getattr(entity, "username", None)
            or str(source_peer)
        )
    except Exception:
        return str(source_peer)


async def _fetch_source_message(client: TelegramClient, target):
    source_peer = await _resolve_source_peer(client, target)
    message = await client.get_messages(source_peer, ids=target["message_id"])

    if isinstance(message, (list, tuple)):
        message = message[0] if message else None

    return source_peer, message


async def _send_media_to_target(client: TelegramClient, event, message, job_index: int):
    """
    Prefer reusing Telegram's existing media handle. If that fails, download
    the accessible media and re-upload it. No original source link is placed
    in the caption, avoiding recursive auto-detection.
    """

    # Photos/documents cover ordinary Telegram photos, videos, GIFs, audio,
    # voice notes, stickers, and files.
    if not (getattr(message, "photo", None) or getattr(message, "document", None)):
        return False, "Pesan sumber tidak berisi foto, video, audio, atau file yang bisa disalin."

    try:
        await client.send_file(
            event.chat_id,
            message.media,
            reply_to=event.message.id,
        )
        return True, None
    except Exception as direct_error:
        logger.warning(
            "Direct media reuse gagal untuk message %s: %s; mencoba download/re-upload",
            getattr(message, "id", "?"),
            direct_error,
        )

    job_dir = DOWNLOAD_ROOT / f"{event.chat_id}_{event.message.id}_{job_index}"
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        file_path = await client.download_media(
            message,
            file=str(job_dir) + "/",
        )
        if not file_path:
            return False, "Telegram tidak memberikan file media untuk pesan tersebut."

        await client.send_file(
            event.chat_id,
            file_path,
            reply_to=event.message.id,
        )
        return True, None
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


async def _handle_target(
    client: TelegramClient,
    event,
    target,
    index: int,
    paid_mode: str = "auto",
):
    try:
        source_peer, message = await _fetch_source_message(client, target)

        if not message:
            await event.reply(
                "Tidak bisa menemukan pesan dari link itu. Pastikan akun ini masih punya akses ke channel/grup sumber."
            )
            return

        is_protected = await _is_protected_source(client, source_peer, message)

        if _is_paid_media(message):
            sent = await _send_paid_media_to_target(
                client,
                event,
                message,
                target,
                saved_only=is_protected,
                mode=paid_mode,
            )
            if is_protected:
                status, _ = _paid_media_details(message)
                if sent["unlocked"] and sent["preview"]:
                    result = "media Stars unlocked dan preview disimpan hanya ke Saved Messages"
                elif sent["unlocked"]:
                    result = "media Stars unlocked disimpan hanya ke Saved Messages"
                elif sent["preview"]:
                    result = "preview Stars disimpan hanya ke Saved Messages"
                elif status == "LOCKED":
                    result = "info Stars disimpan; byte preview tidak tersedia"
                else:
                    result = "info Stars disimpan; pengiriman media gagal"
                logger.info("Sumber anti-forward: %s", result)
            return

        if paid_mode in {"full", "preview"}:
            await event.reply("Pesan pada link itu bukan Telegram Stars/Paid Media.")
            return

        if is_protected:
            if not has_downloadable_message_media(message):
                logger.info("Link anti-forward teks-only dilewati")
                return

            source_title = await _source_title(client, source_peer)
            saved = await save_restricted_message_to_saved(
                client,
                message,
                source_title,
            )
            if saved:
                logger.info("Media link anti-forward disimpan hanya ke Saved Messages")
            else:
                logger.warning("Media link anti-forward gagal disimpan ke Saved Messages")
            return

        ok, error_text = await _send_media_to_target(client, event, message, index)
        if not ok:
            await event.reply(error_text or "Media tidak dapat dikirim.")

    except ValueError:
        await event.reply(
            "Tidak bisa membuka link Telegram itu. Untuk link /c/, akun ini harus sudah menjadi anggota dan chat-nya pernah termuat di session."
        )
    except Exception as exc:
        logger.error("Telegram media-link fetch gagal: %s", exc)
        logger.exception(exc)
        await event.reply(f"Gagal mengambil media dari link Telegram: {type(exc).__name__}")


async def setup_plugin(client: TelegramClient):
    """Setup outgoing Telegram message-link detector."""

    if not TELEGRAM_MEDIA_LINK_ENABLED:
        logger.info("Telegram media-link fetcher loaded (DISABLED)")
        return

    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

    @client.on(events.NewMessage(outgoing=True))
    async def telegram_media_link_handler(event):
        text = event.message.raw_text or ""
        if PAID_MEDIA_MARKER in text or SAVED_CONTENT_MARKER in text:
            return

        command_parts = parse_event_command(event)
        # Link biasa hanya dideteksi otomatis di private chat/Saved Messages.
        # Command eksplisit tetap boleh dipakai di chat lain.
        if not event.is_private and not command_parts:
            return

        paid_mode = "auto"
        target_text = text

        if command_parts:
            command = command_parts[0]
            if command not in {"paidfull", "paidpreview"}:
                return

            paid_mode = "full" if command == "paidfull" else "preview"
            target_text = " ".join(command_parts[1:])

        targets = _extract_targets(target_text)
        if command_parts and not targets:
            reply = await event.get_reply_message()
            if reply:
                targets = _extract_targets(reply.raw_text or reply.text or "")

        if not targets:
            if command_parts:
                await event.reply(
                    "Format: .paidfull <link> atau .paidpreview <link>. Bisa juga reply pesan yang berisi link."
                )
            return

        logger.info(
            "Telegram media-link detector menemukan %s link pada chat %s (mode=%s)",
            len(targets),
            event.chat_id,
            paid_mode,
        )

        for index, target in enumerate(targets, start=1):
            await _handle_target(client, event, target, index, paid_mode=paid_mode)

    logger.info("Telegram media-link fetcher loaded")
