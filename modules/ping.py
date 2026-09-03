"""
PING MODULE
Cek respon bot dan uptime.
"""

import platform
import time
from datetime import datetime

import telethon
from telethon import TelegramClient, events

from modules.commands import is_user_command
from modules.feature_state import WATERMARK_LINE

START_TIME = time.time()


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


async def setup_plugin(client: TelegramClient):
    @client.on(events.NewMessage(outgoing=True))
    async def ping_handler(event):
        if not is_user_command(event, "ping"):
            return

        start = time.perf_counter()
        msg = await event.edit("🏓 Pong...")
        latency = (time.perf_counter() - start) * 1000
        await msg.edit(
            "🏓 Pong!\n"
            f"⚡ Respon: {latency:.2f} ms\n\n"
            f"{WATERMARK_LINE}"
        )

    @client.on(events.NewMessage(outgoing=True))
    async def alive_handler(event):
        if not is_user_command(event, "alive", "uptime"):
            return

        uptime = _format_duration(time.time() - START_TIME)
        await event.edit(
            "✅ Userbot aktif!\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ Uptime: {uptime}\n"
            f"🐍 Python: {platform.python_version()}\n"
            f"📦 Telethon: {telethon.__version__}\n"
            f"🕒 Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"{WATERMARK_LINE}"
        )
