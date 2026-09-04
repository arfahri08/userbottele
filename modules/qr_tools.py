"""QR TOOLS MODULE
Generate QR code images locally.
"""

from io import BytesIO
from pathlib import Path

import qrcode
from telethon import TelegramClient, events

from config import QR_TOOLS_ENABLED
from modules.commands import is_user_command, parse_event_command

QR_READ_DIR = Path(__file__).resolve().parent.parent / "downloads" / "qr_read"


async def setup_plugin(client: TelegramClient):
    if not QR_TOOLS_ENABLED:
        return

    @client.on(events.NewMessage(outgoing=True))
    async def qr_handler(event):
        if not is_user_command(event, "qr"):
            return

        parts = parse_event_command(event)
        content = " ".join(parts[1:]).strip()
        if not content:
            await event.edit("Format: .qr teks atau link")
            return

        image = qrcode.make(content)
        buffer = BytesIO()
        buffer.name = "modulogic-qr.png"
        image.save(buffer, format="PNG")
        buffer.seek(0)
        await client.send_file(
            event.chat_id,
            buffer,
            caption="🔳 QR Code\nDibuat oleh Modulogic by Fahri",
        )
        await event.delete()

    @client.on(events.NewMessage(outgoing=True))
    async def read_qr_handler(event):
        if not is_user_command(event, "readqr", "decodeqr"):
            return

        try:
            import cv2
        except ImportError:
            await event.edit(
                "Fitur .readqr membutuhkan dependency opsional.\n"
                "Install: pip install -r requirements-qr.txt"
            )
            return

        reply = await event.get_reply_message()
        if not reply or not getattr(reply, "media", None):
            await event.edit("Reply gambar QR lalu ketik .readqr")
            return

        QR_READ_DIR.mkdir(parents=True, exist_ok=True)
        file_path = await client.download_media(reply, file=QR_READ_DIR)
        if not file_path:
            await event.edit("Gambar QR tidak dapat di-download.")
            return

        try:
            image = cv2.imread(str(file_path))
            decoded_text, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
            if decoded_text:
                await event.edit(f"🔳 QR terbaca:\n\n{decoded_text}")
            else:
                await event.edit("QR code tidak ditemukan atau tidak terbaca.")
        finally:
            Path(file_path).unlink(missing_ok=True)
