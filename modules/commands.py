"""
Command helpers for Telethon user commands.
"""

COMMAND_PREFIX = "."

from config import COMMAND_ALLOWED_CHAT_IDS


def parse_command_text(text: str):
    text = (text or "").strip()
    if not text.startswith(COMMAND_PREFIX):
        return []

    parts = text.split()
    command = parts[0][len(COMMAND_PREFIX):].split("@", 1)[0].lower()
    return [command, *parts[1:]]


def parse_event_command(event):
    return parse_command_text(getattr(event.message, "raw_text", "") or "")


def is_user_command(event, *commands):
    command_parts = parse_event_command(event)
    if not command_parts:
        return False

    normalized = {command.lower().lstrip(COMMAND_PREFIX) for command in commands}
    if not bool(getattr(event.message, "out", False)):
        return False

    chat_id = getattr(event, "chat_id", None)
    if COMMAND_ALLOWED_CHAT_IDS and chat_id not in COMMAND_ALLOWED_CHAT_IDS:
        return False

    return command_parts[0] in normalized
