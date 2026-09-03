"""Polling fallback untuk hot-reload source di shared storage Android."""

import asyncio
import hashlib
import logging
import os
import sys
from pathlib import Path


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
MODULES_DIR = BASE_DIR / "modules"
WATCH_ENABLED = os.getenv("INTERNAL_SOURCE_WATCH_ENABLED", "true").lower() == "true"

try:
    WATCH_INTERVAL = max(1.0, float(os.getenv("INTERNAL_SOURCE_WATCH_INTERVAL", "3")))
except ValueError:
    WATCH_INTERVAL = 3.0

try:
    WATCH_DEBOUNCE = max(1.0, float(os.getenv("INTERNAL_SOURCE_WATCH_DEBOUNCE", "2")))
except ValueError:
    WATCH_DEBOUNCE = 2.0

_watch_task = None


def _watched_files():
    files = [BASE_DIR / "index.py", BASE_DIR / "config.py", BASE_DIR / ".env"]
    files.extend(sorted(MODULES_DIR.glob("*.py")))
    return files


def _snapshot():
    """Hash isi file agar tetap akurat saat Android mempertahankan mtime."""
    result = {}
    for path in _watched_files():
        try:
            relative = path.relative_to(BASE_DIR).as_posix()
            digest = hashlib.blake2s(path.read_bytes()).hexdigest()
            result[relative] = digest
        except FileNotFoundError:
            result[path.name] = "<missing>"
        except OSError as e:
            logger.debug("Source watcher gagal membaca %s: %s", path, e)
    return result


def _changed_files(previous, current):
    keys = set(previous) | set(current)
    return sorted(key for key in keys if previous.get(key) != current.get(key))


async def _watch_sources():
    baseline = await asyncio.to_thread(_snapshot)
    logger.info(
        "Internal source watcher aktif (interval %.1fs, %s file)",
        WATCH_INTERVAL,
        len(baseline),
    )

    while True:
        await asyncio.sleep(WATCH_INTERVAL)
        current = await asyncio.to_thread(_snapshot)
        if current == baseline:
            continue

        changed = _changed_files(baseline, current)
        logger.info("Perubahan source terdeteksi: %s", ", ".join(changed))

        # Tunggu sampai proses copy/editor selesai. Jika snapshot masih berubah,
        # debounce diulang agar Python tidak start dari file setengah tertulis.
        stable = current
        while True:
            await asyncio.sleep(WATCH_DEBOUNCE)
            candidate = await asyncio.to_thread(_snapshot)
            if candidate == stable:
                break
            stable = candidate

        args = [sys.executable, *sys.argv]
        logger.info("Source stabil; reload proses: %s", " ".join(args))
        try:
            os.execv(sys.executable, args)
        except OSError:
            logger.exception("Internal source watcher gagal me-reload proses")
            baseline = stable


async def setup_plugin(client):
    del client
    global _watch_task

    if not WATCH_ENABLED:
        logger.info("Internal source watcher nonaktif")
        return

    if _watch_task is None or _watch_task.done():
        _watch_task = asyncio.create_task(_watch_sources(), name="internal-source-watcher")

