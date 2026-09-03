"""
VOICE CHAT MUSIC MODULE
Putar audio/video YouTube di voice chat grup/channel.
"""

import asyncio
import importlib.util
import logging
import platform
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from telethon import TelegramClient, events

from modules.commands import parse_event_command
from modules.feature_state import WATERMARK_LINE
from modules.helpers import format_message_extended_media, inspect_message_extended_media

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"^https?://", re.IGNORECASE)
BAR_LENGTH = 18
VIDEO_QUALITIES = {360, 480, 720}
DEFAULT_VIDEO_QUALITY = 720

PLAY_COMMANDS = {
    "play",
    "p",
    "playv",
    "vplay",
    "vp",
    "playaudio",
    "aplay",
    "paudio",
    "a",
}
CONTROL_COMMANDS = {
    "pause",
    "ps",
    "resume",
    "rs",
    "stop",
    "end",
    "leave",
    "skip",
    "next",
    "now",
    "playing",
    "queue",
    "playlist",
    "list",
    "clearqueue",
    "clearq",
    "qclear",
    "removequeue",
    "qremove",
    "rmqueue",
    "quality",
    "vquality",
    "vcquality",
    "refresh",
    "music",
}
COMMANDS = PLAY_COMMANDS | CONTROL_COMMANDS

_voice_client = None
_voice_started = False
_stream_end_handler_registered = False
_telegram_client: Optional[TelegramClient] = None
_states: Dict[int, "PlayerState"] = {}


@dataclass
class Track:
    title: str
    page_url: str
    media_url: str
    audio_url: Optional[str]
    duration: Optional[int]
    requested_by: str
    video: bool
    quality: int = DEFAULT_VIDEO_QUALITY
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlayerState:
    current: Optional[Track] = None
    queue: list[Track] = field(default_factory=list)
    started_at: float = 0.0
    elapsed_before_pause: float = 0.0
    paused: bool = False
    status_message_id: Optional[int] = None
    advancing: bool = False
    video_quality: int = DEFAULT_VIDEO_QUALITY


def _get_state(chat_id: int) -> PlayerState:
    if chat_id not in _states:
        _states[chat_id] = PlayerState()
    return _states[chat_id]


def _looks_like_url(text: str) -> bool:
    return bool(URL_RE.match(text or ""))


def _format_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--"

    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _elapsed_seconds(state: PlayerState) -> float:
    if not state.current:
        return 0

    elapsed = state.elapsed_before_pause
    if not state.paused:
        elapsed += time.monotonic() - state.started_at

    if state.current.duration:
        elapsed = min(elapsed, state.current.duration)
    return max(0, elapsed)


def _progress_bar(elapsed: float, duration: Optional[int]) -> str:
    if not duration:
        return "[" + ("-" * BAR_LENGTH) + "]"

    ratio = min(1, max(0, elapsed / duration))
    filled = int(round(ratio * BAR_LENGTH))
    return "[" + ("#" * filled) + ("-" * (BAR_LENGTH - filled)) + "]"


def _build_panel(state: PlayerState, note: Optional[str] = None) -> str:
    lines = ["Voice Chat Player", "--------------------"]

    if not state.current:
        lines.append(note or "Tidak ada lagu yang sedang diputar.")
        lines.extend(["", WATERMARK_LINE])
        return "\n".join(lines)

    track = state.current
    elapsed = _elapsed_seconds(state)
    status = "Paused" if state.paused else "Playing"
    mode = f"Video {track.quality}p + audio" if track.video else "Audio only"

    lines.extend(
        [
            f"{status}: {track.title}",
            f"Mode: {mode}",
            f"Progress: {_progress_bar(elapsed, track.duration)}",
            f"Time: {_format_time(elapsed)} / {_format_time(track.duration)}",
            f"Queue: {len(state.queue)} lagu",
            f"Video quality: {state.video_quality}p",
            f"Request: {track.requested_by}",
        ]
    )

    if note:
        lines.extend(["", note])

    lines.extend(
        [
            "",
            "Kontrol:",
            ".pause | .resume | .skip [no] | .stop | .queue | .quality 720",
            "",
            WATERMARK_LINE,
        ]
    )
    return "\n".join(lines)


def _setup_issue() -> Optional[str]:
    missing = []

    if importlib.util.find_spec("pytgcalls") is None:
        missing.append("py-tgcalls")
    if importlib.util.find_spec("yt_dlp") is None:
        missing.append("yt-dlp")
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    if not shutil.which("ffprobe"):
        missing.append("ffprobe")

    if not missing:
        return None

    is_termux = "com.termux" in sys.prefix or "com.termux" in sys.executable
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    termux_note = ""
    if is_termux and sys.version_info >= (3, 13):
        termux_note = (
            "\n⚠️ Catatan Termux:\n"
            "Kamu sedang pakai Python "
            f"{python_version}. py-tgcalls membutuhkan ntgcalls native, "
            "dan di Termux Python 3.13 biasanya gagal build dari source.\n"
            "Bot tetap bisa jalan, tapi fitur voice chat music/video perlu environment "
            "yang punya wheel ntgcalls, misalnya Windows/Linux VPS Python 3.11/3.12.\n"
        )

    return (
        "🎵 Music player belum siap.\n"
        f"📦 Yang belum ada: {', '.join(missing)}\n"
        f"🐍 Python: {python_version} ({platform.system()})\n"
        f"{termux_note}\n"
        "Install dependency music optional:\n"
        "python -m pip install -r requirements-music.txt\n\n"
        "Install ffmpeg/ffprobe:\n"
        "• Windows: winget install Gyan.FFmpeg\n"
        "• Termux: pkg install ffmpeg\n\n"
        f"{WATERMARK_LINE}"
    )


async def _ensure_voice_client(client: TelegramClient):
    global _voice_client, _voice_started, _stream_end_handler_registered

    issue = _setup_issue()
    if issue:
        raise RuntimeError(issue)

    from pytgcalls import PyTgCalls, filters
    from pytgcalls.types import StreamEnded

    if _voice_client is None:
        _voice_client = PyTgCalls(client)

    if not _stream_end_handler_registered:
        _stream_end_handler_registered = True

        @_voice_client.on_update(filters.stream_end())
        async def _on_stream_end(_, update):
            if _telegram_client is None:
                return
            if not (update.stream_type & StreamEnded.Type.AUDIO):
                return
            await _handle_stream_end(_telegram_client, update.chat_id)

    if not _voice_started:
        await _voice_client.start()
        _voice_started = True

    return _voice_client


def _pick_format(formats: list[dict], want_video: bool) -> Optional[dict]:
    for item in formats:
        if not item.get("url"):
            continue
        has_video = item.get("vcodec") not in (None, "none")
        has_audio = item.get("acodec") not in (None, "none")
        if want_video and has_video:
            return item
        if not want_video and has_audio:
            return item
    return None


def _normalize_quality(value) -> int:
    try:
        quality = int(value)
    except (TypeError, ValueError):
        return DEFAULT_VIDEO_QUALITY
    return quality if quality in VIDEO_QUALITIES else DEFAULT_VIDEO_QUALITY


def _video_quality_param(VideoQuality, quality: int):
    candidates = {
        360: ("SD_360p", "SD_360P", "LOW", "LOW_360p"),
        480: ("SD_480p", "SD_480P", "MEDIUM", "MEDIUM_480p"),
        720: ("HD_720p", "HD_720P", "HIGH", "HIGH_720p"),
    }.get(_normalize_quality(quality), ("HD_720p", "HIGH"))

    for name in candidates:
        if hasattr(VideoQuality, name):
            return getattr(VideoQuality, name)

    return getattr(VideoQuality, "HD_720p")


def _extract_track_sync(query: str, requested_by: str, video: bool, quality: int = DEFAULT_VIDEO_QUALITY) -> Track:
    import yt_dlp

    target = query if _looks_like_url(query) else f"ytsearch1:{query}"
    quality = _normalize_quality(quality)
    format_selector = (
        f"bv*[height<={quality}]+ba/b[height<={quality}]/best"
        if video
        else "ba/bestaudio/best"
    )

    options = {
        "format": format_selector,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(target, download=False)

    if not info:
        raise RuntimeError("Lagu/video tidak ditemukan.")

    entries = info.get("entries") if isinstance(info, dict) else None
    if entries:
        info = next((entry for entry in entries if entry), None)
        if not info:
            raise RuntimeError("Lagu/video tidak ditemukan.")

    formats = info.get("requested_formats") or []
    video_format = _pick_format(formats, want_video=True)
    audio_format = _pick_format(formats, want_video=False)

    if video:
        media_url = (
            (video_format or {}).get("url")
            or info.get("url")
            or info.get("webpage_url")
        )
        audio_url = (audio_format or {}).get("url")
    else:
        audio_url = (audio_format or {}).get("url") or info.get("url")
        media_url = audio_url

    if not media_url:
        raise RuntimeError("URL stream tidak ditemukan dari YouTube.")

    duration = info.get("duration")
    if duration is not None:
        try:
            duration = int(float(duration))
        except (TypeError, ValueError):
            duration = None

    headers: Dict[str, str] = {}
    for source in (info, video_format or {}, audio_format or {}):
        for key, value in (source.get("http_headers") or {}).items():
            if isinstance(key, str) and isinstance(value, str):
                headers[key] = value

    return Track(
        title=info.get("title") or query,
        page_url=info.get("webpage_url") or query,
        media_url=media_url,
        audio_url=audio_url,
        duration=duration,
        requested_by=requested_by,
        video=video,
        quality=quality,
        headers=headers,
    )


async def _extract_track(query: str, requested_by: str, video: bool, quality: int = DEFAULT_VIDEO_QUALITY) -> Track:
    return await asyncio.to_thread(_extract_track_sync, query, requested_by, video, quality)


async def _send_or_update_panel(
    client: TelegramClient,
    chat_id: int,
    state: PlayerState,
    note: Optional[str] = None,
    message: Any = None,
):
    text = _build_panel(state, note)

    if message is not None:
        try:
            await message.edit(text)
            state.status_message_id = message.id
            return
        except Exception:
            pass

    if state.status_message_id:
        try:
            await client.edit_message(chat_id, state.status_message_id, text)
            return
        except Exception:
            state.status_message_id = None

    sent = await client.send_message(chat_id, text)
    state.status_message_id = sent.id


async def _play_track(
    client: TelegramClient,
    chat_id: int,
    state: PlayerState,
    track: Track,
    message: Any = None,
    note: Optional[str] = None,
):
    from pytgcalls.types import AudioQuality, GroupCallConfig, MediaStream, VideoQuality

    voice = await _ensure_voice_client(client)

    if track.video:
        stream = MediaStream(
            track.media_url,
            audio_path=track.audio_url,
            audio_parameters=AudioQuality.HIGH,
            video_parameters=_video_quality_param(VideoQuality, track.quality),
            headers=track.headers or None,
        )
    else:
        stream = MediaStream(
            track.media_url,
            audio_parameters=AudioQuality.HIGH,
            video_flags=MediaStream.Flags.IGNORE,
            headers=track.headers or None,
        )

    await voice.play(chat_id, stream, GroupCallConfig(auto_start=True))

    state.current = track
    state.started_at = time.monotonic()
    state.elapsed_before_pause = 0.0
    state.paused = False
    state.advancing = False
    await _send_or_update_panel(client, chat_id, state, note, message)


async def _leave_call(chat_id: int):
    if _voice_client is None:
        return

    try:
        await _voice_client.leave_call(chat_id)
    except Exception as e:
        logger.debug("Gagal leave voice chat %s: %s", chat_id, e)


async def _handle_stream_end(client: TelegramClient, chat_id: int):
    state = _states.get(chat_id)
    if not state or not state.current or state.advancing:
        return

    state.advancing = True
    await asyncio.sleep(1)

    if state.queue:
        next_track = state.queue.pop(0)
        try:
            await _play_track(
                client,
                chat_id,
                state,
                next_track,
                note="Lanjut ke queue berikutnya.",
            )
        except Exception as e:
            state.current = None
            await _send_or_update_panel(
                client,
                chat_id,
                state,
                f"Gagal memutar queue berikutnya: {str(e)[:900]}",
            )
    else:
        state.current = None
        state.elapsed_before_pause = 0.0
        state.paused = False
        await _leave_call(chat_id)
        await _send_or_update_panel(client, chat_id, state, "Queue selesai.")

    state.advancing = False


async def _requested_by(event) -> str:
    try:
        sender = await event.get_sender()
    except Exception:
        sender = None

    if not sender:
        return "unknown"

    name = getattr(sender, "first_name", None) or getattr(sender, "username", None)
    return name or str(getattr(sender, "id", "unknown"))


async def _clean_command(event, fallback: Optional[str] = None):
    try:
        await event.delete()
    except Exception:
        if fallback:
            await event.edit(fallback)


async def _safe_event_edit(event, text: str):
    try:
        await event.edit(text)
    except Exception:
        await event.respond(text)


async def _handle_play(event, parts: list[str]):
    if event.is_private:
        await event.edit("Music player dipakai di grup/channel yang punya voice chat.")
        return

    query = " ".join(parts[1:]).strip()
    if not query:
        await event.edit(
            "Format:\n"
            ".play judul lagu atau link YouTube\n"
            ".playaudio judul lagu atau link YouTube\n\n"
            f"{WATERMARK_LINE}"
        )
        return

    issue = _setup_issue()
    if issue:
        await event.edit(issue)
        return

    video = parts[0] not in {"playaudio", "aplay", "paudio", "a"}
    state = _get_state(event.chat_id)

    status = await event.edit(f"Mencari YouTube: {query[:80]}")

    try:
        track = await _extract_track(query, await _requested_by(event), video, state.video_quality)
    except Exception as e:
        await status.edit(
            "Gagal mencari/mengambil stream YouTube.\n"
            f"{str(e)[:1200]}\n\n"
            f"{WATERMARK_LINE}"
        )
        return

    if state.current:
        state.queue.append(track)
        await status.edit(
            "Masuk queue.\n"
            f"Judul: {track.title}\n"
            f"Posisi queue: {len(state.queue)}\n\n"
            f"{WATERMARK_LINE}"
        )
        await _send_or_update_panel(
            event.client,
            event.chat_id,
            state,
            f"Ditambahkan ke queue: {track.title}",
        )
        return

    try:
        await _play_track(
            event.client,
            event.chat_id,
            state,
            track,
            message=status,
            note="Mulai memutar di voice chat.",
        )
    except Exception as e:
        state.current = None
        await status.edit(
            "Gagal join/memutar di voice chat.\n"
            f"{str(e)[:1200]}\n\n"
            "Pastikan voice chat tersedia dan akun punya izin join.\n\n"
            f"{WATERMARK_LINE}"
        )


async def _require_current(event) -> Optional[PlayerState]:
    state = _states.get(event.chat_id)
    if not state or not state.current:
        await event.edit(f"Tidak ada lagu yang sedang diputar.\n\n{WATERMARK_LINE}")
        return None
    return state


async def _handle_pause(event):
    state = await _require_current(event)
    if not state:
        return

    if state.paused:
        await _clean_command(event)
        await _send_or_update_panel(event.client, event.chat_id, state, "Sudah paused.")
        return

    voice = await _ensure_voice_client(event.client)
    await voice.pause(event.chat_id)
    state.elapsed_before_pause = _elapsed_seconds(state)
    state.paused = True
    await _clean_command(event)
    await _send_or_update_panel(event.client, event.chat_id, state, "Paused.")


async def _handle_resume(event):
    state = await _require_current(event)
    if not state:
        return

    if not state.paused:
        await _clean_command(event)
        await _send_or_update_panel(event.client, event.chat_id, state, "Sudah playing.")
        return

    voice = await _ensure_voice_client(event.client)
    await voice.resume(event.chat_id)
    state.started_at = time.monotonic()
    state.paused = False
    await _clean_command(event)
    await _send_or_update_panel(event.client, event.chat_id, state, "Resume.")


async def _handle_stop(event, note: str = "Player dihentikan."):
    state = _get_state(event.chat_id)
    state.queue.clear()
    state.current = None
    state.started_at = 0.0
    state.elapsed_before_pause = 0.0
    state.paused = False
    await _leave_call(event.chat_id)
    await _clean_command(event)
    await _send_or_update_panel(event.client, event.chat_id, state, note)


async def _handle_skip(event, parts: Optional[list[str]] = None):
    state = await _require_current(event)
    if not state:
        return

    if parts and len(parts) > 1:
        try:
            queue_index = int(parts[1])
        except ValueError:
            await event.edit(f"Format: .skip atau .skip <nomor queue>\n\n{WATERMARK_LINE}")
            return

        if queue_index < 1 or queue_index > len(state.queue):
            await event.edit(f"Nomor queue tidak valid. Queue saat ini: {len(state.queue)} lagu.\n\n{WATERMARK_LINE}")
            return

        removed = state.queue.pop(queue_index - 1)
        await _clean_command(event)
        await _send_or_update_panel(
            event.client,
            event.chat_id,
            state,
            f"Dihapus dari queue #{queue_index}: {removed.title}",
        )
        return

    if not state.queue:
        await _handle_stop(event, "Queue kosong, player dihentikan.")
        return

    next_track = state.queue.pop(0)
    await _clean_command(event)
    try:
        await _play_track(
            event.client,
            event.chat_id,
            state,
            next_track,
            note="Skip ke queue berikutnya.",
        )
    except Exception as e:
        state.current = None
        await _send_or_update_panel(
            event.client,
            event.chat_id,
            state,
            f"Gagal skip: {str(e)[:900]}",
        )


async def _handle_clear_queue(event):
    state = _get_state(event.chat_id)
    removed = len(state.queue)
    state.queue.clear()
    await _clean_command(event)
    await _send_or_update_panel(
        event.client,
        event.chat_id,
        state,
        f"Queue dibersihkan. {removed} lagu dihapus dari antrian.",
    )


async def _handle_remove_queue(event, parts: list[str]):
    state = _states.get(event.chat_id)
    if not state or not state.queue:
        await event.edit(f"Queue kosong.\n\n{WATERMARK_LINE}")
        return

    if len(parts) < 2:
        await event.edit(f"Format: .qremove <nomor queue>\n\n{WATERMARK_LINE}")
        return

    try:
        queue_index = int(parts[1])
    except ValueError:
        await event.edit(f"Nomor queue harus angka.\n\n{WATERMARK_LINE}")
        return

    if queue_index < 1 or queue_index > len(state.queue):
        await event.edit(f"Nomor queue tidak valid. Queue saat ini: {len(state.queue)} lagu.\n\n{WATERMARK_LINE}")
        return

    removed = state.queue.pop(queue_index - 1)
    await _clean_command(event)
    await _send_or_update_panel(
        event.client,
        event.chat_id,
        state,
        f"Dihapus dari queue #{queue_index}: {removed.title}",
    )


async def _handle_quality(event, parts: list[str]):
    state = _get_state(event.chat_id)
    if len(parts) < 2:
        await event.edit(
            "Format: .quality 360|480|720\n"
            f"Quality sekarang: {state.video_quality}p\n\n"
            f"{WATERMARK_LINE}"
        )
        return

    try:
        quality = int(parts[1])
    except ValueError:
        await event.edit(f"Quality harus angka: 360, 480, atau 720.\n\n{WATERMARK_LINE}")
        return

    if quality not in VIDEO_QUALITIES:
        await event.edit(f"Quality tersedia: 360, 480, 720.\n\n{WATERMARK_LINE}")
        return

    state.video_quality = quality
    await _clean_command(event)
    await _send_or_update_panel(
        event.client,
        event.chat_id,
        state,
        f"Video quality diset ke {quality}p untuk lagu/video berikutnya.",
    )


async def _handle_refresh(event):
    state = _states.get(event.chat_id)
    if not state:
        state = _get_state(event.chat_id)

    await _clean_command(event)
    await _send_or_update_panel(event.client, event.chat_id, state, "Progress di-refresh.")


async def _handle_queue(event):
    state = _states.get(event.chat_id)
    if not state or not state.queue:
        await event.edit(f"Queue kosong.\n\n{WATERMARK_LINE}")
        return

    lines = ["Queue", "--------------------"]
    for index, track in enumerate(state.queue[:10], start=1):
        mode = f"video {track.quality}p" if track.video else "audio"
        lines.append(f"{index}. {track.title} ({_format_time(track.duration)}, {mode})")

    if len(state.queue) > 10:
        lines.append(f"... dan {len(state.queue) - 10} lagi")

    lines.extend(["", WATERMARK_LINE])
    await event.edit("\n".join(lines))


async def _handle_help(event):
    await event.edit(
        "🎵 Voice Chat Music\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎬 .play/.vplay <judul/link> - putar video + audio YouTube\n"
        "🎧 .playaudio/.aplay <judul/link> - putar audio saja\n"
        "⏸️ .pause/.ps / ▶️ .resume/.rs - pause atau lanjut\n"
        "⏭️ .skip - lanjut ke queue berikutnya\n"
        "🗑️ .skip <no> / .qremove <no> - hapus item queue\n"
        "🧹 .clearqueue - kosongkan antrian\n"
        "🎚️ .quality 360|480|720 - atur kualitas video berikutnya\n"
        "⏹️ .stop/.leave - stop dan keluar voice chat\n"
        "🔄 .refresh - refresh progress bar\n"
        "📜 .queue/.playlist - lihat antrian\n\n"
        "⚠️ Butuh dependency optional: requirements-music.txt + ffmpeg.\n"
        "🤖 Userbot akun biasa tidak bisa kirim inline button bot, jadi kontrol lewat command.\n\n"
        f"{WATERMARK_LINE}"
    )


async def setup_plugin(client: TelegramClient):
    global _telegram_client
    _telegram_client = client

    @client.on(events.NewMessage(outgoing=True))
    async def music_handler(event):
        parts = parse_event_command(event)
        if not parts or parts[0] not in COMMANDS:
            return

        command = parts[0]

        try:
            if command in PLAY_COMMANDS:
                reply = await event.get_reply_message()
                inspection = inspect_message_extended_media(reply) if reply else None
                if inspection:
                    await _safe_event_edit(
                        event,
                        f"{format_message_extended_media(inspection)}\n\n{WATERMARK_LINE}",
                    )
                    return
                await _handle_play(event, parts)
            elif command in {"pause", "ps"}:
                await _handle_pause(event)
            elif command in {"resume", "rs"}:
                await _handle_resume(event)
            elif command in {"stop", "end", "leave"}:
                await _handle_stop(event)
            elif command in {"skip", "next"}:
                await _handle_skip(event, parts)
            elif command in {"clearqueue", "clearq", "qclear"}:
                await _handle_clear_queue(event)
            elif command in {"removequeue", "qremove", "rmqueue"}:
                await _handle_remove_queue(event, parts)
            elif command in {"quality", "vquality", "vcquality"}:
                await _handle_quality(event, parts)
            elif command in {"now", "playing", "refresh"}:
                await _handle_refresh(event)
            elif command in {"queue", "playlist", "list"}:
                await _handle_queue(event)
            elif command == "music":
                await _handle_help(event)
        except Exception as e:
            logger.exception("Music command error: %s", e)
            await _safe_event_edit(
                event,
                "Music player error.\n"
                f"{str(e)[:1200]}\n\n"
                f"{WATERMARK_LINE}"
            )

    logger.info("Music module loaded")
