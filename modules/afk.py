"""
AFK MODULE
Balas pesan private saat sedang AFK.
"""

from datetime import datetime

from telethon import TelegramClient, events

from modules.commands import is_user_command, parse_event_command
from modules.feature_state import WATERMARK_LINE

AFK_STATE = {
    "enabled": False,
    "reason": "",
    "since": None,
    "replied_chats": set(),
}


def _duration_text(start: datetime) -> str:
    if not start:
        return "-"

    seconds = int((datetime.now() - start).total_seconds())
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


async def setup_plugin(client: TelegramClient):
    @client.on(events.NewMessage(outgoing=True))
    async def afk_command(event):
        if is_user_command(event, "afk"):
            parts = parse_event_command(event)
            reason = " ".join(parts[1:]).strip() or "Tidak ada alasan."

            AFK_STATE["enabled"] = True
            AFK_STATE["reason"] = reason
            AFK_STATE["since"] = datetime.now()
            AFK_STATE["replied_chats"] = set()

            await event.edit(
                "🌙 AFK mode aktif.\n"
                f"📝 Alasan: {reason}\n\n"
                f"{WATERMARK_LINE}"
            )
            return

        if is_user_command(event, "unafk"):
            if not AFK_STATE["enabled"]:
                await event.edit("✅ AFK mode memang sedang OFF.")
                return

            duration = _duration_text(AFK_STATE["since"])
            AFK_STATE["enabled"] = False
            AFK_STATE["reason"] = ""
            AFK_STATE["since"] = None
            AFK_STATE["replied_chats"] = set()

            await event.edit(
                "☀️ AFK mode dimatikan.\n"
                f"⏱️ Durasi AFK: {duration}\n\n"
                f"{WATERMARK_LINE}"
            )

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def afk_auto_reply(event):
        if not AFK_STATE["enabled"]:
            return

        me = await client.get_me()
        if event.sender_id == me.id:
            return

        if event.chat_id in AFK_STATE["replied_chats"]:
            return

        AFK_STATE["replied_chats"].add(event.chat_id)
        await event.reply(
            "🌙 Sedang AFK.\n"
            f"📝 Alasan: {AFK_STATE['reason']}\n"
            f"⏱️ Sejak: {_duration_text(AFK_STATE['since'])}\n\n"
            f"{WATERMARK_LINE}"
        )
