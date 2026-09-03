"""
NOTES MODULE
Simpan dan panggil catatan teks sederhana.
"""

import json
from pathlib import Path

from telethon import TelegramClient, events

from modules.commands import is_user_command, parse_event_command
from modules.feature_state import WATERMARK_LINE

DATA_DIR = Path("data")
NOTES_FILE = DATA_DIR / "notes.json"


def _load_notes():
    if not NOTES_FILE.exists():
        return {}

    try:
        return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_notes(notes):
    DATA_DIR.mkdir(exist_ok=True)
    NOTES_FILE.write_text(
        json.dumps(notes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def setup_plugin(client: TelegramClient):
    @client.on(events.NewMessage(outgoing=True))
    async def notes_handler(event):
        if is_user_command(event, "save"):
            parts = parse_event_command(event)
            if len(parts) < 2:
                await event.edit("🗒️ Format: .save nama catatan atau reply pesan dengan .save nama")
                return

            name = parts[1].lower()
            text = " ".join(parts[2:]).strip()
            reply = await event.get_reply_message()

            if not text and reply:
                text = reply.raw_text or reply.text or ""

            if not text:
                await event.edit("⚠️ Isi catatan kosong. Tulis teks atau reply pesan.")
                return

            notes = _load_notes()
            notes[name] = text
            _save_notes(notes)

            await event.edit(
                "✅ Catatan disimpan.\n"
                f"🗒️ Nama: {name}\n\n"
                f"{WATERMARK_LINE}"
            )
            return

        if is_user_command(event, "get"):
            parts = parse_event_command(event)
            if len(parts) < 2:
                await event.edit("🗒️ Format: .get nama")
                return

            name = parts[1].lower()
            note = _load_notes().get(name)
            if not note:
                await event.edit(f"⚠️ Catatan `{name}` tidak ditemukan.")
                return

            await event.edit(
                f"🗒️ Catatan: {name}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"{note}\n\n"
                f"{WATERMARK_LINE}"
            )
            return

        if is_user_command(event, "notes"):
            notes = _load_notes()
            if not notes:
                await event.edit("🗒️ Belum ada catatan tersimpan.")
                return

            names = "\n".join(f"• {name}" for name in sorted(notes))
            await event.edit(
                "🗒️ Daftar Catatan\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"{names}\n\n"
                f"{WATERMARK_LINE}"
            )
            return

        if is_user_command(event, "delnote"):
            parts = parse_event_command(event)
            if len(parts) < 2:
                await event.edit("🗒️ Format: .delnote nama")
                return

            name = parts[1].lower()
            notes = _load_notes()
            if name not in notes:
                await event.edit(f"⚠️ Catatan `{name}` tidak ditemukan.")
                return

            del notes[name]
            _save_notes(notes)
            await event.edit(f"🗑️ Catatan `{name}` dihapus.\n\n{WATERMARK_LINE}")
