"""
PURGE MODULE
Hapus pesan cepat dengan reply .del atau .purge.
"""

from telethon import TelegramClient, events

from modules.commands import is_user_command
from modules.feature_state import WATERMARK_LINE


async def setup_plugin(client: TelegramClient):
    @client.on(events.NewMessage(outgoing=True))
    async def delete_handler(event):
        if not is_user_command(event, "del"):
            return

        reply = await event.get_reply_message()
        if reply:
            await client.delete_messages(event.chat_id, [reply.id, event.message.id])
        else:
            await event.delete()

    @client.on(events.NewMessage(outgoing=True))
    async def purge_handler(event):
        if not is_user_command(event, "purge"):
            return

        reply = await event.get_reply_message()
        if not reply:
            await event.edit("🧹 Reply pesan awal lalu ketik .purge")
            return

        start_id = min(reply.id, event.message.id)
        end_id = max(reply.id, event.message.id)
        message_ids = list(range(start_id, end_id + 1))
        deleted = 0

        for index in range(0, len(message_ids), 100):
            chunk = message_ids[index:index + 100]
            await client.delete_messages(event.chat_id, chunk)
            deleted += len(chunk)

        done = await client.send_message(
            event.chat_id,
            "🧹 Purge selesai.\n"
            f"🗑️ Pesan diproses: {deleted}\n\n"
            f"{WATERMARK_LINE}",
        )
        await done.delete(delay=5)
