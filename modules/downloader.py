"""
DOWNLOADER MODULE
Multi-platform downloader with TikTok yt-dlp/TikWM fallback.
"""

import asyncio
import html
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from telethon import TelegramClient, events, functions, types

from modules.commands import parse_event_command
from modules.helpers import format_message_extended_media, inspect_message_extended_media

logger = logging.getLogger(__name__)

TEMP_DIR = Path(os.getenv("DOWNLOADER_TEMP_DIR", "downloads/tiktok"))
GENERIC_TEMP_DIR = Path(os.getenv("DOWNLOADER_GENERIC_TEMP_DIR", "downloads/downloader"))
TELEGRAM_STORY_TEMP_DIR = Path(os.getenv("TELEGRAM_STORY_TEMP_DIR", "downloads/telegram_status"))
MAX_MB = int(os.getenv("DOWNLOADER_MAX_MB", "95"))
MAX_FILES = int(os.getenv("DOWNLOADER_MAX_FILES", "10"))
MAX_IMAGE_SEND = int(os.getenv("DOWNLOADER_MAX_IMAGES", "15"))
TELEGRAM_STORY_LIMIT = max(1, int(os.getenv("TELEGRAM_STORY_LIMIT", "10")))
YTDLP_BIN = os.getenv("YTDLP_BIN", "").strip()
COOKIE_PATH = os.getenv("YTDLP_COOKIES", "").strip()
CHOICE_TTL_SECONDS = 120
API_TIMEOUT_SECONDS = int(os.getenv("DOWNLOADER_API_TIMEOUT", "30"))
SEND_DELAY_SECONDS = float(os.getenv("DOWNLOADER_SEND_DELAY", "0.9"))
TIKTOK_CDN_RETRIES = max(1, int(os.getenv("TIKTOK_CDN_RETRIES", "3")))
PINTEREST_HOST = "https://id.pinterest.com"
THREADS_HOST = "https://www.threads.com"

TIKTOK_RE = re.compile(
    r"https?://(?:www\.|vm\.|vt\.|m\.)?(?:tiktok\.com|tiktokv\.com)/[^\s<>]+",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
TELEGRAM_DEEP_LINK_RE = re.compile(r"tg://[^\s<>\"']+", re.IGNORECASE)
TELEGRAM_STORY_HTTP_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{5,32})/s/(\d+)"
    r"(?:[/?#][^\s<>\"']*)?",
    re.IGNORECASE,
)
TELEGRAM_STORY_TEST_RE = re.compile(
    r"(?:(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/[a-zA-Z0-9_]{5,32}/s/\d+|"
    r"tg://resolve\?[^\s<>\"']*(?:domain=|story=))",
    re.IGNORECASE,
)
TELEGRAM_PROFILE_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{5,32})/?(?:\?.*)?$",
    re.IGNORECASE,
)
TELEGRAM_USERNAME_RE = re.compile(r"^@?[a-zA-Z0-9_]{5,32}$")
PINTEREST_PIN_RE = re.compile(
    r"^(?:https?://(?:www\.|\w+\.)?pinterest\.[a-z.]+/pin/(\d{5,30})/?|"
    r"https?://(?:www\.)?pin\.it/([a-zA-Z0-9]+)/?|(\d{5,30}))$",
    re.IGNORECASE,
)

PLATFORM_PATTERNS = (
    {
        "id": "tiktok",
        "name": "TikTok",
        "emoji": "🎵",
        "test": TIKTOK_RE,
    },
    {
        "id": "pinterest",
        "name": "Pinterest",
        "emoji": "📌",
        "test": re.compile(r"(pinterest\.[a-z.]+|pin\.it)", re.IGNORECASE),
    },
    {
        "id": "facebook",
        "name": "Facebook",
        "emoji": "📘",
        "test": re.compile(r"(facebook\.com|fb\.watch|fb\.com)", re.IGNORECASE),
    },
    {
        "id": "soundcloud",
        "name": "SoundCloud",
        "emoji": "☁️",
        "test": re.compile(r"soundcloud\.com", re.IGNORECASE),
    },
    {
        "id": "threads",
        "name": "Threads",
        "emoji": "🧵",
        "test": re.compile(r"threads\.(?:net|com)", re.IGNORECASE),
    },
    {
        "id": "telegram_story",
        "name": "Telegram Status",
        "emoji": "📱",
        "test": TELEGRAM_STORY_TEST_RE,
    },
)

COMMAND_PLATFORM = {
    "tt": "tiktok",
    "tiktok": "tiktok",
    "ttmp3": "tiktok",
    "tta": "tiktok",
    "dl": None,
    "download": None,
    "pin": "pinterest",
    "pinterest": "pinterest",
    "fb": "facebook",
    "facebook": "facebook",
    "sc": "soundcloud",
    "soundcloud": "soundcloud",
    "th": "threads",
    "thread": "threads",
    "threads": "threads",
    "thmp3": "threads",
    "threadsmp3": "threads",
    "story": "telegram_story",
    "stories": "telegram_story",
    "status": "telegram_story",
    "tgstory": "telegram_story",
    "tgstatus": "telegram_story",
}

STORY_MODE_ALIASES = {
    "active": "active",
    "aktif": "active",
    "now": "active",
    "baru": "active",
    "terbaru": "active",
    "latest": "active",
    "pin": "pinned",
    "pinned": "pinned",
    "profile": "pinned",
    "profil": "pinned",
    "posted": "pinned",
    "post": "pinned",
    "auto": "auto",
    "all": "all",
    "semua": "all",
}

API_CANDIDATES = {
    "pinterest": [
        "https://api.agatz.xyz/api/pinterest",
        "https://api.vreden.my.id/api/pindl",
        "https://api.ryzendesu.vip/api/downloader/pinterest",
    ],
    "facebook": [
        "https://api.priyodown.com/v1/info",
        "https://api.agatz.xyz/api/facebook",
        "https://api.vreden.my.id/api/fbdl",
        "https://api.ryzendesu.vip/api/downloader/fbdown",
    ],
    "soundcloud": [
        "https://api.agatz.xyz/api/soundcloud",
        "https://api.vreden.my.id/api/soundcloud",
        "https://api.ryzendesu.vip/api/downloader/soundcloud",
    ],
    # Threads HTML sekarang kadang hanya mengekspos social-preview card (gambar
    # komposit putih + branding Threads). Vreden dipakai sebagai sumber media
    # terstruktur pertama karena endpoint ini mengembalikan URL media post, bukan
    # og:image halaman. Direct scraper tetap dipertahankan sebagai fallback.
    "threads": [
        "https://api.vreden.my.id/api/v1/download/threads?slof=1",
    ],
}

PINTEREST_HEADERS = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9,id;q=0.8",
    "referer": f"{PINTEREST_HOST}/",
}

THREADS_CRAWLER_USER_AGENTS = (
    # Browser UA harus dicoba dulu. Crawler UA Threads sering hanya menerima
    # social-preview card (og:image) yang berisi bidang putih/logo Threads,
    # bukan file media asli yang diunggah.
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Android 13; Mobile; rv:128.0) Gecko/128.0 Firefox/128.0",
    # Crawler UA hanya fallback untuk kasus halaman normal tidak memberi media.
    "facebookexternalhit/1.1",
    "Twitterbot/1.0",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".opus", ".ogg", ".wav"}

pending_sessions = {}


def _extract_tiktok_url(text: str):
    match = TIKTOK_RE.search(text or "")
    if not match:
        return None
    return match.group(0).rstrip(")>.,")


def _extract_first_url(text: str):
    match = URL_RE.search(text or "")
    if not match:
        return None
    return match.group(0).rstrip(")>.,?!")


def _strip_target(value: str):
    return str(value or "").strip().rstrip(")>.,?!\"'")


def _parse_telegram_story_link(text: str):
    text = str(text or "")

    http_match = TELEGRAM_STORY_HTTP_RE.search(text)
    if http_match:
        raw = _strip_target(http_match.group(0))
        return {
            "peer": f"@{http_match.group(1)}",
            "story_ids": [int(http_match.group(2))],
            "mode": "single",
            "source": "link story",
            "raw": raw,
        }

    for match in TELEGRAM_DEEP_LINK_RE.finditer(text):
        raw = _strip_target(unquote(match.group(0)))
        parsed = urlparse(raw)
        if parsed.scheme.lower() != "tg" or parsed.netloc.lower() != "resolve":
            continue

        query = parse_qs(parsed.query)
        username = (query.get("domain") or [""])[0]
        story_id = (query.get("story") or [""])[0]
        if TELEGRAM_USERNAME_RE.fullmatch(username or "") and str(story_id).isdigit():
            return {
                "peer": f"@{username.lstrip('@')}",
                "story_ids": [int(story_id)],
                "mode": "single",
                "source": "link story",
                "raw": raw,
            }

    return None


def _extract_telegram_story_link(text: str):
    target = _parse_telegram_story_link(text)
    return target["raw"] if target else None


def _normalize_telegram_peer(value: str, allow_bare_username: bool = True):
    clean = _strip_target(unquote(value))
    if not clean:
        return None

    profile_match = TELEGRAM_PROFILE_RE.match(clean)
    if profile_match:
        return f"@{profile_match.group(1)}"

    if clean.startswith("@") and TELEGRAM_USERNAME_RE.fullmatch(clean):
        return f"@{clean.lstrip('@')}"

    if not allow_bare_username:
        return None

    if TELEGRAM_USERNAME_RE.fullmatch(clean):
        return f"@{clean.lstrip('@')}"

    return None


def _parse_telegram_story_target(text: str, default_peer=None, allow_bare_username: bool = True):
    link_target = _parse_telegram_story_link(text)
    if link_target:
        return link_target

    mode = "auto"
    peer = None
    story_id = None

    for token in re.split(r"\s+", str(text or "").strip()):
        clean = _strip_target(token)
        if not clean:
            continue

        alias = STORY_MODE_ALIASES.get(clean.lower())
        if alias:
            mode = alias
            continue

        if clean.isdigit():
            story_id = int(clean)
            continue

        peer_candidate = _normalize_telegram_peer(clean, allow_bare_username=allow_bare_username)
        if peer_candidate:
            peer = peer_candidate

    if not peer and default_peer is not None:
        peer = default_peer

    if not peer:
        return None

    if story_id:
        return {
            "peer": peer,
            "story_ids": [story_id],
            "mode": "single",
            "source": "story id",
        }

    return {
        "peer": peer,
        "story_ids": None,
        "mode": mode,
        "source": "status aktif/pinned",
    }


def _story_target_from_message(message):
    media = getattr(message, "media", None)
    if isinstance(media, types.MessageMediaStory):
        target = {
            "peer": media.peer,
            "story_ids": [media.id],
            "mode": "single",
            "source": "story message",
        }
        if getattr(media, "story", None):
            target["stories"] = [media.story]
        return target

    reply_to = getattr(message, "reply_to", None)
    if isinstance(reply_to, types.MessageReplyStoryHeader):
        return {
            "peer": reply_to.user_id,
            "story_ids": [reply_to.story_id],
            "mode": "single",
            "source": "comment story",
        }

    return None


async def _get_telegram_story_target(event, target_text: str):
    target = _parse_telegram_story_target(target_text)
    if target:
        return target

    target = _story_target_from_message(event.message)
    if target:
        return target

    reply = await event.get_reply_message()
    if reply:
        target = _story_target_from_message(reply)
        if target:
            return target

        target = _parse_telegram_story_target(
            reply.raw_text or reply.text or "",
            allow_bare_username=False,
        )
        if target:
            return target

    if getattr(event, "is_private", False) and event.chat_id:
        return _parse_telegram_story_target(
            target_text,
            default_peer=event.chat_id,
        )

    return None


def _platform_info(platform_id: str):
    for platform in PLATFORM_PATTERNS:
        if platform["id"] == platform_id:
            return platform
    return {"id": platform_id, "name": platform_id.title(), "emoji": "📥"}


def _detect_platform(text: str):
    url = _extract_first_url(text)
    target = url or (text or "").strip()
    if not target:
        return None, None

    for platform in PLATFORM_PATTERNS:
        if platform["test"].search(target):
            if platform["id"] == "tiktok":
                return platform["id"], _extract_tiktok_url(target) or url
            if platform["id"] == "telegram_story":
                return platform["id"], _extract_telegram_story_link(target)
            return platform["id"], url or target.rstrip(")>.,?!")

    return None, None


async def _get_command_target(event):
    parts = parse_event_command(event)
    text = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
    if text:
        return text

    reply = await event.get_reply_message()
    if reply:
        return (reply.raw_text or reply.text or "").strip()

    return ""


async def _get_target_url(event):
    parts = parse_event_command(event)
    text = " ".join(parts[1:]) if len(parts) > 1 else ""
    url = _extract_tiktok_url(text)
    if url:
        return url

    reply = await event.get_reply_message()
    if reply:
        return _extract_tiktok_url(reply.raw_text or reply.text or "")

    return None


def _session_key(event):
    return event.chat_id


def _clear_session(event):
    pending_sessions.pop(_session_key(event), None)


def _remember_session(event, url: str, menu_message_id: int, platform_id: str = "tiktok"):
    pending_sessions[_session_key(event)] = {
        "platform_id": platform_id,
        "url": url,
        "menu_message_id": menu_message_id,
        "created_at": time.time(),
    }


def _get_session(event):
    session = pending_sessions.get(_session_key(event))
    if not session:
        return None

    if time.time() - session["created_at"] > CHOICE_TTL_SECONDS:
        _clear_session(event)
        return None

    return session


def _is_outgoing(event) -> bool:
    return bool(getattr(event.message, "out", False))


async def _event_extended_media(event, include_reply: bool = False):
    inspection = inspect_message_extended_media(event.message)
    if inspection:
        return event.message, inspection

    if include_reply:
        reply = await event.get_reply_message()
        if reply:
            inspection = inspect_message_extended_media(reply)
            if inspection:
                return reply, inspection

    return None, None


async def _status_message(event, text: str):
    if _is_outgoing(event):
        return await event.edit(text)
    return await event.respond(text)


async def _reply_text(event, text: str):
    if _is_outgoing(event):
        await event.edit(text)
    else:
        await event.respond(text)


async def _detector_status_message(event, session: dict, text: str):
    """Edit menu detektor yang sudah ada; buat pesan hanya jika menu hilang."""
    try:
        message = await event.client.get_messages(
            event.chat_id,
            ids=session.get("menu_message_id"),
        )
        if message:
            await message.edit(text)
            return message
    except Exception as e:
        logger.warning("Gagal mengedit menu downloader lama: %s", e)

    return await event.respond(text)


def _file_type(path: Path):
    ext = path.suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    return "document"


def _cleanup(paths):
    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception as e:
            logger.debug("Gagal hapus temp file %s: %s", path, e)


def _ytdlp_command():
    if YTDLP_BIN:
        return [YTDLP_BIN]
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return [sys.executable, "-m", "yt_dlp"]


def _build_ytdlp_args(url: str, mode: str):
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        "--no-warnings",
        "--no-progress",
        "--no-mtime",
        "--restrict-filenames",
        "--trim-filenames",
        "90",
        "--socket-timeout",
        "20",
        "--retries",
        "5",
        "--fragment-retries",
        "5",
        "--no-playlist",
        "--playlist-end",
        str(MAX_FILES),
        "--max-filesize",
        f"{MAX_MB}M",
        "--merge-output-format",
        "mp4",
        "--print",
        "after_move:filepath",
        "-P",
        str(TEMP_DIR),
        "-o",
        "%(extractor)s_%(id)s_%(epoch)s.%(ext)s",
    ]

    if COOKIE_PATH and Path(COOKIE_PATH).exists():
        args.extend(["--cookies", COOKIE_PATH])

    if mode == "audio":
        args.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
    else:
        args.extend([
            "-f",
            # TikTok menyediakan progressive MP4. Memilih satu stream lebih
            # stabil dan tetap bekerja di perangkat yang belum punya ffmpeg.
            "b[ext=mp4]/best",
        ])

    args.append(url)
    return args


def _run_ytdlp_sync(url: str, mode: str):
    process = subprocess.run(
        [*_ytdlp_command(), *_build_ytdlp_args(url, mode)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )

    files = []
    for line in process.stdout.splitlines():
        path = Path(line.strip())
        if path.exists() and path.is_file():
            files.append(path)

    if not files:
        if process.returncode != 0:
            raise RuntimeError((process.stderr or f"yt-dlp exit code {process.returncode}").strip())
        raise RuntimeError("yt-dlp selesai, tapi file hasil download tidak ditemukan.")

    unique = []
    seen = set()
    for file_path in files:
        resolved = str(file_path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(file_path)

    return unique[:MAX_FILES]


async def _run_ytdlp(url: str, mode: str):
    return await asyncio.to_thread(_run_ytdlp_sync, url, mode)


def _request_json(url: str, label: str, headers=None, timeout: int = 25, data=None):
    request = Request(
        url,
        data=data,
        headers={
            "accept": "application/json,text/plain,*/*",
            "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            **(headers or {}),
        },
    )

    with urlopen(request, timeout=timeout) as response:
        if response.status >= 400:
            raise RuntimeError(f"{label} membalas HTTP {response.status}.")
        return json.loads(response.read(5 * 1024 * 1024).decode("utf-8"))


def _request_text(url: str, label: str, headers=None, timeout: int = API_TIMEOUT_SECONDS):
    request = Request(
        url,
        headers={
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            **(headers or {}),
        },
    )

    with urlopen(request, timeout=timeout) as response:
        if response.status >= 400:
            raise RuntimeError(f"{label} membalas HTTP {response.status}.")
        content_type = response.headers.get_content_charset() or "utf-8"
        return response.read(12 * 1024 * 1024).decode(content_type, errors="replace"), response.url


def _normalize_media_url(url: str, base_url: str = "https://www.tikwm.com"):
    url = str(url or "").strip()
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/") and base_url:
        return f"{base_url}{url}"
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return None


def _is_url(value: str) -> bool:
    value = str(value or "")
    return value.startswith("//") or value.startswith("/") or bool(URL_RE.match(value))


def _collect_url_entries(value, path=None, output=None):
    path = path or []
    output = output if output is not None else []

    if value is None:
        return output

    if isinstance(value, str):
        if _is_url(value):
            normalized = _normalize_media_url(value)
            if normalized:
                output.append({"url": normalized, "path": ".".join(path).lower()})
        return output

    if isinstance(value, list):
        for index, item in enumerate(value):
            _collect_url_entries(item, [*path, str(index)], output)
        return output

    if isinstance(value, dict):
        for key, item in value.items():
            _collect_url_entries(item, [*path, str(key)], output)

    return output


def _unique_entries(entries):
    seen = set()
    unique = []
    for entry in entries:
        url = entry.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(entry)
    return unique


def _has_ext(url: str, extensions):
    clean = str(url or "").split("?", 1)[0].lower()
    return any(clean.endswith(ext) or f"{ext}/" in clean or f"{ext}." in clean for ext in extensions)


def _is_probably_page_url(url: str) -> bool:
    clean = str(url or "").lower()
    if re.search(r"\.(mp4|mov|m3u8|jpg|jpeg|png|webp|mp3|m4a|aac|wav|ogg)(?:[/?#.]|$)", clean):
        return False

    return any(
        marker in clean
        for marker in (
            "tiktok.com/@",
            "vt.tiktok.com",
            "facebook.com/",
            "fb.watch",
            "pinterest.com/pin",
            "pin.it/",
            "soundcloud.com/",
            "threads.net/",
            "threads.com/",
        )
    )


def _score_entry(entry, positive_keywords=None, negative_keywords=None):
    positive_keywords = positive_keywords or []
    negative_keywords = negative_keywords or []
    path = entry.get("path", "")
    url = entry.get("url", "").lower()
    score = 0

    for keyword in positive_keywords:
        if keyword in path or keyword in url:
            score += 3
    for keyword in negative_keywords:
        if keyword in path or keyword in url:
            score -= 4

    if "watermark" in url:
        score -= 4
    if "wmplay" in path:
        score -= 5
    if any(keyword in path for keyword in ("no_watermark", "nowm", "nwm")):
        score += 5
    if "hd" in path or "high" in path:
        score += 4
    if "download" in path:
        score += 3

    return score


def _pick_best(entries, media_type: str):
    configs = {
        "video": {
            "exts": [".mp4", ".mov", ".m3u8"],
            "positive": ["video", "play", "hd", "sd", "download", "nowm", "nwm", "no_watermark", "url"],
            "negative": ["cover", "thumbnail", "thumb", "avatar", "image", "music", "audio"],
        },
        "image": {
            "exts": [".jpg", ".jpeg", ".png", ".webp"],
            "positive": ["image", "images", "photo", "picture", "media", "url", "download"],
            "negative": ["avatar", "profile", "thumb", "thumbnail", "cover"],
        },
        "audio": {
            "exts": [".mp3", ".m4a", ".aac", ".wav", ".ogg"],
            "positive": ["audio", "music", "mp3", "sound", "download", "play", "url"],
            "negative": ["cover", "thumbnail", "thumb", "avatar", "image"],
        },
    }[media_type]

    candidates = [entry for entry in entries if _has_ext(entry["url"], configs["exts"])]
    if not candidates:
        candidates = [
            entry
            for entry in entries
            if not _is_probably_page_url(entry["url"])
            and _score_entry(entry, configs["positive"], configs["negative"]) > 1
        ]

    if not candidates:
        return None

    return sorted(
        candidates,
        key=lambda entry: _score_entry(entry, configs["positive"], configs["negative"]),
        reverse=True,
    )[0]["url"]


def _pick_images(entries):
    image_entries = [
        entry
        for entry in _unique_entries(entries)
        if _has_ext(entry["url"], [".jpg", ".jpeg", ".png", ".webp"])
        and _score_entry(
            entry,
            ["image", "images", "photo", "picture", "media"],
            ["avatar", "profile", "thumbnail", "thumb"],
        )
        >= -2
    ]
    return [entry["url"] for entry in image_entries[:MAX_IMAGE_SEND]]


def _parse_pinterest_pin_url(value: str):
    clean = str(value or "").strip().rstrip("),.?!")
    clean_without_query = re.split(r"[?#]", clean, maxsplit=1)[0]
    match = PINTEREST_PIN_RE.match(clean_without_query)
    if not match:
        return None

    if match.group(1):
        return {"format": "long", "id": match.group(1), "url": clean}
    if match.group(2):
        return {"format": "short", "id": match.group(2), "url": clean}
    return {"format": "id", "id": match.group(3), "url": f"{PINTEREST_HOST}/pin/{match.group(3)}/"}


def _extract_pinterest_pin_id(value: str):
    clean = str(value or "")
    match = re.search(r"pinterest\.[^/]+/pin/(\d{5,30})", clean, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.match(r"^(\d{5,30})$", clean)
    return match.group(1) if match else None


def _get_trace_id():
    return f"{int(time.time() * 1000000) % 0xFFFFFFFFFFFFFFFF:016x}"


def _resolve_pinterest_pin(original_url: str):
    parsed = _parse_pinterest_pin_url(original_url)
    if not parsed:
        raise RuntimeError("URL Pinterest tidak valid.")

    if parsed["format"] != "short":
        pin_id = _extract_pinterest_pin_id(parsed["url"]) or parsed["id"]
        return {"id": pin_id, "url": f"{PINTEREST_HOST}/pin/{pin_id}/"}

    html_text, final_url = _request_text(
        parsed["url"],
        "Pinterest",
        headers=PINTEREST_HEADERS,
        timeout=API_TIMEOUT_SECONDS,
    )
    pin_id = _extract_pinterest_pin_id(final_url) or _extract_pinterest_pin_id(html_text)
    if not pin_id:
        raise RuntimeError("Gagal resolve shortlink pin.it.")

    return {"id": pin_id, "url": f"{PINTEREST_HOST}/pin/{pin_id}/"}


def _extract_json_object_at(text: str, start_index: int):
    object_start = text.find("{", start_index)
    if object_start < 0:
        return None

    depth = 0
    in_string = False
    quote = ""
    escaped = False

    for index in range(object_start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                in_string = False
                quote = ""
            continue

        if char in {"\"", "'"}:
            in_string = True
            quote = char
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[object_start:index + 1]

    return None


def _parse_json_safe(value: str):
    try:
        return json.loads(value)
    except Exception:
        return None


def _extract_pinterest_relay_payloads(html_text: str):
    marker = "window.__PWS_RELAY_REGISTER_COMPLETED_REQUEST__("
    payloads = []
    cursor = 0

    while cursor < len(html_text):
        marker_index = html_text.find(marker, cursor)
        if marker_index < 0:
            break

        json_text = _extract_json_object_at(html_text, marker_index + len(marker))
        payload = _parse_json_safe(json_text) if json_text else None
        if payload:
            payloads.append(payload)

        cursor = marker_index + len(marker)

    return payloads


def _extract_pinterest_initial_props(html_text: str):
    match = re.search(
        r"<script[^>]+id=[\"']__PWS_INITIAL_PROPS__[\"'][^>]*>([\s\S]*?)</script>",
        html_text,
        re.IGNORECASE,
    )
    if not match:
        return None

    return _parse_json_safe(html.unescape(match.group(1)))


def _add_pinterest_entry(entries, url: str, path: str):
    normalized = _normalize_media_url(url, base_url="")
    if not normalized:
        return
    if not re.search(r"\.(?:jpg|jpeg|png|webp|mp4|mov|m3u8)(?:[/?#.]|$)", normalized, re.IGNORECASE):
        return

    entries.append({"url": normalized, "path": f"pinterest.{path}".lower()})


def _collect_pinterest_preferred_entries(value, entries=None, path=None):
    entries = entries if entries is not None else []
    path = path or []

    if value is None:
        return entries

    if isinstance(value, list):
        for index, item in enumerate(value):
            _collect_pinterest_preferred_entries(item, entries, [*path, str(index)])
        return entries

    if not isinstance(value, dict):
        return entries

    for key in ("imageLargeUrl", "thumbnail", "url"):
        if value.get(key):
            _add_pinterest_entry(entries, value.get(key), ".".join([*path, key]))

    image_variants = value.get("images") or value.get("image")
    if isinstance(image_variants, dict):
        for key, image in image_variants.items():
            if isinstance(image, dict) and image.get("url"):
                _add_pinterest_entry(entries, image["url"], ".".join([*path, "images", str(key), "url"]))

    pages = (((value.get("storyPinData") or {}).get("pages")) or [])
    if pages:
        blocks = ((pages[0] or {}).get("blocks")) or []
        if blocks:
            video_data = (blocks[0] or {}).get("videoDataV2") or {}
            video_list = ((video_data.get("videoList720P") or {}).get("v720P")) or {}
            if video_list.get("url"):
                _add_pinterest_entry(
                    entries,
                    video_list["url"],
                    ".".join([*path, "storyPinData", "videoList720P", "v720P", "url"]),
                )

    video_list = (
        (value.get("videos") or {}).get("video_list")
        or (value.get("video") or {}).get("video_list")
        or value.get("video_list")
    )
    if isinstance(video_list, dict):
        for key, video in video_list.items():
            if not isinstance(video, dict):
                continue
            if video.get("url"):
                _add_pinterest_entry(entries, video["url"], ".".join([*path, "video_list", str(key), "url"]))
            if video.get("thumbnail"):
                _add_pinterest_entry(
                    entries,
                    video["thumbnail"],
                    ".".join([*path, "video_list", str(key), "thumbnail"]),
                )

    for key, item in value.items():
        if isinstance(item, (dict, list)):
            _collect_pinterest_preferred_entries(item, entries, [*path, str(key)])

    return entries


def _get_pinterest_payload_roots(payloads):
    roots = []

    for payload in payloads:
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            for item in payload["data"].values():
                if isinstance(item, dict):
                    roots.append(item.get("data") or item)
        else:
            roots.append(payload)

    return [root for root in roots if root]


def _score_pinterest_entry(entry, media_type: str):
    path = entry.get("path", "")
    url = entry.get("url", "").lower()
    score = _score_entry(
        entry,
        (
            ["video", "videolist720p", "v720p", "storypindata", "url", "download"]
            if media_type == "video"
            else ["imagelargeurl", "images.orig", "originals", "image", "images", "url"]
        ),
        ["avatar", "avatars", "profile", "pinner", "creator", "thumbnail"],
    )

    if "v.pinimg.com/videos" in url:
        score += 12 if media_type == "video" else -2
    if "i.pinimg.com/originals" in url:
        score += 12 if media_type == "image" else -2
    if "/736x/" in url:
        score += 7 if media_type == "image" else -1
    if "/564x/" in url:
        score += 4 if media_type == "image" else -1
    if any(size in url for size in ("/236x/", "/170x/", "/75x75/")):
        score -= 8
    if "imagelargeurl" in path:
        score += 12 if media_type == "image" else -2
    if "videolist720p" in path or "v720p" in path:
        score += 12 if media_type == "video" else -2
    if "thumbnail" in path:
        score -= 3 if media_type == "video" else 7
    if ".m3u8" in url:
        score -= 8

    return score


def _pick_pinterest_video(entries):
    candidates = [
        entry
        for entry in _unique_entries(entries)
        if _has_ext(entry["url"], [".mp4", ".mov"])
        and _score_pinterest_entry(entry, "video") > 0
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda entry: _score_pinterest_entry(entry, "video"), reverse=True)[0]["url"]


def _pick_pinterest_image(entries):
    candidates = [
        entry
        for entry in _unique_entries(entries)
        if _has_ext(entry["url"], [".jpg", ".jpeg", ".png", ".webp"])
        and _score_pinterest_entry(entry, "image") > 0
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda entry: _score_pinterest_entry(entry, "image"), reverse=True)[0]["url"]


def _pick_pinterest_images(entries):
    candidates = [
        entry
        for entry in _unique_entries(entries)
        if _has_ext(entry["url"], [".jpg", ".jpeg", ".png", ".webp"])
        and _score_pinterest_entry(entry, "image") > 0
    ]
    return [
        entry["url"]
        for entry in sorted(candidates, key=lambda entry: _score_pinterest_entry(entry, "image"), reverse=True)[
            :MAX_IMAGE_SEND
        ]
    ]


def _has_pinterest_downloadable_entries(entries):
    return bool(_pick_pinterest_video(entries) or _pick_pinterest_image(entries))


def _scrape_pinterest_media(original_url: str):
    pin = _resolve_pinterest_pin(original_url)
    headers = {
        **PINTEREST_HEADERS,
        "x-b3-traceid": _get_trace_id(),
        "x-b3-spanid": _get_trace_id(),
        "x-pinterest-source-url": f"/pin/{pin['id']}/",
    }
    html_text, _ = _request_text(pin["url"], "Pinterest", headers=headers, timeout=API_TIMEOUT_SECONDS)

    payloads = _extract_pinterest_relay_payloads(html_text)
    initial_props = _extract_pinterest_initial_props(html_text)
    roots = [*_get_pinterest_payload_roots(payloads), initial_props]
    roots = [root for root in roots if root]

    preferred_entries = _collect_pinterest_preferred_entries(roots)
    broad_entries = [
        entry
        for entry in _unique_entries(_collect_url_entries(roots))
        if re.search(r"\.(?:jpg|jpeg|png|webp|mp4|mov|m3u8)(?:[/?#.]|$)", entry["url"], re.IGNORECASE)
    ]
    html_entries = []
    for index, raw_url in enumerate(re.findall(r"https?:\\?/\\?/[^\"'\\\s<>]+", html_text)):
        normalized = _normalize_media_url(raw_url.replace("\\u002F", "/").replace("\\/", "/"), base_url="")
        if normalized and re.search(r"\.(?:jpg|jpeg|png|webp|mp4|mov|m3u8)(?:[/?#.]|$)", normalized, re.IGNORECASE):
            html_entries.append({"url": normalized, "path": f"pinterest.html.{index}"})

    entries = _unique_entries([*preferred_entries, *broad_entries, *html_entries])
    if not _has_pinterest_downloadable_entries(entries):
        raise RuntimeError(f"Media Pinterest tidak ditemukan untuk pin {pin['id']}.")

    return {"data": {"source": "pinterest-local-scraper", "pinId": pin["id"]}, "entries": entries}


def _normalize_threads_url(url: str):
    clean = _strip_target(url)
    if not clean:
        return clean

    try:
        parsed = urlparse(clean)
        if not parsed.scheme:
            parsed = urlparse(f"https://{clean}")
        if not re.search(r"threads\.(?:net|com)$", parsed.netloc, re.IGNORECASE):
            return clean

        return parsed._replace(
            scheme="https",
            netloc="www.threads.com",
            query="",
            fragment="",
        ).geturl()
    except Exception:
        return re.sub(
            r"https?://(?:www\.)?threads\.(?:net|com)",
            THREADS_HOST,
            clean,
            flags=re.IGNORECASE,
        ).split("?", 1)[0].split("#", 1)[0]


def _decode_html_value(value: str):
    decoded = html.unescape(str(value or ""))
    # Threads/Meta hydration data sering menyimpan URL sebagai JSON-escaped text.
    for source, target in (
        ("\\/", "/"),
        ("\\u002F", "/"),
        ("\\u002f", "/"),
        ("\\u0026", "&"),
        ("\\u003D", "="),
        ("\\u003d", "="),
        ("\\u003F", "?"),
        ("\\u003f", "?"),
    ):
        decoded = decoded.replace(source, target)
    return decoded


def _get_html_attribute(tag: str, attribute: str):
    match = re.search(
        rf"{re.escape(attribute)}\s*=\s*(\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
        tag,
        re.IGNORECASE,
    )
    if not match:
        return None

    return _decode_html_value(match.group(2) or match.group(3) or match.group(4) or "")


def _extract_meta_values(html_text: str, names):
    wanted = {name.lower() for name in names}
    values = []

    for tag in re.findall(r"<meta\b[^>]*>", html_text or "", flags=re.IGNORECASE):
        name = (
            _get_html_attribute(tag, "property")
            or _get_html_attribute(tag, "name")
            or ""
        ).lower()
        if name not in wanted:
            continue

        content = _get_html_attribute(tag, "content")
        if content:
            values.append(content)

    return values


def _guess_threads_media_type_from_url(url: str):
    clean = str(url or "").split("?", 1)[0].lower()
    if re.search(r"\.(?:mp4|mov|m4v|webm)$", clean):
        return "video"
    if re.search(r"\.(?:jpg|jpeg|png|webp)$", clean):
        return "image"
    return None


def _threads_post_code(url: str):
    match = re.search(r"/(?:post|t)/([^/?#]+)", str(url or ""), re.IGNORECASE)
    return match.group(1) if match else None


def _is_threads_asset_url(url: str, media_type: str | None = None):
    clean = _decode_html_value(url).strip()
    if not clean.startswith(("http://", "https://")):
        return False
    if re.search(r"static\.cdninstagram\.com/rsrc\.php", clean, re.IGNORECASE):
        return False
    if re.search(r"(?:profile_pic|avatar|t51\.2885-19)", clean, re.IGNORECASE):
        return False

    guessed = _guess_threads_media_type_from_url(clean)
    if media_type and guessed and guessed != media_type:
        return False

    return bool(
        guessed
        or re.search(
            r"(?:cdninstagram\.com|fbcdn\.net|threads\.net|threads\.com)",
            clean,
            re.IGNORECASE,
        )
    )


def _threads_media_key(url: str):
    clean = _decode_html_value(url).strip()
    parsed = urlparse(clean)
    # CDN signatures/query params berubah-ubah. Path cukup stabil untuk dedupe varian
    # resolusi yang menunjuk asset yang sama.
    return f"{parsed.netloc.lower()}{parsed.path}"


def _unique_threads_media(media):
    seen = set()
    unique = []

    for item in media:
        url = _decode_html_value(item.get("url"))
        media_type = item.get("type")
        if not url or media_type not in {"video", "image"}:
            continue
        if not _is_threads_asset_url(url, media_type):
            continue

        key = (media_type, _threads_media_key(url))
        if key in seen:
            continue
        seen.add(key)
        unique.append(
            {
                "url": url,
                "type": media_type,
                "width": int(item.get("width") or 0),
                "height": int(item.get("height") or 0),
                "source": item.get("source") or "unknown",
                "score": int(item.get("score") or 0),
            }
        )

    return unique


def _threads_best_variant(candidates, media_type: str):
    valid = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        url = _decode_html_value(item.get("url") or item.get("src") or "")
        if not _is_threads_asset_url(url, media_type):
            continue
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        valid.append(
            {
                "url": url,
                "type": media_type,
                "width": width,
                "height": height,
                "source": "threads-json",
                "score": width * height,
            }
        )

    if not valid:
        return None

    return max(valid, key=lambda item: (item["width"] * item["height"], item["width"], item["height"]))


def _collect_threads_media_object(value, output, path=None):
    path = path or []
    if not isinstance(value, dict):
        return

    path_text = ".".join(str(part).lower() for part in path)
    if any(
        marker in path_text
        for marker in (
            "profile_pic",
            "avatar",
            "user.profile",
            "link_preview_attachment",
            "quoted_post",
            "reposted_post",
        )
    ):
        # Media di atas bukan media upload utama milik post target.
        return

    carousel = value.get("carousel_media")
    if isinstance(carousel, list) and carousel:
        for index, child in enumerate(carousel):
            if isinstance(child, dict):
                _collect_threads_media_object(child, output, [*path, "carousel_media", str(index)])
        # Tetap lanjut karena object parent kadang juga memuat video utama.

    video_versions = value.get("video_versions")
    has_video = isinstance(video_versions, list) and bool(video_versions)
    if has_video:
        best_video = _threads_best_variant(video_versions, "video")
        if best_video:
            output.append(best_video)

    # Pada media video, image_versions2 biasanya hanya thumbnail/cover. Jangan
    # mengirim thumbnail itu sebagai gambar terpisah jika video aslinya tersedia.
    image_versions = value.get("image_versions2")
    if isinstance(image_versions, dict) and not has_video:
        candidates = image_versions.get("candidates")
        if isinstance(candidates, list):
            best_image = _threads_best_variant(candidates, "image")
            if best_image:
                output.append(best_image)


def _find_threads_post_roots(value, post_code: str | None, roots=None):
    roots = roots if roots is not None else []
    if isinstance(value, dict):
        code = value.get("code") or value.get("shortcode")
        if post_code and str(code or "") == post_code:
            roots.append(value)
        for child in value.values():
            if isinstance(child, (dict, list)):
                _find_threads_post_roots(child, post_code, roots)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                _find_threads_post_roots(child, post_code, roots)
    return roots


def _collect_threads_media_recursive(value, output, path=None):
    path = path or []
    if isinstance(value, dict):
        _collect_threads_media_object(value, output, path)
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                _collect_threads_media_recursive(child, output, [*path, str(key)])
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, (dict, list)):
                _collect_threads_media_recursive(child, output, [*path, str(index)])


def _extract_threads_json_payloads(html_text: str):
    payloads = []
    for body in re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", html_text or "", flags=re.IGNORECASE):
        decoded = html.unescape(body.strip())
        if not decoded or decoded[0] not in "[{":
            continue
        try:
            payloads.append(json.loads(decoded))
        except Exception:
            continue
    return payloads


def _extract_threads_structured_media(html_text: str, post_code: str | None = None):
    payloads = _extract_threads_json_payloads(html_text)
    if not payloads:
        return []

    exact_roots = []
    if post_code:
        for payload in payloads:
            _find_threads_post_roots(payload, post_code, exact_roots)

    output = []
    if exact_roots:
        for root in exact_roots:
            _collect_threads_media_recursive(root, output, ["target_post"])
    elif post_code:
        # Jangan broad-scan seluruh hydration page jika root post target tidak
        # ditemukan. Broad scan pernah mengambil social-preview/link-preview image
        # dari object lain dan mengirim kartu putih bertuliskan Threads.
        return []
    else:
        for payload in payloads:
            _collect_threads_media_recursive(payload, output, ["page"])

    return _unique_threads_media(output)


def _parse_srcset(srcset: str):
    variants = []
    for part in str(srcset or "").split(","):
        chunk = part.strip()
        if not chunk:
            continue
        pieces = chunk.rsplit(None, 1)
        url = _decode_html_value(pieces[0])
        width = 0
        if len(pieces) == 2:
            match = re.match(r"(\d+)w$", pieces[1].strip(), re.IGNORECASE)
            if match:
                width = int(match.group(1))
        variants.append((url, width))
    return variants


def _extract_threads_dom_media(html_text: str, post_code: str | None = None):
    output = []
    text = html_text or ""

    for match in re.finditer(r"<img\b[^>]*>", text, flags=re.IGNORECASE):
        tag = match.group(0)
        alt = (_get_html_attribute(tag, "alt") or "").lower()
        if any(marker in alt for marker in ("profile picture", "profile photo", "avatar", "foto profil")):
            continue

        srcset = _get_html_attribute(tag, "srcset") or ""
        variants = _parse_srcset(srcset)
        src = _get_html_attribute(tag, "src")
        if src:
            variants.append((src, 0))
        variants = [(url, width) for url, width in variants if _is_threads_asset_url(url, "image")]
        if not variants:
            continue

        best_url, best_width = max(variants, key=lambda item: item[1])
        # Avatar/icon umumnya kecil. Untuk candidate tanpa descriptor, izinkan hanya
        # URL post-media Instagram (t51.2885-15), bukan profile image t51.2885-19.
        if best_width and best_width < 400:
            continue
        if not best_width and not re.search(r"t51\.2885-15|cdninstagram\.com/v/t51", best_url, re.IGNORECASE):
            continue

        context = text[max(0, match.start() - 2200): min(len(text), match.end() + 2200)]
        context_lower = context.lower()

        # DOM fallback hanya boleh menerima img yang berada di sekitar struktur
        # media post. Social card Threads juga berupa CDN image besar/srcset, jadi
        # ukuran dan hostname saja tidak cukup untuk membedakannya.
        media_markers = (
            "image_versions2",
            "carousel_media",
            "original_width",
            "original_height",
            "\"media_type\"",
        )
        if not any(marker in context_lower for marker in media_markers):
            continue
        if any(marker in context_lower for marker in ("og:image", "twitter:image", "link_preview_attachment")):
            continue

        score = best_width
        if post_code and post_code.lower() in context_lower:
            score += 5000
        if re.search(r"(?:profile_pic|avatar|t51\.2885-19)", context, re.IGNORECASE):
            score -= 5000
        output.append(
            {
                "url": best_url,
                "type": "image",
                "width": best_width,
                "height": 0,
                "source": "threads-dom-srcset",
                "score": score,
            }
        )

    for match in re.finditer(r"<(?:video|source)\b[^>]*>", text, flags=re.IGNORECASE):
        tag = match.group(0)
        src = _get_html_attribute(tag, "src")
        if not src or not _is_threads_asset_url(src, "video"):
            continue
        context = text[max(0, match.start() - 1800): min(len(text), match.end() + 1800)]
        score = 1000 + (5000 if post_code and post_code in context else 0)
        output.append(
            {
                "url": src,
                "type": "video",
                "width": 0,
                "height": 0,
                "source": "threads-dom-video",
                "score": score,
            }
        )

    unique = _unique_threads_media(output)
    return sorted(unique, key=lambda item: item.get("score", 0), reverse=True)


def _extract_threads_context_media(html_text: str, post_code: str | None = None):
    decoded = _decode_html_value(html_text or "")
    output = []
    pattern = re.compile(
        r"https?://[^\"'<>\s\\]+?\.(?:mp4|mov|m4v|webm|jpg|jpeg|png|webp)(?:\?[^\"'<>\s\\]*)?",
        re.IGNORECASE,
    )

    for match in pattern.finditer(decoded):
        url = match.group(0)
        media_type = _guess_threads_media_type_from_url(url)
        if not media_type or not _is_threads_asset_url(url, media_type):
            continue

        context = decoded[max(0, match.start() - 900): min(len(decoded), match.end() + 900)].lower()
        score = 0
        if post_code and post_code.lower() in context:
            score += 30
        if "image_versions2" in context:
            score += 24 if media_type == "image" else 4
        if "candidates" in context:
            score += 12 if media_type == "image" else 2
        if "video_versions" in context:
            score += 24 if media_type == "video" else 2
        if "carousel_media" in context:
            score += 10
        if "original_width" in context or "original_height" in context:
            score += 8
        if any(marker in context for marker in ("profile_pic", "avatar", "t51.2885-19")):
            score -= 40
        if any(marker in context for marker in ("og:image", "twitter:image")):
            score -= 30

        threshold = 12 if media_type == "image" else 8
        if score >= threshold:
            output.append(
                {
                    "url": url,
                    "type": media_type,
                    "width": 0,
                    "height": 0,
                    "source": "threads-html-context",
                    "score": score,
                }
            )

    unique = _unique_threads_media(output)
    return sorted(unique, key=lambda item: item.get("score", 0), reverse=True)


def _extract_threads_video_meta(html_text: str):
    # Video metadata umumnya menunjuk file video langsung. Image metadata sengaja
    # TIDAK dipakai sebagai default karena Threads dapat mengubah og:image menjadi
    # branded social-preview card (putih + logo/tulisan Threads).
    output = []
    for url in _extract_meta_values(
        html_text,
        ("og:video", "og:video:url", "og:video:secure_url", "twitter:player:stream"),
    ):
        if _is_threads_asset_url(url, "video"):
            output.append(
                {
                    "url": url,
                    "type": "video",
                    "width": 0,
                    "height": 0,
                    "source": "threads-video-meta",
                    "score": 1,
                }
            )
    return _unique_threads_media(output)


def _merge_threads_media(*groups):
    merged = []
    seen = set()
    for group in groups:
        for item in group or []:
            key = (item.get("type"), _threads_media_key(item.get("url")))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _extract_threads_media_from_html(html_text: str, post_code: str | None = None):
    # Prioritas sengaja bersifat fallback, bukan digabung. Begitu media asli ditemukan
    # dari JSON post, jangan campurkan kandidat lain dari meta/HTML karena kandidat
    # itu dapat berupa preview card Threads atau thumbnail.
    structured = _extract_threads_structured_media(html_text, post_code)
    if structured:
        return structured

    dom = _extract_threads_dom_media(html_text, post_code)
    if dom:
        return dom

    contextual = _extract_threads_context_media(html_text, post_code)
    if contextual:
        return contextual

    # og:image/twitter:image sengaja tidak dipakai. Hanya video meta yang masih aman
    # sebagai fallback karena URL tersebut menunjuk stream/file video langsung.
    return _extract_threads_video_meta(html_text)



def _threads_media_from_api_entries(entries):
    """Convert a downloader API response into original Threads media candidates.

    API responses may also contain profile photos, thumbnails, canonical URLs, and
    link previews. Keep only paths that look like actual downloadable media.
    """
    output = []
    seen = set()

    for entry in _unique_entries(entries or []):
        url = _decode_html_value(entry.get("url") or "").strip()
        path = str(entry.get("path") or "").lower()
        if not url or _is_probably_page_url(url):
            continue

        if any(
            marker in path
            for marker in (
                "avatar",
                "profile",
                "profile_pic",
                "thumbnail",
                "thumb",
                "cover",
                "logo",
                "link_preview",
                "preview_image",
            )
        ):
            continue

        media_type = _guess_threads_media_type_from_url(url)
        if not media_type:
            if any(marker in path for marker in ("video", "play_url", "video_url", "download_url")):
                media_type = "video"
            elif any(marker in path for marker in ("image", "photo", "picture", "media_url", "carousel")):
                media_type = "image"

        if media_type not in {"image", "video"}:
            continue
        if not _is_threads_asset_url(url, media_type) and not _has_ext(
            url,
            [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v", ".webm"],
        ):
            continue

        key = (media_type, _threads_media_key(url))
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "url": url,
                "type": media_type,
                "width": 0,
                "height": 0,
                "source": "threads-vreden-api",
                "score": 10000,
            }
        )

    return output[:MAX_FILES]


def _extract_threads_media_from_api_sync(url: str):
    api_result, source = _call_api_candidates("threads", url)
    media = _threads_media_from_api_entries(api_result.get("entries") or [])
    if not media:
        raise RuntimeError(f"{source} tidak mengirim media asli Threads.")
    logger.info("Threads original-media API source=%s count=%d", source, len(media))
    return media


def _extract_threads_media_sync(url: str):
    normalized_url = _normalize_threads_url(url)
    post_code = _threads_post_code(normalized_url)
    errors = []

    # Sumber pertama: API downloader yang mengembalikan media post terstruktur.
    # Ini menghindari social-preview card yang sekarang sering diberikan Threads
    # lewat og:image/raw HTML.
    try:
        return _extract_threads_media_from_api_sync(normalized_url)
    except Exception as e:
        errors.append(f"api: {e}")

    # Fallback: direct HTML tetapi dengan extractor ketat. Tidak ada og:image dan
    # tidak ada broad page scan saat root post target tidak ditemukan.
    for user_agent in THREADS_CRAWLER_USER_AGENTS:
        try:
            html_text, final_url = _request_text(
                normalized_url,
                "Threads",
                headers={
                    "user-agent": user_agent,
                    "referer": f"{THREADS_HOST}/",
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "accept-language": "en-US,en;q=0.9,id;q=0.8",
                },
                timeout=API_TIMEOUT_SECONDS,
            )
            effective_code = _threads_post_code(final_url) or post_code
            media = _extract_threads_media_from_html(html_text, effective_code)
            if media:
                logger.info(
                    "Threads strict HTML extractor source=%s count=%d",
                    media[0].get("source"),
                    len(media),
                )
                return media
            errors.append(f"html/{user_agent[:18]}: media asli tidak ditemukan")
        except Exception as e:
            errors.append(f"html/{user_agent[:18]}: {e}")

    raise RuntimeError(
        "Media asli Threads tidak ditemukan. Social-preview/og:image sengaja ditolak. "
        + " | ".join(errors[-4:])
    )


def _run_ffmpeg_to_mp3_sync(file_path: Path, index: int):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg belum terpasang, jadi audio Threads belum bisa diekstrak.")

    output_dir = GENERIC_TEMP_DIR / "threads"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"threads_audio_{int(time.time())}_{index}.mp3"

    process = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(file_path),
            "-vn",
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(output_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )

    if process.returncode != 0 or not output_path.exists():
        raise RuntimeError((process.stderr or f"ffmpeg keluar dengan kode {process.returncode}").strip())

    return output_path


def _download_threads_sync(url: str, mode: str):
    media = _extract_threads_media_sync(url)
    video_media = [item for item in media if item["type"] == "video"]
    image_media = [item for item in media if item["type"] == "image"]
    downloaded = []
    audio_files = []

    if mode == "audio" and not video_media:
        raise RuntimeError("Postingan Threads ini terdeteksi sebagai gambar, jadi tidak ada audio untuk diambil.")

    selected = (video_media if mode == "audio" else media)[:MAX_FILES]
    if not selected:
        raise RuntimeError("Media publik Threads tidak ditemukan.")

    try:
        for index, item in enumerate(selected, start=1):
            downloaded.append(_download_external_file_sync(item["url"], item["type"], index, "threads"))

        if mode != "audio":
            return downloaded

        for index, file_path in enumerate(downloaded, start=1):
            audio_files.append(_run_ffmpeg_to_mp3_sync(file_path, index))

        _cleanup(downloaded)
        return audio_files
    except Exception:
        _cleanup(downloaded)
        _cleanup(audio_files)
        raise


def _api_endpoint(base_url: str, original_url: str):
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'url': original_url})}"


def _call_api_candidates(platform_id: str, original_url: str):
    errors = []

    if platform_id == "pinterest":
        try:
            return _scrape_pinterest_media(original_url), "Pinterest Scraper"
        except Exception as e:
            errors.append(f"scraper: {e}")

    for endpoint in API_CANDIDATES.get(platform_id, []):
        try:
            data = _request_json(
                _api_endpoint(endpoint, original_url),
                _platform_info(platform_id)["name"],
                timeout=API_TIMEOUT_SECONDS,
            )
            entries = _unique_entries(_collect_url_entries(data))
            if platform_id == "pinterest" and not _has_pinterest_downloadable_entries(entries):
                errors.append("response tidak berisi media Pinterest")
                continue
            if entries:
                return {"data": data, "entries": entries}, endpoint.split("/")[2]
            errors.append("response kosong")
        except Exception as e:
            errors.append(str(e))

    raise RuntimeError(" | ".join(errors) or "Semua API gagal.")


def _normalize_generic_result(api_result, platform_id: str):
    entries = api_result["entries"]

    if platform_id == "pinterest":
        return {
            "video": _pick_pinterest_video(entries),
            "image": _pick_pinterest_image(entries),
            "images": _pick_pinterest_images(entries),
            "audio": None,
        }

    if platform_id == "soundcloud":
        return {
            "audio": _pick_best(entries, "audio") or _pick_best(entries, "video"),
            "image": _pick_best(entries, "image"),
            "images": [],
            "video": None,
        }

    return {
        "video": _pick_best(entries, "video"),
        "image": _pick_best(entries, "image"),
        "images": _pick_images(entries),
        "audio": _pick_best(entries, "audio"),
    }


def _fetch_tikwm_data_sync(tiktok_url: str):
    form_data = urlencode({"url": tiktok_url, "hd": "1"}).encode("utf-8")
    query = urlencode({"url": tiktok_url, "hd": "1"})
    attempts = (
        ("https://www.tikwm.com/api/", form_data, "https://www.tikwm.com/"),
        (f"https://www.tikwm.com/api/?{query}", None, "https://www.tikwm.com/"),
        (f"https://tikwmapi.com/api/?{query}", None, "https://tikwmapi.com/"),
    )

    errors = []
    for endpoint, request_data, referer in attempts:
        try:
            response = _request_json(
                endpoint,
                "TikWM API",
                headers={
                    "referer": referer,
                    "origin": referer.rstrip("/"),
                    "content-type": "application/x-www-form-urlencoded",
                },
                timeout=API_TIMEOUT_SECONDS,
                data=request_data,
            )
            if not isinstance(response, dict):
                raise RuntimeError("response bukan object JSON")

            code = response.get("code")
            if code not in (None, 0, "0"):
                raise RuntimeError(str(response.get("msg") or response.get("message") or f"code {code}"))

            payload = response.get("data") or response.get("result") or response
            if not isinstance(payload, dict):
                raise RuntimeError("data media kosong")

            images, videos, audios = _extract_tikwm_candidates(payload)
            if images or videos or audios:
                return payload
            raise RuntimeError(str(response.get("msg") or "URL media tidak ditemukan"))
        except Exception as e:
            errors.append(f"{urlparse(endpoint).netloc}: {e}")

    raise RuntimeError(" | ".join(errors) or "TikWM API tidak mengirim data media.")


def _guess_extension(url: str, content_type: str, media_type: str):
    ext = Path(urlparse(url).path).suffix.lower().lstrip(".")
    if ext:
        return ext

    content_type = (content_type or "").lower()
    if "video/mp4" in content_type:
        return "mp4"
    if "audio" in content_type:
        return "mp3"
    if "webp" in content_type:
        return "webp"
    if "png" in content_type:
        return "png"
    if "jpeg" in content_type or "jpg" in content_type:
        return "jpg"

    if media_type == "video":
        return "mp4"
    if media_type == "audio":
        return "mp3"
    return "jpg"


def _download_remote_file_sync(url: str, media_type: str, index: int):
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    host = (urlparse(url).netloc or "").lower()
    primary_referer = "https://www.tikwm.com/" if "tikwm" in host else "https://www.tiktok.com/"
    referers = (primary_referer, "https://www.tiktok.com/", "https://www.tikwm.com/")
    file_path = None
    last_error = None

    for attempt in range(TIKTOK_CDN_RETRIES):
        try:
            request = Request(
                url,
                headers={
                    "accept": "video/*,audio/*,image/*,*/*",
                    "accept-encoding": "identity",
                    "referer": referers[attempt % len(referers)],
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
                },
            )

            with urlopen(request, timeout=45) as response:
                if response.status >= 400:
                    raise RuntimeError(f"CDN TikTok membalas HTTP {response.status}.")

                content_type = (response.headers.get("content-type") or "").lower()
                if "text/html" in content_type or "application/json" in content_type:
                    raise RuntimeError(f"CDN mengirim {content_type}, bukan file media.")

                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > MAX_MB * 1024 * 1024:
                    raise RuntimeError(f"File TikTok lebih dari batas {MAX_MB} MB.")

                ext = _guess_extension(url, content_type, media_type)
                file_path = TEMP_DIR / f"tiktok_{time.time_ns()}_{index}.{ext}"
                total = 0

                with file_path.open("wb") as file:
                    while True:
                        chunk = response.read(128 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_MB * 1024 * 1024:
                            raise RuntimeError(f"File TikTok lebih dari batas {MAX_MB} MB.")
                        file.write(chunk)

                if total == 0:
                    raise RuntimeError("CDN TikTok mengirim file kosong.")
                return file_path
        except Exception as e:
            last_error = e
            if file_path:
                file_path.unlink(missing_ok=True)
                file_path = None
            if attempt + 1 < TIKTOK_CDN_RETRIES:
                time.sleep(0.5 * (attempt + 1))

    raise RuntimeError(str(last_error) if last_error else "CDN TikTok gagal diakses.")


def _download_external_file_sync(url: str, media_type: str, index: int, platform_id: str):
    target_dir = GENERIC_TEMP_DIR / platform_id
    target_dir.mkdir(parents=True, exist_ok=True)
    referer = {
        "pinterest": "https://www.pinterest.com/",
        "facebook": "https://www.facebook.com/",
        "soundcloud": "https://soundcloud.com/",
        "threads": f"{THREADS_HOST}/",
    }.get(platform_id, "https://www.google.com/")
    request = Request(
        url,
        headers={
            "accept": "video/*,audio/*,image/*,*/*",
            "referer": referer,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
    )

    with urlopen(request, timeout=45) as response:
        if response.status >= 400:
            raise RuntimeError(f"CDN {_platform_info(platform_id)['name']} membalas HTTP {response.status}.")

        ext = _guess_extension(url, response.headers.get("content-type"), media_type)
        file_path = target_dir / f"{platform_id}_{int(time.time())}_{index}.{ext}"
        total = 0

        with file_path.open("wb") as file:
            while True:
                chunk = response.read(128 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_MB * 1024 * 1024:
                    file_path.unlink(missing_ok=True)
                    raise RuntimeError(f"File lebih dari batas {MAX_MB} MB.")
                file.write(chunk)

    return file_path


def _download_extended_sync(platform_id: str, url: str, mode: str):
    if platform_id == "threads":
        return _download_threads_sync(url, mode), "Threads Metadata"

    api_result, source = _call_api_candidates(platform_id, url)
    result = _normalize_generic_result(api_result, platform_id)
    files = []

    if mode == "audio":
        if not result.get("audio"):
            raise RuntimeError("Audio tidak ditemukan dari response API.")
        return [_download_external_file_sync(result["audio"], "audio", 1, platform_id)], source

    if platform_id == "soundcloud":
        if not result.get("audio"):
            raise RuntimeError("Audio SoundCloud tidak ditemukan dari response API.")
        return [_download_external_file_sync(result["audio"], "audio", 1, platform_id)], source

    if result.get("video"):
        return [_download_external_file_sync(result["video"], "video", 1, platform_id)], source

    images = result.get("images") or []
    if images:
        for index, image_url in enumerate(images[:MAX_IMAGE_SEND], start=1):
            files.append(_download_external_file_sync(image_url, "image", index, platform_id))
        return files, source

    if result.get("image"):
        return [_download_external_file_sync(result["image"], "image", 1, platform_id)], source

    if result.get("audio"):
        return [_download_external_file_sync(result["audio"], "audio", 1, platform_id)], source

    raise RuntimeError("Media URL tidak ditemukan dari response API.")


async def _download_extended(platform_id: str, url: str, mode: str):
    return await asyncio.to_thread(_download_extended_sync, platform_id, url, mode)


def _normalized_candidates(*values):
    result = []
    seen = set()

    def collect(value):
        if isinstance(value, str):
            normalized = _normalize_media_url(value)
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for key in ("url", "play", "download_url", "display_image", "owner_watermark_image"):
                collect(value.get(key))

    for value in values:
        collect(value)
    return result


def _extract_tikwm_candidates(data: dict):
    video_data = data.get("video") if isinstance(data.get("video"), dict) else {}
    music_info = data.get("music_info") if isinstance(data.get("music_info"), dict) else {}
    images = _normalized_candidates(data.get("images"))
    videos = _normalized_candidates(
        data.get("hdplay"),
        data.get("play"),
        data.get("nowm"),
        video_data.get("noWatermark"),
        video_data.get("no_watermark"),
    )
    audios = _normalized_candidates(data.get("music"), music_info.get("play"), data.get("audio"))
    return images, videos, audios


def _download_tikwm_data_sync(data: dict, mode: str):
    images, videos, audios = _extract_tikwm_candidates(data)
    downloaded = []

    if mode == "audio":
        if not audios:
            raise RuntimeError("Audio TikTok tidak ditemukan dari fallback API.")
        errors = []
        for audio in audios:
            try:
                return [_download_remote_file_sync(audio, "audio", 1)]
            except Exception as e:
                errors.append(str(e))
        raise RuntimeError(" | ".join(errors))

    if images:
        for index, image_url in enumerate(images[:MAX_FILES], start=1):
            try:
                downloaded.append(_download_remote_file_sync(image_url, "image", index))
            except Exception:
                logger.warning("Gagal mengambil gambar TikTok ke-%s", index)
        if downloaded:
            return downloaded

    errors = []
    for video in videos:
        try:
            return [_download_remote_file_sync(video, "video", 1)]
        except Exception as e:
            errors.append(str(e))

    raise RuntimeError(" | ".join(errors) or "Media TikTok tidak ditemukan dari fallback API.")


def _run_tikwm_fallback_sync(url: str, mode: str):
    data = _fetch_tikwm_data_sync(url)
    return _download_tikwm_data_sync(data, mode)


async def _run_tikwm_fallback(url: str, mode: str):
    return await asyncio.to_thread(_run_tikwm_fallback_sync, url, mode)


async def _download_tiktok(url: str, mode: str):
    errors = []
    try:
        # API media langsung tidak membutuhkan cookie/ffmpeg dan lebih stabil
        # terhadap challenge TikTok dibanding ekstraksi halaman terlebih dulu.
        return await _run_tikwm_fallback(url, mode), "TikWM API"
    except Exception as e:
        errors.append(f"TikWM API: {e}")
        logger.warning("Jalur utama TikTok gagal; mencoba jalur cadangan")

    try:
        return await _run_ytdlp(url, mode), "yt-dlp"
    except Exception as e:
        errors.append(f"yt-dlp: {e}")
        logger.warning("Seluruh jalur download TikTok gagal")

    raise RuntimeError("\n".join(errors))


async def _send_downloaded_files(event, files, mode: str):
    # Slideshow TikTok dikirim sebagai satu album. Caption string pada album
    # ditempel ke item pertama dan tampil sebagai satu caption grup Telegram.
    if (
        mode != "audio"
        and len(files) > 1
        and all(_file_type(path) == "image" for path in files)
    ):
        caption = (
            "✅ Slideshow TikTok berhasil didownload\n"
            f"🖼️ Jumlah: {len(files)} gambar\n"
            "📦 Mode: Media"
        )
        await event.client.send_file(
            event.chat_id,
            list(files),
            caption=caption,
            force_document=False,
        )
        return

    for index, file_path in enumerate(files, start=1):
        file_type = _file_type(file_path)
        counter = f" ({index}/{len(files)})" if len(files) > 1 else ""
        caption = (
            f"✅ TikTok berhasil didownload{counter}\n"
            f"📦 Mode: {'Audio' if mode == 'audio' else 'Media'}"
        )

        send_kwargs = {
            "caption": caption,
            "force_document": file_type in {"audio", "document"},
        }
        if file_type == "video":
            send_kwargs.update(
                {
                    "force_document": False,
                    "supports_streaming": True,
                    "nosound_video": False,
                }
            )
        elif file_type == "image":
            send_kwargs["force_document"] = False

        await event.client.send_file(event.chat_id, file_path, **send_kwargs)

        if len(files) > 1:
            await asyncio.sleep(1)


async def _send_extended_files(event, files, platform_id: str, mode: str):
    platform = _platform_info(platform_id)

    for index, file_path in enumerate(files, start=1):
        file_type = _file_type(file_path)
        counter = f" ({index}/{len(files)})" if len(files) > 1 else ""
        caption = (
            f"✅ {platform['emoji']} {platform['name']} berhasil didownload{counter}\n"
            f"📦 Mode: {'Audio' if mode == 'audio' else 'Media'}\n"
            f"✨ Status: Berhasil tanpa ribet"
        )

        send_kwargs = {
            "caption": caption,
            "force_document": file_type in {"audio", "document"},
        }
        if file_type == "video":
            send_kwargs.update(
                {
                    "force_document": False,
                    "supports_streaming": True,
                    "nosound_video": False,
                }
            )
        elif file_type == "image":
            send_kwargs["force_document"] = False

        await event.client.send_file(event.chat_id, file_path, **send_kwargs)

        if len(files) > 1:
            await asyncio.sleep(SEND_DELAY_SECONDS)


def _story_items_from_result(result):
    stories = getattr(result, "stories", None)
    if isinstance(stories, list):
        return stories
    return list(getattr(stories, "stories", []) or [])


async def _expand_story_items(client: TelegramClient, peer, story_items):
    expanded = []
    skipped_ids = []

    for item in story_items:
        if isinstance(item, types.StoryItem):
            expanded.append(item)
        elif isinstance(item, types.StoryItemSkipped):
            skipped_ids.append(item.id)

    if skipped_ids:
        try:
            result = await client(functions.stories.GetStoriesByIDRequest(peer, skipped_ids))
            expanded.extend(
                item
                for item in _story_items_from_result(result)
                if isinstance(item, types.StoryItem)
            )
        except Exception as e:
            logger.debug("Gagal expand skipped story %s: %s", skipped_ids, e)

    return expanded


async def _fetch_telegram_story_items(client: TelegramClient, target: dict):
    if not target:
        raise RuntimeError("Target status Telegram tidak ditemukan.")

    if target.get("stories"):
        try:
            peer = await client.get_input_entity(target["peer"])
        except Exception:
            peer = target["peer"]
        source = target.get("source", "story message")
        return peer, await _expand_story_items(client, peer, target["stories"]), source

    peer = await client.get_input_entity(target["peer"])

    story_ids = target.get("story_ids") or []
    if story_ids:
        result = await client(functions.stories.GetStoriesByIDRequest(peer, story_ids))
        source = target.get("source", "story id")
        return peer, await _expand_story_items(client, peer, _story_items_from_result(result)), source

    mode = target.get("mode") or "auto"
    if mode == "active":
        result = await client(functions.stories.GetPeerStoriesRequest(peer))
        return peer, await _expand_story_items(client, peer, _story_items_from_result(result)), "status aktif"

    if mode == "pinned":
        result = await client(functions.stories.GetPinnedStoriesRequest(peer, 0, TELEGRAM_STORY_LIMIT))
        return peer, await _expand_story_items(client, peer, _story_items_from_result(result)), "status pinned profile"

    if mode == "all":
        active_result = await client(functions.stories.GetPeerStoriesRequest(peer))
        active_stories = await _expand_story_items(client, peer, _story_items_from_result(active_result))

        pinned_result = await client(functions.stories.GetPinnedStoriesRequest(peer, 0, TELEGRAM_STORY_LIMIT))
        pinned_stories = await _expand_story_items(client, peer, _story_items_from_result(pinned_result))

        stories = []
        seen = set()
        for story in [*active_stories, *pinned_stories]:
            story_id = getattr(story, "id", None)
            if story_id in seen:
                continue
            seen.add(story_id)
            stories.append(story)
        return peer, stories, "status aktif + pinned profile"

    result = await client(functions.stories.GetPeerStoriesRequest(peer))
    stories = await _expand_story_items(client, peer, _story_items_from_result(result))
    if stories:
        return peer, stories, "status aktif"

    result = await client(functions.stories.GetPinnedStoriesRequest(peer, 0, TELEGRAM_STORY_LIMIT))
    return peer, await _expand_story_items(client, peer, _story_items_from_result(result)), "status pinned profile"


async def _telegram_peer_label(client: TelegramClient, peer):
    try:
        entity = await client.get_entity(peer)
    except Exception:
        return str(peer)

    username = getattr(entity, "username", None)
    if username:
        return f"@{username}"

    title = getattr(entity, "title", None)
    if title:
        return title

    first_name = getattr(entity, "first_name", None) or ""
    last_name = getattr(entity, "last_name", None) or ""
    name = f"{first_name} {last_name}".strip()
    return name or str(getattr(entity, "id", peer))


def _trim_story_caption(header_lines, story_caption: str):
    header = "\n".join(header_lines)
    story_caption = (story_caption or "").strip()
    if not story_caption:
        return header

    available = 1000 - len(header) - 2
    if available < 80:
        return header

    if len(story_caption) > available:
        story_caption = f"{story_caption[:available - 3]}..."

    return f"{header}\n\nCaption:\n{story_caption}"


async def _download_telegram_story_files(client: TelegramClient, stories):
    TELEGRAM_STORY_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = []

    for story in stories[:TELEGRAM_STORY_LIMIT]:
        if not isinstance(story, types.StoryItem) or not getattr(story, "media", None):
            continue

        file_path = await client.download_media(story.media, file=TELEGRAM_STORY_TEMP_DIR)
        if not file_path:
            continue

        path = Path(file_path)
        if path.exists() and path.stat().st_size > MAX_MB * 1024 * 1024:
            path.unlink(missing_ok=True)
            raise RuntimeError(f"Story ID {story.id} lebih dari batas {MAX_MB} MB.")

        downloaded.append({"file": path, "story": story})

    if not downloaded:
        raise RuntimeError("Tidak ada media story yang bisa didownload.")

    return downloaded


async def _send_telegram_story_files(event, downloaded, peer_label: str):
    for index, item in enumerate(downloaded, start=1):
        file_path = item["file"]
        story = item["story"]
        file_type = _file_type(file_path)
        counter = f" ({index}/{len(downloaded)})" if len(downloaded) > 1 else ""
        header_lines = [
            f"✅ Telegram status berhasil didownload{counter}",
            f"👤 Dari: {peer_label}",
            f"📌 Story ID: {story.id}",
        ]

        if getattr(story, "pinned", False):
            header_lines.append("📍 Pinned profile: ya")

        caption = _trim_story_caption(header_lines, getattr(story, "caption", ""))
        send_kwargs = {
            "caption": caption,
            "force_document": file_type in {"audio", "document"},
            "parse_mode": None,
        }

        if file_type == "video":
            send_kwargs.update(
                {
                    "force_document": False,
                    "supports_streaming": True,
                    "nosound_video": False,
                }
            )
        elif file_type == "image":
            send_kwargs["force_document"] = False

        await event.client.send_file(event.chat_id, file_path, **send_kwargs)

        if len(downloaded) > 1:
            await asyncio.sleep(SEND_DELAY_SECONDS)


async def _process_telegram_story_download(event, target, status):
    downloaded = []

    try:
        peer, stories, _source = await _fetch_telegram_story_items(event.client, target)
        stories = [
            story
            for story in stories
            if isinstance(story, types.StoryItem) and getattr(story, "media", None)
        ][:TELEGRAM_STORY_LIMIT]

        if not stories:
            raise RuntimeError(
                "Status tidak ditemukan. Bisa jadi sudah expired, private, atau belum ada pinned story."
            )

        peer_label = await _telegram_peer_label(event.client, peer)
        await status.edit(f"✅ Telegram status ditemukan ({len(stories)}). Mendownload media...")
        downloaded = await _download_telegram_story_files(event.client, stories)
        await status.edit("✅ Download selesai. Mengirim file...")
        await _send_telegram_story_files(event, downloaded, peer_label)
        await status.edit(f"✅ Telegram status selesai dikirim ({len(downloaded)} file).")
    except Exception:
        logger.warning("Download Telegram status gagal")
        await status.edit(
            "❌ Gagal download Telegram status.\n"
            "💡 Pastikan akun ini bisa melihat status tersebut. Bot tidak bisa bypass private/expired story."
        )
    finally:
        _cleanup([item["file"] for item in downloaded])


async def _process_download(event, url: str, mode: str, status):
    files = []

    try:
        files, _source = await _download_tiktok(url, mode)
        await status.edit("✅ Download selesai. Mengirim file...")
        await _send_downloaded_files(event, files, mode)
        await status.edit(f"✅ TikTok selesai dikirim ({len(files)} file).")
    except Exception:
        logger.warning("Download TikTok gagal")
        await status.edit(
            "❌ Gagal download TikTok.\n"
            "💡 Pastikan link publik dan coba kembali beberapa saat lagi."
        )
    finally:
        _cleanup(files)


async def _process_platform_download(event, platform_id: str, url: str, mode: str, status):
    if platform_id == "tiktok":
        await _process_download(event, url, mode, status)
        return

    if platform_id == "telegram_story":
        target = url if isinstance(url, dict) else _parse_telegram_story_target(url)
        await _process_telegram_story_download(event, target, status)
        return

    platform = _platform_info(platform_id)
    files = []

    try:
        files, _source = await _download_extended(platform_id, url, mode)
        await status.edit(f"✅ {platform['emoji']} Download selesai. Mengirim file...")
        await _send_extended_files(event, files, platform_id, mode)
        await status.edit(
            f"✅ {platform['emoji']} {platform['name']} selesai dikirim ({len(files)} file)."
        )
    except Exception:
        logger.warning("Download %s gagal", platform["name"])
        await status.edit(
            f"❌ Gagal download {platform['emoji']} {platform['name']}.\n"
            "💡 Pastikan link publik dan coba kembali beberapa saat lagi."
        )
    finally:
        _cleanup(files)


async def _send_detector_menu(event, platform_id: str, url: str):
    platform = _platform_info(platform_id)
    menu = await event.respond(
        f"{platform['emoji']} Link {platform['name']} terdeteksi!\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎛️ Pilih format download:\n\n"
        "1️⃣ Media terbaik\n"
        "2️⃣ Audio saja\n"
        "3️⃣ Batal\n\n"
        "💬 Balas angka pilihan di chat ini.\n"
        "⏳ Menu berlaku 2 menit.\n"
        "🚀 Support: TikTok, Pinterest, Facebook, SoundCloud, Threads, Telegram Status"
    )
    _remember_session(event, url, menu.id, platform_id)


async def setup_plugin(client: TelegramClient):
    @client.on(events.NewMessage(outgoing=True))
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def tiktok_choice_handler(event):
        if not event.is_private:
            return

        if inspect_message_extended_media(event.message):
            logger.info("Choice downloader dilewati: MessageExtendedMedia diprioritaskan")
            return

        text = (event.message.raw_text or "").strip()
        if text not in {"1", "2", "3"}:
            return

        session = _get_session(event)
        if not session:
            return

        _clear_session(event)
        if _is_outgoing(event):
            try:
                await event.delete()
            except Exception:
                pass

        platform_id = session.get("platform_id", "tiktok")
        platform = _platform_info(platform_id)

        if text == "3":
            await _detector_status_message(
                event,
                session,
                f"🛑 Download {platform['emoji']} {platform['name']} dibatalkan.",
            )
            return

        mode = "audio" if text == "2" else "media"
        status = await _detector_status_message(
            event,
            session,
            f"⏳ Memproses {platform['emoji']} {platform['name']}...\n"
            "🔎 Sedang mencari dan menyiapkan media.",
        )
        await _process_platform_download(event, platform_id, session["url"], mode, status)

    @client.on(events.NewMessage(outgoing=True))
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def platform_auto_detector(event):
        # Auto detect link hanya boleh aktif di private chat/Saved Messages.
        if not event.is_private:
            return

        inspection = inspect_message_extended_media(event.message)
        if inspection:
            logger.info(
                "Auto downloader diarahkan ke MessageExtendedMedia (status=%s, items=%s)",
                inspection["status"],
                inspection["item_count"],
            )
            return

        if parse_event_command(event):
            return

        platform_id, url = _detect_platform(event.message.raw_text or "")
        if not platform_id or not url:
            return

        logger.info("Link %s terdeteksi otomatis", platform_id)
        if platform_id == "telegram_story":
            status = await event.respond(
                "⏳ Memproses 📱 Telegram Status...\n"
                "🔎 Sedang mencari dan menyiapkan media."
            )
            await _process_platform_download(event, platform_id, url, "media", status)
            return

        await _send_detector_menu(event, platform_id, url)

    @client.on(events.NewMessage(outgoing=True))
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def downloader_command_handler(event):
        command_parts = parse_event_command(event)
        if not command_parts or command_parts[0] not in COMMAND_PLATFORM:
            return

        _, inspection = await _event_extended_media(event, include_reply=True)
        if inspection:
            await _reply_text(
                event,
                format_message_extended_media(inspection),
            )
            return

        command = command_parts[0]
        forced_platform = COMMAND_PLATFORM[command]
        target = await _get_command_target(event)

        if forced_platform == "tiktok":
            platform_id = "tiktok"
            url = _extract_tiktok_url(target)
        elif forced_platform == "telegram_story":
            platform_id = "telegram_story"
            story_target_text = " ".join(command_parts[1:]).strip()
            url = await _get_telegram_story_target(event, story_target_text)
        elif forced_platform:
            platform_id = forced_platform
            url = _extract_first_url(target) or (
                target if platform_id == "pinterest" and _parse_pinterest_pin_url(target) else None
            )
        else:
            platform_id, url = _detect_platform(target)

        if not platform_id or not url:
            await _reply_text(
                event,
                "🌈 Format Multi Downloader\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🎵 .tt <link TikTok> — download video/foto TikTok\n"
                "🎧 .ttmp3 <link TikTok> — ambil audio TikTok\n"
                "📥 .dl <link> — auto detect TikTok/Pinterest/Facebook/SoundCloud/Threads/Telegram Status\n"
                "📌 .pin <link/id> — download Pinterest\n"
                "📘 .fb <link> — download Facebook\n"
                "☁️ .sc <link> — download SoundCloud\n"
                "🧵 .threads <link> — download media Threads publik\n"
                "🎧 .threadsmp3 <link> — ambil audio dari video Threads\n"
                "📱 .status <link/@username> — download status Telegram aktif/pinned\n"
                "📱 .status pinned @username — ambil story yang dipin di profil\n"
                "📱 .status all @username — ambil status aktif + pinned\n"
                "↩️ Bisa juga reply pesan berisi link lalu kirim command."
            )
            return

        mode = "audio" if command in ("ttmp3", "tta", "sc", "soundcloud", "thmp3", "threadsmp3") else "media"
        platform = _platform_info(platform_id)
        status = await _status_message(
            event,
            f"⏳ Memproses {platform['emoji']} {platform['name']}...\n"
            "🔎 Sedang mencari dan menyiapkan media."
        )
        await _process_platform_download(event, platform_id, url, mode, status)
