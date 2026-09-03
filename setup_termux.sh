#!/bin/bash
# Setup script untuk Termux
# Run: bash setup_termux.sh

echo "=========================================="
echo "🤖 USERBOT TELEGRAM - TERMUX SETUP"
echo "=========================================="

# Update packages
echo "📦 Update packages..."
pkg update -y
pkg upgrade -y

# Install Python dan dependencies
echo "🐍 Install Python..."
pkg install -y python pip

# Install git (untuk clone repo jika perlu)
pkg install -y git

# Install Node.js untuk PM2 process manager
echo "📡 Install Node.js dan PM2..."
pkg install -y nodejs
npm install -g pm2

# Install curl (untuk monitoring)
pkg install -y curl

# Navigate to bot folder
cd /storage/emulated/0/USERBOT\ TELE 2>/dev/null || {
    echo "⚠️  Folder tidak ditemukan. Membuat folder baru..."
    mkdir -p /storage/emulated/0/USERBOT\ TELE
    cd /storage/emulated/0/USERBOT\ TELE
}

# Install Python requirements
echo "📥 Install dependencies..."
pip install -U -r requirements.txt

# Siapkan pemulihan Telegram lewat PM2 dan script Termux:Boot.
echo "🚀 Menyiapkan auto-start setelah tablet reboot..."
python termux_autostart.py

echo ""
echo "=========================================="
echo "✅ SETUP SELESAI!"
echo "=========================================="
echo ""
echo "📌 LANGKAH SELANJUTNYA:"
echo ""
echo "1. Jalankan/reload bot dengan PM2:"
echo "   bash run_24h.sh"
echo ""
echo "2. Cek status dan watch:"
echo "   pm2 status"
echo "   pm2 describe d"
echo ""
echo "3. Lihat log perubahan/restart:"
echo "   pm2 logs d"
echo ""
echo "4. Setelah reboot Termux (jika auto-boot belum dipasang):"
echo "   bash run_24h.sh"
echo ""
echo "Auto-boot: install dan buka Termux:Boot satu kali."
echo "Log boot: ~/.pm2/termux-boot.log"
echo ""
echo "Catatan: gunakan ecosystem.config.js; jangan 'pm2 start index.py'"
echo ""
echo "=========================================="
