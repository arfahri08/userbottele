"""HEALTH MONITOR MODULE
Status runtime dan pemantauan koneksi Telegram.
"""

import asyncio
import logging
import platform
import time

import psutil
from telethon import TelegramClient, events

from config import HEALTH_CHECK_INTERVAL, HEALTH_MONITOR_ENABLED, SAVED_MESSAGES_TARGET
from modules.commands import is_user_command
from modules.feature_state import WATERMARK_LINE

logger = logging.getLogger(__name__)
START_TIME = time.time()


def _duration(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def _health_text(client):
    process = psutil.Process()
    return (
        "🩺 Modulogic Health\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Telegram: {'CONNECTED' if client.is_connected() else 'DISCONNECTED'}\n"
        f"⏱️ Uptime: {_duration(time.time() - START_TIME)}\n"
        f"🧠 RAM proses: {process.memory_info().rss / 1024**2:.1f} MB\n"
        f"💻 CPU: {psutil.cpu_percent(interval=None):.1f}%\n"
        f"🐍 Platform: {platform.system()} {platform.release()}\n\n"
        f"{WATERMARK_LINE}"
    )


async def setup_plugin(client: TelegramClient):
    if not HEALTH_MONITOR_ENABLED:
        return

    @client.on(events.NewMessage(outgoing=True))
    async def health_handler(event):
        if not is_user_command(event, "health"):
            return
        await event.edit(_health_text(client))

    async def connection_watchdog():
        was_connected = client.is_connected()
        while True:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)
            is_connected = client.is_connected()
            if is_connected == was_connected:
                continue

            was_connected = is_connected
            status = "terhubung kembali" if is_connected else "terputus"
            logger.warning("Koneksi Telegram %s", status)
            if is_connected:
                try:
                    await client.send_message(
                        SAVED_MESSAGES_TARGET,
                        f"🩺 Health monitor: koneksi Telegram {status}.",
                    )
                except Exception:
                    logger.exception("Gagal mengirim alert health monitor")

    asyncio.create_task(connection_watchdog())
    logger.info("Health monitor loaded")
