"""
RESTART MODULE
Restart bot lewat command .upt dan kirim notifikasi saat aktif kembali.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, events

from config import SAVED_MESSAGES_TARGET
from modules.commands import is_user_command
from modules.feature_state import WATERMARK_LINE

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
RESTART_STATE_FILE = BASE_DIR / ".upt_restart.json"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_restart_state(event):
    data = {
        "requested_at": _now_text(),
        "chat_id": event.chat_id,
        "message_id": event.message.id,
    }

    try:
        RESTART_STATE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception as e:
        logger.warning("Gagal menulis restart state: %s", e)


def _read_restart_state():
    try:
        if not RESTART_STATE_FILE.exists():
            return None
        return json.loads(RESTART_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Gagal membaca restart state: %s", e)
        return None


def _clear_restart_state():
    try:
        if RESTART_STATE_FILE.exists():
            RESTART_STATE_FILE.unlink()
    except Exception as e:
        logger.warning("Gagal menghapus restart state: %s", e)


async def _notify_ready(client: TelegramClient):
    await asyncio.sleep(2)

    state = _read_restart_state()
    if state:
        text = (
            "✅ Bot aktif kembali!\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 Restart diminta: {state.get('requested_at', '-')}\n"
            f"🚀 Aktif lagi: {_now_text()}\n\n"
            "📋 Ketik .menu di Saved Messages untuk melihat fitur aktif.\n\n"
            f"{WATERMARK_LINE}"
        )
    else:
        text = (
            "✅ Bot aktif!\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 Waktu: {_now_text()}\n\n"
            "📋 Ketik .menu di Saved Messages untuk melihat fitur aktif.\n\n"
            f"{WATERMARK_LINE}"
        )

    try:
        await client.send_message(SAVED_MESSAGES_TARGET, text)
        _clear_restart_state()
    except Exception as e:
        logger.warning("Gagal mengirim notifikasi ready: %s", e)


async def _restart_process():
    await asyncio.sleep(1.5)
    args = [sys.executable, *sys.argv]
    logger.info("Restarting process: %s", " ".join(args))
    os.execv(sys.executable, args)


async def setup_plugin(client: TelegramClient):
    """Setup .upt restart command."""

    asyncio.create_task(_notify_ready(client))

    @client.on(events.NewMessage(outgoing=True))
    async def restart_command(event):
        if not is_user_command(event, "upt"):
            return

        logger.info("Restart command diterima: %s", event.message.raw_text)
        _write_restart_state(event)
        await event.edit(
            "🔄 Bot sedang restart...\n"
            "⏳ Tunggu notifikasi aktif kembali di Saved Messages."
        )
        asyncio.create_task(_restart_process())

    logger.info("Restart command module loaded")
