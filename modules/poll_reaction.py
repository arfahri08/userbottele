"""POLL AND REACTION TOOLS MODULE
Buat poll dan beri reaction dari command outgoing.
"""

from telethon import TelegramClient, events, functions, types, utils

from config import POLL_REACTION_ENABLED
from modules.commands import is_user_command, parse_event_command
from modules.feature_state import WATERMARK_LINE


async def setup_plugin(client: TelegramClient):
    if not POLL_REACTION_ENABLED:
        return

    @client.on(events.NewMessage(outgoing=True))
    async def poll_handler(event):
        if not is_user_command(event, "poll"):
            return

        payload = (event.message.raw_text or "").split(maxsplit=1)
        if len(payload) < 2 or "|" not in payload[1]:
            await event.edit("Format: .poll Pertanyaan | Pilihan 1 | Pilihan 2")
            return

        question, *answers = [item.strip() for item in payload[1].split("|")]
        answers = [answer for answer in answers if answer]
        if not question or len(answers) < 2 or len(answers) > 10:
            await event.edit("Poll membutuhkan 2-10 pilihan.")
            return

        poll = types.Poll(
            id=0,
            question=types.TextWithEntities(text=question, entities=[]),
            answers=[
                types.PollAnswer(
                    text=types.TextWithEntities(text=answer, entities=[]),
                    option=bytes([index]),
                )
                for index, answer in enumerate(answers)
            ],
            hash=0,
        )
        await client(
            functions.messages.SendMediaRequest(
                peer=event.chat_id,
                media=types.InputMediaPoll(poll=poll),
                message="",
                random_id=utils.generate_random_long(),
            )
        )
        await event.delete()

    @client.on(events.NewMessage(outgoing=True))
    async def reaction_handler(event):
        if not is_user_command(event, "react", "reaction"):
            return

        reply = await event.get_reply_message()
        parts = parse_event_command(event)
        emoji = parts[1] if len(parts) > 1 else "👍"
        if not reply:
            await event.edit("Reply pesan lalu ketik .react 👍")
            return

        await client(
            functions.messages.SendReactionRequest(
                peer=event.chat_id,
                msg_id=reply.id,
                reaction=[types.ReactionEmoji(emoticon=emoji)],
            )
        )
        await event.edit(f"{emoji} Reaction dikirim.\n\n{WATERMARK_LINE}")
