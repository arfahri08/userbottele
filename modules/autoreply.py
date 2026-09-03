"""
AUTO-REPLY MODULE
Balasan otomatis acak untuk pesan private.
"""

import json
import logging
import random
from pathlib import Path

from telethon import TelegramClient, events

from modules.commands import parse_event_command
from modules.feature_state import WATERMARK_LINE, is_feature_enabled

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
REPLIES_FILE = DATA_DIR / "autoreplies.json"
LIST_PREVIEW_LIMIT = 40
REPLY_PREVIEW_LIMIT = 120

DEFAULT_REPLIES = (
    "Lagi belum bisa bales sekarang, nanti aku balas ya.",
    "Pesanmu sudah masuk. Aku cek nanti kalau sudah sempat.",
    "Aku lagi off sebentar, nanti aku respon.",
    "Sebentar ya, aku lagi tidak pegang Telegram.",
    "Terima kasih sudah chat. Nanti aku kabari lagi.",
    "Aku lagi sibuk dulu, pesannya aman kebaca nanti.",
    "Belum bisa bales sekarang. Ditunggu ya.",
    "Aku sedang away, nanti aku lanjut balas.",
    "Pesan diterima. Aku balas begitu ada waktu.",
    "Maaf, aku belum bisa respon cepat sekarang.",
)


def _clean_reply(text: str) -> str:
    return (text or "").strip()


def _clip_reply(text: str, limit: int = REPLY_PREVIEW_LIMIT) -> str:
    text = _clean_reply(text).replace("\n", " ")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [dipotong]"


def _reply_payload(replies):
    return {"replies": list(replies)}


def _write_replies(replies):
    DATA_DIR.mkdir(exist_ok=True)
    temp_file = REPLIES_FILE.with_suffix(".json.tmp")
    temp_file.write_text(
        json.dumps(_reply_payload(replies), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_file.replace(REPLIES_FILE)


def _ensure_replies_file():
    if REPLIES_FILE.exists():
        return
    _write_replies(DEFAULT_REPLIES)


def _load_replies():
    if not REPLIES_FILE.exists():
        _ensure_replies_file()
        return list(DEFAULT_REPLIES)

    try:
        data = json.loads(REPLIES_FILE.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Gagal membaca daftar autoreply, pakai default.", exc_info=True)
        return list(DEFAULT_REPLIES)

    if isinstance(data, dict):
        data = data.get("replies", [])

    if not isinstance(data, list):
        return list(DEFAULT_REPLIES)

    replies = [_clean_reply(item) for item in data if isinstance(item, str)]
    return [reply for reply in replies if reply]


def _save_replies(replies):
    _write_replies(replies)


def _add_reply(text: str):
    reply = _clean_reply(text)
    replies = _load_replies()

    if not reply:
        return False, "empty", len(replies)

    if any(saved.casefold() == reply.casefold() for saved in replies):
        return False, "duplicate", len(replies)

    replies.append(reply)
    _save_replies(replies)
    return True, "added", len(replies)


def _delete_reply(target: str):
    target = _clean_reply(target)
    replies = _load_replies()

    if not target:
        return False, "empty", None, len(replies)

    deleted_reply = None

    if target.isdigit():
        index = int(target) - 1
        if index < 0 or index >= len(replies):
            return False, "not_found", None, len(replies)
        deleted_reply = replies.pop(index)
    else:
        for index, reply in enumerate(replies):
            if reply.casefold() == target.casefold():
                deleted_reply = replies.pop(index)
                break

        if deleted_reply is None:
            return False, "not_found", None, len(replies)

    _save_replies(replies)
    return True, "deleted", deleted_reply, len(replies)


def _format_replies() -> str:
    replies = _load_replies()
    lines = [
        "💬 Daftar Auto Reply",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📦 File: {REPLIES_FILE.as_posix()}",
        f"🔢 Total: {len(replies)}",
        "",
    ]

    if not replies:
        lines.append("Belum ada balasan. Tambahkan dengan .addrep <pesan>.")
    else:
        for index, reply in enumerate(replies[:LIST_PREVIEW_LIMIT], start=1):
            lines.append(f"{index}. {_clip_reply(reply)}")

        remaining = len(replies) - LIST_PREVIEW_LIMIT
        if remaining > 0:
            lines.append(f"... dan {remaining} balasan lain.")

    lines.extend(
        [
            "",
            "➕ Tambah: .addrep <pesan>",
            "🗑️ Hapus: .delrep <nomor>",
            "",
            WATERMARK_LINE,
        ]
    )
    return "\n".join(lines)


def _pick_reply() -> str:
    replies = _load_replies()
    if not replies:
        return ""
    return random.choice(replies)


async def setup_plugin(client: TelegramClient):
    """Setup autoreply handler."""

    _ensure_replies_file()

    @client.on(events.NewMessage(outgoing=True))
    async def autoreply_command_handler(event):
        command_parts = parse_event_command(event)
        if not command_parts:
            return

        command = command_parts[0]
        if command not in ("addrep", "replies", "listrep", "delrep", "reloadrep"):
            return

        if command in ("replies", "listrep"):
            await event.edit(_format_replies())
            return

        if command == "reloadrep":
            total = len(_load_replies())
            await event.edit(
                "Daftar autoreply sudah dibaca ulang dari JSON.\n"
                f"Total autoreply: {total}\n"
                f"File: {REPLIES_FILE.as_posix()}\n\n"
                f"{WATERMARK_LINE}"
            )
            return

        if command == "delrep":
            target = " ".join(command_parts[1:]).strip()
            deleted, reason, deleted_reply, total = _delete_reply(target)

            if reason == "empty":
                await event.edit("Format: .delrep <nomor> atau .delrep <teks lengkap>")
                return

            if not deleted:
                await event.edit(
                    "Balasan autoreply tidak ditemukan.\n"
                    "Cek nomor dengan .replies\n\n"
                    f"{WATERMARK_LINE}"
                )
                return

            await event.edit(
                "Balasan autoreply dihapus.\n"
                f"Isi: {_clip_reply(deleted_reply)}\n"
                f"Sisa autoreply: {total}\n\n"
                f"{WATERMARK_LINE}"
            )
            return

        text = " ".join(command_parts[1:]).strip()
        replied_message = await event.get_reply_message()

        if not text and replied_message:
            text = _clean_reply(replied_message.raw_text or replied_message.text or "")

        added, reason, total = _add_reply(text)

        if reason == "empty":
            await event.edit("Format: .addrep pesan atau reply pesan dengan .addrep")
            return

        if not added:
            await event.edit(
                "Balasan itu sudah ada di daftar autoreply.\n"
                f"Total autoreply: {total}\n\n"
                f"{WATERMARK_LINE}"
            )
            return

        await event.edit(
            "Balasan autoreply ditambahkan.\n"
            f"Total autoreply: {total}\n\n"
            f"{WATERMARK_LINE}"
        )

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def autoreply_handler(event):
        if not is_feature_enabled("autoreply"):
            return

        try:
            me = await client.get_me()
            if event.sender_id == me.id:
                return

            sender = await event.get_sender()
            sender_name = sender.first_name or sender.username or "Unknown"
            reply_text = _pick_reply()
            if not reply_text:
                logger.info("Autoreply aktif, tapi daftar balasan kosong")
                return

            await event.reply(reply_text)
            logger.info("Autoreply dikirim ke %s", sender_name)

        except Exception as e:
            logger.error("Error saat autoreply: %s", e)

    if is_feature_enabled("autoreply"):
        logger.info("Autoreply module loaded")
    else:
        logger.info("Autoreply module loaded (DISABLED)")
