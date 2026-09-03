#!/bin/bash
# Start/reload bot melalui ecosystem PM2 agar watch config benar-benar dipakai.
# Usage: bash run_24h.sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v pm2 >/dev/null 2>&1; then
    echo "❌ PM2 belum terinstall. Jalankan: pkg install nodejs && npm install -g pm2"
    exit 1
fi

echo "🤖 Starting/reloading Telegram Userbot via PM2..."
pm2 startOrReload ecosystem.config.js --only d --update-env
pm2 save
pm2 status

echo "✅ Watch aktif. Cek event reload dengan: pm2 logs d"
