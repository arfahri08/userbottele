"""
GET ID MODULE
Ambil informasi ID chat, user, dan message.
"""

from telethon import TelegramClient, events, utils

from modules.commands import is_user_command, parse_event_command
from modules.feature_state import WATERMARK_LINE


async def _name(entity):
    if not entity:
        return "-"

    first_name = getattr(entity, "first_name", None)
    last_name = getattr(entity, "last_name", None)
    full_name = " ".join(part for part in (first_name, last_name) if part)

    return (
        getattr(entity, "title", None)
        or full_name
        or getattr(entity, "username", None)
        or "-"
    )


def _entity_id(entity):
    if not entity:
        return "-"

    try:
        return utils.get_peer_id(entity)
    except Exception:
        return getattr(entity, "id", None) or "-"


def _entity_username(entity):
    username = getattr(entity, "username", None)
    return f"@{username}" if username else "-"


async def _resolve_target(client, target: str):
    target = (target or "").strip()
    if not target:
        return None

    try:
        return await client.get_entity(target)
    except Exception:
        return None


async def setup_plugin(client: TelegramClient):
    @client.on(events.NewMessage(outgoing=True))
    async def id_handler(event):
        if not is_user_command(event, "id", "cekid"):
            return

        command_parts = parse_event_command(event)
        target_text = command_parts[1] if len(command_parts) > 1 else ""
        chat = await event.get_chat()
        reply = await event.get_reply_message()
        target = await _resolve_target(client, target_text)

        lines = [
            "ID Info",
            "--------------------",
            f"Chat: {await _name(chat)}",
            f"Chat ID: {event.chat_id}",
            f"Message ID: {event.message.id}",
        ]

        if event.is_private:
            lines.extend(
                [
                    "",
                    "Private User",
                    f"Nama: {await _name(chat)}",
                    f"User ID: {_entity_id(chat)}",
                    f"Username: {_entity_username(chat)}",
                ]
            )
        elif event.is_group:
            lines.extend(
                [
                    "",
                    "Group/Channel",
                    f"Nama: {await _name(chat)}",
                    f"Group ID: {event.chat_id}",
                ]
            )
        elif event.is_channel:
            lines.extend(
                [
                    "",
                    "Channel",
                    f"Nama: {await _name(chat)}",
                    f"Channel ID: {event.chat_id}",
                ]
            )

        if target:
            lines.extend(
                [
                    "",
                    "Target",
                    f"Nama: {await _name(target)}",
                    f"User/Chat ID: {_entity_id(target)}",
                    f"Username: {_entity_username(target)}",
                ]
            )
        elif target_text:
            lines.extend(["", f"Target `{target_text}` tidak ditemukan."])

        if reply:
            reply_sender = await reply.get_sender()
            lines.extend(
                [
                    "",
                    "Reply Target",
                    f"Nama: {await _name(reply_sender)}",
                    f"User ID: {reply.sender_id}",
                    f"Username: {_entity_username(reply_sender)}",
                    f"Reply Message ID: {reply.id}",
                ]
            )

        lines.extend(["", WATERMARK_LINE])
        await event.edit("\n".join(lines))
