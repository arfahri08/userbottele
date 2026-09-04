"""
Runtime feature registry and menu text builder.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

from config import (
    ANTI_DELETE_ENABLED,
    ANTI_VIEWONCE_ENABLED,
    AUTOREPLY_ENABLED,
    LOGGER_ENABLED,
    RESTRICTED_CHANNEL_ENABLED,
    TELEGRAM_MEDIA_LINK_ENABLED,
    USERNAME_TRACKER_ENABLED,
    PAID_MEDIA_GUARD_ENABLED,
    MEDIA_MANAGER_ENABLED,
    POLL_REACTION_ENABLED,
    QR_TOOLS_ENABLED,
    HEALTH_MONITOR_ENABLED,
)

# Dipertahankan sebagai compatibility shim untuk modul lama, tetapi sengaja
# kosong agar tidak ada nama/watermark yang ikut terkirim ke chat atau caption.
WATERMARK_TEXT = ""
WATERMARK_LINE = ""


@dataclass(frozen=True)
class FeatureInfo:
    key: str
    title: str
    description: str
    module_file: str
    icon: str = "🔹"
    commands: Tuple[str, ...] = ()
    toggleable: bool = False
    startup_enabled: bool = False


FEATURES: Tuple[FeatureInfo, ...] = (
    FeatureInfo(
        key="ping",
        title="Ping & Alive",
        description="Cek respon bot, uptime, dan status runtime.",
        module_file="ping.py",
        icon="⚡",
        commands=(".ping", ".alive", ".uptime"),
        startup_enabled=True,
    ),
    FeatureInfo(
        key="getid",
        title="ID Info",
        description="Cek ID user private, grup/channel, atau orang yang direply.",
        module_file="getid.py",
        icon="🆔",
        commands=(".cekid", ".id", ".cekid @username"),
        startup_enabled=True,
    ),
    FeatureInfo(
        key="afk",
        title="AFK Mode",
        description="Balas otomatis saat kamu sedang away.",
        module_file="afk.py",
        icon="🌙",
        commands=(".afk [alasan]", ".unafk"),
        startup_enabled=True,
    ),
    FeatureInfo(
        key="notes",
        title="Notes",
        description="Simpan dan panggil catatan teks dari Saved Messages.",
        module_file="notes.py",
        icon="🗒️",
        commands=(".save", ".get", ".notes", ".delnote"),
        startup_enabled=True,
    ),
    FeatureInfo(
        key="reminder",
        title="Reminder",
        description="Jadwalkan pengingat yang tetap tersimpan setelah restart.",
        module_file="reminder.py",
        icon="⏰",
        commands=(".remind 10m <teks>", ".reminders", ".cancelrem <id>"),
        startup_enabled=True,
    ),
    FeatureInfo(
        key="purge",
        title="Purge Tools",
        description="Hapus pesan cepat dengan reply .del atau .purge.",
        module_file="purge.py",
        icon="🧹",
        commands=(".del", ".purge"),
        startup_enabled=True,
    ),
    FeatureInfo(
        key="downloader",
        title="Multi Downloader",
        description="Auto-deteksi TikTok, Pinterest, Facebook, SoundCloud, Threads, dan Telegram Status.",
        module_file="downloader.py",
        icon="🌈",
        commands=(
            "kirim link otomatis",
            ".dl <link>",
            ".tt <link>",
            ".ttmp3 <link>",
            ".pin <link/id>",
            ".fb <link>",
            ".sc <link>",
            ".threads <link>",
            ".threadsmp3 <link>",
            ".status <link/@username>",
            ".status pinned @username",
            ".status all @username",
        ),
        startup_enabled=True,
    ),
    FeatureInfo(
        key="music",
        title="Voice Chat Music",
        description="Putar audio/video YouTube di voice chat. Butuh dependency optional.",
        module_file="music.py",
        icon="🎵",
        commands=(
            ".play <judul/link>",
            ".vplay <judul/link>",
            ".playaudio <judul/link>",
            ".music",
            ".pause",
            ".resume",
            ".skip [nomor queue]",
            ".stop",
            ".clearqueue",
            ".quality 360|480|720",
            ".refresh",
        ),
        startup_enabled=True,
    ),
    FeatureInfo(
        key="autoreply",
        title="Auto Reply",
        description="Balas otomatis pesan private dengan pesan acak saat fitur ON.",
        module_file="autoreply.py",
        icon="💬",
        commands=(
            ".reply on",
            ".reply off",
            ".reply status",
            ".reply toggle",
            ".addrep <pesan>",
            ".replies",
            ".delrep <nomor>",
        ),
        toggleable=True,
        startup_enabled=AUTOREPLY_ENABLED,
    ),
    FeatureInfo(
        key="anti_viewonce",
        title="Anti View Once",
        description="Simpan media view-once dari private chat ke Saved Messages.",
        module_file="anti_viewonce.py",
        icon="👁️",
        startup_enabled=ANTI_VIEWONCE_ENABLED,
    ),
    FeatureInfo(
        key="anti_delete",
        title="Anti Delete",
        description="Simpan teks dan media pesan private yang dihapus ke Saved Messages.",
        module_file="anti_delete.py",
        icon="🗑️",
        startup_enabled=ANTI_DELETE_ENABLED,
    ),
    FeatureInfo(
        key="restricted",
        title="Restricted Channel Saver",
        description="Copy atau upload ulang pesan dari channel/group restricted.",
        module_file="restricted.py",
        icon="🔒",
        startup_enabled=RESTRICTED_CHANNEL_ENABLED,
    ),
    FeatureInfo(
        key="logger",
        title="Message Logger",
        description="Kirim log pesan private yang diedit/dihapus ke Saved Messages lengkap dengan user dan link chat.",
        module_file="logger.py",
        icon="📝",
        startup_enabled=LOGGER_ENABLED,
    ),
    FeatureInfo(
        key="username_tracker",
        title="Username History",
        description="Catat perubahan username akun yang pernah private chat berdasarkan numeric User ID.",
        module_file="username_tracker.py",
        icon="🔎",
        commands=(".usn (reply)", ".usn <user_id/@username>"),
        startup_enabled=USERNAME_TRACKER_ENABLED,
    ),
    FeatureInfo(
        key="paid_media_guard",
        title="Paid Media Guard",
        description="Deteksi media Stars dan native-forward ke Saved Messages tanpa membuka paywall.",
        module_file="paid_media_guard.py",
        icon="⭐",
        startup_enabled=PAID_MEDIA_GUARD_ENABLED,
    ),
    FeatureInfo(
        key="telegram_media_link",
        title="Telegram Media Link",
        description="Ambil media dari link pesan Telegram yang bisa diakses akun.",
        module_file="telegram_media_link.py",
        icon="🔗",
        commands=(
            "kirim link t.me/<username>/<message_id>",
            ".paidfull <link>",
            ".paidpreview <link> (manual)",
        ),
        startup_enabled=TELEGRAM_MEDIA_LINK_ENABLED,
    ),
    FeatureInfo(
        key="restart",
        title="Restart Control",
        description="Restart bot langsung dari Telegram dan kirim notifikasi saat aktif.",
        module_file="restart.py",
        icon="🔄",
        commands=(".upt",),
        startup_enabled=True,
    ),
    FeatureInfo(
        key="media_manager",
        title="Media Manager",
        description="Lihat penggunaan downloads dan hapus file lama.",
        module_file="media_manager.py",
        icon="💾",
        commands=(".disk", ".cleanup [hari]"),
        startup_enabled=MEDIA_MANAGER_ENABLED,
    ),
    FeatureInfo(
        key="poll_reaction",
        title="Poll & Reaction",
        description="Buat poll dan beri reaction pada pesan.",
        module_file="poll_reaction.py",
        icon="📊",
        commands=(".poll pertanyaan | opsi 1 | opsi 2", ".react 👍 (reply)"),
        startup_enabled=POLL_REACTION_ENABLED,
    ),
    FeatureInfo(
        key="qr_tools",
        title="QR Tools",
        description="Buat QR code dari teks atau link.",
        module_file="qr_tools.py",
        icon="🔳",
        commands=(".qr <teks/link>", ".readqr (reply gambar)"),
        startup_enabled=QR_TOOLS_ENABLED,
    ),
    FeatureInfo(
        key="health_monitor",
        title="Health Monitor",
        description="Cek koneksi, uptime, RAM, CPU, dan perubahan koneksi.",
        module_file="health_monitor.py",
        icon="🩺",
        commands=(".health",),
        startup_enabled=HEALTH_MONITOR_ENABLED,
    ),
)

_feature_state = {feature.key: feature.startup_enabled for feature in FEATURES}


def _module_exists(feature: FeatureInfo) -> bool:
    return (Path(__file__).resolve().parent / feature.module_file).exists()


def iter_available_features() -> Iterable[FeatureInfo]:
    return (feature for feature in FEATURES if _module_exists(feature))


def get_feature(key: str) -> FeatureInfo:
    for feature in FEATURES:
        if feature.key == key:
            return feature
    raise KeyError(f"Feature not registered: {key}")


def is_feature_enabled(key: str) -> bool:
    return bool(_feature_state.get(key, False))


def set_feature_enabled(key: str, enabled: bool) -> bool:
    get_feature(key)
    _feature_state[key] = bool(enabled)
    return _feature_state[key]


def toggle_feature(key: str) -> bool:
    return set_feature_enabled(key, not is_feature_enabled(key))


def get_status_label(key: str) -> str:
    return "🟢 ON" if is_feature_enabled(key) else "🔴 OFF"


def build_help_text() -> str:
    lines = [
        "🤖✨ USERBOT MENU ✨🤖",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📌🔥 STATUS FITUR AKTIF 🔥📌",
    ]

    for feature in iter_available_features():
        lines.append("")
        lines.append(f"{feature.icon} {feature.title} — {get_status_label(feature.key)}")
        lines.append(f"   ✨ {feature.description}")

        if feature.commands:
            lines.append(f"   ⚙️ Command: {', '.join(feature.commands)}")

    lines.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━",
            "⌨️🚀 COMMAND UTAMA",
            "• 🧭 .help / .menu — tampilkan menu ini",
            "• 🌈 .dl <link> — download multi-platform",
            "• 🎵 .play <judul/link> — musik/video voice chat",
            "• 💬 .reply on/off — auto reply private chat",
            "",
            "💡 Toggle runtime akan kembali ke default .env setelah restart.",
            "🎯 Kirim link ke private chat bot untuk auto-deteksi downloader.",
            "",
            WATERMARK_TEXT,
        ]
    )

    return "\n".join(lines)
