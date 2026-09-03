import os
from dotenv import load_dotenv

load_dotenv()


# Telegram API credentials
API_ID = int(os.getenv("API_ID", ""))
API_HASH = os.getenv("API_HASH", "")
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "")

# Feature settings
AUTOREPLY_ENABLED = os.getenv("AUTOREPLY_ENABLED", "False").lower() == "true"
ANTI_VIEWONCE_ENABLED = os.getenv("ANTI_VIEWONCE_ENABLED", "True").lower() == "true"
ANTI_DELETE_ENABLED = os.getenv("ANTI_DELETE_ENABLED", "True").lower() == "true"
RESTRICTED_CHANNEL_ENABLED = os.getenv("RESTRICTED_CHANNEL_ENABLED", "True").lower() == "true"
LOGGER_ENABLED = os.getenv("LOGGER_ENABLED", "True").lower() == "true"
TELEGRAM_MEDIA_LINK_ENABLED = os.getenv("TELEGRAM_MEDIA_LINK_ENABLED", "True").lower() == "true"

# Anti-viewonce target
SAVE_TO_SAVED_MESSAGES = os.getenv("SAVE_TO_SAVED_MESSAGES", "True").lower() == "true"
FORWARD_CHAT_ID = int(os.getenv("FORWARD_CHAT_ID", "0"))  # 0 means disabled

# Tujuan pusat untuk semua output yang sebelumnya masuk Saved Messages.
# Jalankan .id di channel, lalu tempel Channel ID di bawah. Contoh: -1001234567890.
SAVED_MESSAGES_TARGET_ID = -1003961764934
_saved_messages_target = os.getenv("SAVED_MESSAGES_TARGET", "").strip()
SAVED_MESSAGES_TARGET = (
    int(_saved_messages_target)
    if _saved_messages_target.lstrip("-").isdigit()
    else SAVED_MESSAGES_TARGET_ID or "me"
)

# Username history tracker
USERNAME_TRACKER_ENABLED = os.getenv("USERNAME_TRACKER_ENABLED", "True").lower() == "true"
try:
    USERNAME_TRACKER_SCAN_MINUTES = max(5, int(os.getenv("USERNAME_TRACKER_SCAN_MINUTES", "60")))
except ValueError:
    USERNAME_TRACKER_SCAN_MINUTES = 60

# Telegram Stars paid-media guard (no paywall bypass)
PAID_MEDIA_GUARD_ENABLED = os.getenv("PAID_MEDIA_GUARD_ENABLED", "True").lower() == "true"
PAID_MEDIA_FORWARD_TO_SAVED = os.getenv("PAID_MEDIA_FORWARD_TO_SAVED", "True").lower() == "true"
