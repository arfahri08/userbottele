"""
MENU MODULE
Command .help/.menu dan toggle fitur runtime.
"""

import logging

from telethon import TelegramClient, events

from modules.commands import is_user_command, parse_event_command
from modules.feature_state import (
    WATERMARK_LINE,
    build_help_text,
    get_status_label,
    set_feature_enabled,
    toggle_feature,
)

logger = logging.getLogger(__name__)


async def _edit_or_reply(event, text: str):
    try:
        await event.edit(text)
    except Exception:
        await event.reply(text)


async def setup_plugin(client: TelegramClient):
    """Setup .help/.menu dan auto reply toggle commands."""

    @client.on(events.NewMessage(outgoing=True))
    async def menu_handler(event):
        if not is_user_command(event, "help", "menu"):
            return

        logger.info("Menu command diterima: %s", event.message.raw_text)
        await _edit_or_reply(event, build_help_text())

    @client.on(events.NewMessage(outgoing=True))
    async def autoreply_command(event):
        command_parts = parse_event_command(event)
        if not command_parts or command_parts[0] not in ("reply", "ar"):
            return

        action = command_parts[1].lower() if len(command_parts) > 1 else "status"

        if action == "on":
            set_feature_enabled("autoreply", True)
            text = f"Auto Reply sekarang ON.\n\n{WATERMARK_LINE}"
        elif action == "off":
            set_feature_enabled("autoreply", False)
            text = f"Auto Reply sekarang OFF.\n\n{WATERMARK_LINE}"
        elif action == "toggle":
            status = "ON" if toggle_feature("autoreply") else "OFF"
            text = f"Auto Reply sekarang {status}.\n\n{WATERMARK_LINE}"
        elif action == "status":
            text = f"Auto Reply saat ini {get_status_label('autoreply')}.\n\n{WATERMARK_LINE}"
        else:
            text = "Format: .reply on|off|toggle|status"

        await _edit_or_reply(event, text)

    logger.info("Menu module loaded")
