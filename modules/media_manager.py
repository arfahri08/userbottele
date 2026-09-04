"""MEDIA MANAGER MODULE
Statistik dan pembersihan file runtime di downloads/.
"""

import time
from pathlib import Path

from telethon import TelegramClient, events

from config import MEDIA_MANAGER_ENABLED
from modules.commands import is_user_command, parse_event_command
from modules.feature_state import WATERMARK_LINE

DOWNLOAD_ROOT = Path(__file__).resolve().parent.parent / "downloads"


def _files():
    return [path for path in DOWNLOAD_ROOT.rglob("*") if path.is_file()]


def _format_size(size):
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024


async def setup_plugin(client: TelegramClient):
    if not MEDIA_MANAGER_ENABLED:
        return

    @client.on(events.NewMessage(outgoing=True))
    async def media_manager_handler(event):
        if is_user_command(event, "disk", "storage"):
            files = _files() if DOWNLOAD_ROOT.exists() else []
            total_size = sum(path.stat().st_size for path in files)
            await event.edit(
                "💾 Download storage\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📁 Folder: {DOWNLOAD_ROOT.name}/\n"
                f"📦 File: {len(files)}\n"
                f"📊 Ukuran: {_format_size(total_size)}\n\n"
                f"{WATERMARK_LINE}"
            )
            return

        if not is_user_command(event, "cleanup"):
            return

        parts = parse_event_command(event)
        try:
            days = int(parts[1]) if len(parts) > 1 else 7
        except ValueError:
            await event.edit("Format: .cleanup [jumlah_hari]\nContoh: .cleanup 7")
            return

        if days < 1:
            await event.edit("Jumlah hari minimal adalah 1.")
            return

        cutoff = time.time() - days * 86400
        deleted = 0
        freed = 0
        for path in _files() if DOWNLOAD_ROOT.exists() else []:
            if path.stat().st_mtime >= cutoff:
                continue
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            deleted += 1
            freed += size

        await event.edit(
            "🧹 Cleanup selesai\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🗑️ File dihapus: {deleted}\n"
            f"💾 Ruang dibebaskan: {_format_size(freed)}\n"
            f"⏳ Batas umur: {days} hari\n\n"
            f"{WATERMARK_LINE}"
        )
