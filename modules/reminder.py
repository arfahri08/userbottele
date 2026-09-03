"""
REMINDER MODULE
Jadwalkan pengingat yang tetap aman setelah restart.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from telethon import TelegramClient, events

from config import SAVED_MESSAGES_TARGET
from modules.commands import is_user_command, parse_event_command
from modules.feature_state import WATERMARK_LINE

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
REMINDERS_FILE = DATA_DIR / "reminders.json"
MAX_REMINDERS = int(os.getenv("REMINDER_MAX_ACTIVE", "50"))
MAX_DELAY_SECONDS = int(os.getenv("REMINDER_MAX_DAYS", "365")) * 86400
CHECK_GRACE_SECONDS = 3

_tasks = {}


def _now_ts() -> int:
    return int(time.time())


def _load_reminders():
    if not REMINDERS_FILE.exists():
        return []

    try:
        data = json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Gagal baca reminders.json, memakai list kosong: %s", e)
        return []

    if not isinstance(data, list):
        return []

    reminders = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if not item.get("id") or not item.get("text") or not item.get("chat_id"):
            continue
        try:
            item["due_ts"] = int(item["due_ts"])
            item["chat_id"] = int(item["chat_id"])
        except Exception:
            continue
        reminders.append(item)

    return reminders


def _save_reminders(reminders):
    DATA_DIR.mkdir(exist_ok=True)
    tmp_path = REMINDERS_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(reminders, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(REMINDERS_FILE)


def _active_reminders():
    return [item for item in _load_reminders() if item.get("status") == "pending"]


def _new_id():
    return f"r{int(time.time() * 1000)}"


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def _format_due(due_ts: int) -> str:
    return datetime.fromtimestamp(int(due_ts)).strftime("%Y-%m-%d %H:%M:%S")


def _parse_duration(value: str):
    value = (value or "").strip().lower().replace(" ", "")
    if not value:
        return None

    unit_seconds = {
        "s": 1,
        "sec": 1,
        "secs": 1,
        "detik": 1,
        "m": 60,
        "min": 60,
        "mins": 60,
        "menit": 60,
        "h": 3600,
        "hr": 3600,
        "hrs": 3600,
        "jam": 3600,
        "d": 86400,
        "day": 86400,
        "days": 86400,
        "hari": 86400,
        "w": 604800,
        "week": 604800,
        "weeks": 604800,
        "minggu": 604800,
    }

    matches = re.findall(r"(\d+)([a-z]+)", value)
    if not matches:
        return None

    consumed = "".join(number + unit for number, unit in matches)
    if consumed != value:
        return None

    total = 0
    for number, unit in matches:
        if unit not in unit_seconds:
            return None
        total += int(number) * unit_seconds[unit]

    return total if total > 0 else None


def _parse_due_from_parts(parts):
    if not parts:
        return None, [], "Format waktu kosong."

    duration = _parse_duration(parts[0])
    if duration:
        if duration > MAX_DELAY_SECONDS:
            return None, [], f"Maksimal reminder {MAX_DELAY_SECONDS // 86400} hari."
        return _now_ts() + duration, parts[1:], None

    if len(parts) >= 2:
        raw_datetime = f"{parts[0]} {parts[1]}"
        for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
            try:
                due = datetime.strptime(raw_datetime, fmt)
                delay = int((due - datetime.now()).total_seconds())
                if delay <= 0:
                    return None, [], "Waktu reminder harus di masa depan."
                if delay > MAX_DELAY_SECONDS:
                    return None, [], f"Maksimal reminder {MAX_DELAY_SECONDS // 86400} hari."
                return int(due.timestamp()), parts[2:], None
            except ValueError:
                continue

    if len(parts) >= 1:
        raw_time = parts[0]
        try:
            target_time = datetime.strptime(raw_time, "%H:%M").time()
            due = datetime.combine(datetime.now().date(), target_time)
            if due <= datetime.now():
                due += timedelta(days=1)
            return int(due.timestamp()), parts[1:], None
        except ValueError:
            pass

    return None, [], "Format waktu tidak dikenali. Contoh: 10m, 1h30m, 2026-06-01 08:30, atau 08:30."


def _remove_reminder(reminder_id: str, cancel_task: bool = True):
    reminders = _load_reminders()
    kept = [item for item in reminders if item.get("id") != reminder_id]
    _save_reminders(kept)
    task = _tasks.pop(reminder_id, None)
    if cancel_task and task and task is not asyncio.current_task():
        task.cancel()
    return len(kept) != len(reminders)


async def _edit_or_reply(event, text: str):
    try:
        await event.edit(text)
    except Exception:
        await event.reply(text)


async def _send_reminder(client: TelegramClient, reminder):
    text = (
        "REMINDER\n"
        "====================\n"
        f"{reminder['text']}\n\n"
        f"Dijadwalkan: {_format_due(reminder['due_ts'])}\n"
        f"ID: {reminder['id']}\n\n"
        f"{WATERMARK_LINE}"
    )

    try:
        await client.send_message(reminder["chat_id"], text)
    except Exception as e:
        logger.warning("Gagal kirim reminder ke %s: %s", reminder.get("chat_id"), e)
        await client.send_message(
            SAVED_MESSAGES_TARGET,
            "REMINDER FALLBACK\n"
            f"Chat tujuan: {reminder.get('chat_id')}\n\n"
            f"{text}",
        )


async def _schedule_reminder(client: TelegramClient, reminder):
    reminder_id = reminder["id"]
    try:
        while True:
            delay = int(reminder["due_ts"]) - _now_ts()
            if delay <= CHECK_GRACE_SECONDS:
                break
            await asyncio.sleep(min(delay, 3600))

        await _send_reminder(client, reminder)
        _remove_reminder(reminder_id, cancel_task=False)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("Reminder %s gagal: %s", reminder_id, e)
    finally:
        _tasks.pop(reminder_id, None)


def _start_task(client: TelegramClient, reminder):
    reminder_id = reminder["id"]
    old_task = _tasks.pop(reminder_id, None)
    if old_task:
        old_task.cancel()
    _tasks[reminder_id] = asyncio.create_task(_schedule_reminder(client, reminder))


def _usage_text():
    return (
        "REMINDER\n"
        "====================\n"
        ".remind 10m minum air\n"
        ".remind 1h30m cek pesan\n"
        ".remind 08:30 meeting pagi\n"
        ".remind 2026-06-01 08:30 bayar tagihan\n"
        ".remind 15m sambil reply pesan\n"
        ".reminders - lihat daftar\n"
        ".cancelrem <id> - batal\n\n"
        f"{WATERMARK_LINE}"
    )


async def setup_plugin(client: TelegramClient):
    for reminder in _active_reminders():
        _start_task(client, reminder)

    @client.on(events.NewMessage(outgoing=True))
    async def reminder_handler(event):
        if is_user_command(event, "remind", "reminder", "ingat", "rem"):
            parts = parse_event_command(event)
            if len(parts) < 2:
                await _edit_or_reply(event, _usage_text())
                return

            active = _active_reminders()
            if len(active) >= MAX_REMINDERS:
                await _edit_or_reply(event, f"Batas reminder aktif tercapai ({MAX_REMINDERS}). Hapus dulu dengan .cancelrem <id>.")
                return

            due_ts, rest, error = _parse_due_from_parts(parts[1:])
            if error:
                await _edit_or_reply(event, f"{error}\n\n{_usage_text()}")
                return

            reminder_text = " ".join(rest).strip()
            reply = await event.get_reply_message()
            if not reminder_text and reply:
                reminder_text = (reply.raw_text or reply.text or "[media]").strip()

            if not reminder_text:
                await _edit_or_reply(event, "Teks reminder kosong. Tulis teks atau reply pesan yang mau diingatkan.")
                return

            reminder = {
                "id": _new_id(),
                "chat_id": int(event.chat_id),
                "text": reminder_text[:1500],
                "due_ts": int(due_ts),
                "created_ts": _now_ts(),
                "status": "pending",
            }

            reminders = _load_reminders()
            reminders.append(reminder)
            _save_reminders(reminders)
            _start_task(client, reminder)

            await _edit_or_reply(
                event,
                "Reminder disimpan.\n"
                f"ID: {reminder['id']}\n"
                f"Waktu: {_format_due(reminder['due_ts'])}\n"
                f"Sisa: {_format_duration(reminder['due_ts'] - _now_ts())}\n\n"
                f"{WATERMARK_LINE}",
            )
            return

        if is_user_command(event, "reminders", "listrem", "daftarrem"):
            active = sorted(_active_reminders(), key=lambda item: item["due_ts"])
            if not active:
                await _edit_or_reply(event, f"Belum ada reminder aktif.\n\n{WATERMARK_LINE}")
                return

            lines = ["REMINDER AKTIF", "===================="]
            for index, item in enumerate(active[:20], start=1):
                preview = item["text"].replace("\n", " ")
                if len(preview) > 55:
                    preview = f"{preview[:52]}..."
                lines.append(
                    f"{index}. {item['id']} | {_format_due(item['due_ts'])} | "
                    f"{_format_duration(item['due_ts'] - _now_ts())}\n   {preview}"
                )

            if len(active) > 20:
                lines.append(f"... dan {len(active) - 20} reminder lagi.")

            lines.append("")
            lines.append(WATERMARK_LINE)
            await _edit_or_reply(event, "\n".join(lines))
            return

        if is_user_command(event, "cancelrem", "delrem", "hapusrem"):
            parts = parse_event_command(event)
            if len(parts) < 2:
                await _edit_or_reply(event, "Format: .cancelrem <id>")
                return

            if _remove_reminder(parts[1]):
                await _edit_or_reply(event, f"Reminder {parts[1]} dibatalkan.\n\n{WATERMARK_LINE}")
            else:
                await _edit_or_reply(event, f"Reminder {parts[1]} tidak ditemukan.")
            return

        if is_user_command(event, "remindhelp"):
            await _edit_or_reply(event, _usage_text())
