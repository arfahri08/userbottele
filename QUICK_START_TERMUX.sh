#!/bin/bash
# QUICK START TERMUX USERBOT - Copy & Paste Commands
# Salin perintah di bawah satu per satu ke Termux

echo "🤖 QUICK START TELEGRAM USERBOT 24/7 DI TERMUX"
echo ""
echo "📋 STEP-BY-STEP COMMANDS:"
echo ""

echo "1️⃣  UPDATE TERMUX"
echo "$ pkg update -y && pkg upgrade -y"
echo ""

echo "2️⃣  INSTALL PYTHON, NODE.JS & PM2"
echo "$ pkg install -y python pip nodejs git curl"
echo "$ npm install -g pm2"
echo ""

echo "3️⃣  GO TO STORAGE"
echo "$ cd /storage/emulated/0"
echo ""

echo "4️⃣  COPY BOT FOLDER"
echo "Manual: Copy folder 'USERBOT TELE' ke /storage/emulated/0"
echo "$ ls -la  # Verifikasi folder sudah ada"
echo ""

echo "5️⃣  ENTER BOT FOLDER"
echo "$ cd USERBOT\ TELE"
echo ""

echo "6️⃣  INSTALL DEPENDENCIES"
echo "$ pip install -U -r requirements.txt"
echo "$ python termux_autostart.py"
echo "    - Install dan buka Termux:Boot satu kali untuk auto-start setelah reboot"
echo ""

echo "7️⃣  EDIT .env (ISI CREDENTIALS)"
echo "$ nano .env"
echo "    - Isi: API_ID, API_HASH, PHONE_NUMBER"
echo "    - Tekan: Ctrl+X → Y → Enter"
echo ""

echo "8️⃣  JALANKAN/RELOAD BOT (PM2 + WATCH)"
echo "$ bash run_24h.sh"
echo "    - Wajib lewat ecosystem.config.js agar watch polling terpasang"
echo ""

echo "9️⃣  CEK STATUS & KONFIG WATCH"
echo "$ pm2 status"
echo "$ pm2 describe d"
echo ""

echo "🔟 LIHAT LOG HOT-RELOAD"
echo "$ pm2 logs d"
echo ""

echo "═══════════════════════════════════════"
echo "✅ SELESAI! Bot siap 24/7"
echo "═══════════════════════════════════════"
