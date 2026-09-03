"""
TELEGRAM USERBOT - TELETHON MAIN
Satu jalur runtime: Telethon.
"""

import asyncio
import importlib
import logging
from pathlib import Path

from telethon import TelegramClient

from config import API_HASH, API_ID, PHONE_NUMBER


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
PLUGINS_DIR = BASE_DIR / "modules"
SKIP_MODULES = {"__init__", "commands", "feature_state", "helpers"}

client = TelegramClient(
    "userbot_session",
    API_ID,
    API_HASH,
    connection_retries=5,
    retry_delay=1,
    auto_reconnect=True,
    flood_sleep_threshold=0,
)


async def load_plugins():
    """Auto-load semua module Telethon dari folder modules/."""

    logger.info("=" * 50)
    logger.info("MEMULAI LOAD PLUGINS...")
    logger.info("=" * 50)

    plugins_loaded = []

    for plugin_file in sorted(PLUGINS_DIR.glob("*.py")):
        plugin_name = plugin_file.stem

        if (
            plugin_name.startswith("_")
            or plugin_name.endswith("_pyrogram")
            or plugin_name.endswith("_telethon")
            or plugin_name in SKIP_MODULES
        ):
            continue

        try:
            module = importlib.import_module(f"modules.{plugin_name}")
            setup_func = getattr(module, "setup_plugin", None)

            if not setup_func:
                continue

            await setup_func(client)
            plugins_loaded.append(plugin_name)
            logger.info("Plugin loaded: %s", plugin_name)

        except Exception as e:
            logger.error("Error loading plugin %s: %s", plugin_name, e)
            logger.exception(e)

    logger.info("=" * 50)
    logger.info("LOADED %s PLUGINS!", len(plugins_loaded))
    logger.info("=" * 50)

    return plugins_loaded


async def main():
    """Start client, load plugins, lalu keep bot running."""

    try:
        await client.start(phone=PHONE_NUMBER)
        logger.info("Client terkoneksi ke Telegram")

        me = await client.get_me()
        logger.info("Login sebagai: %s (%s)", me.first_name, me.username or "no username")

        await load_plugins()

        logger.info("Bot berjalan... Press Ctrl+C untuk stop")
        await client.run_until_disconnected()

    except Exception as e:
        logger.error("Fatal error: %s", e)
        logger.exception(e)

    finally:
        if client.is_connected():
            await client.disconnect()
            logger.info("Bot disconnected")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
