"""
Auto-start handler untuk 24/7 running di Termux
Jalankan file ini untuk setup auto-start dan auto-restart
"""

import os
import shlex
import subprocess
import time
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_termux_autorestart():
    """Setup PM2 start wrapper untuk Telegram userbot di Termux."""
    
    logger.info("🔧 Setting up Termux auto-restart...")
    
    # Cek apakah sudah di Termux
    if not os.path.exists("/data/data/com.termux"):
        logger.warning("⚠️  Tidak terdeteksi sebagai Termux environment")
        logger.warning("Script ini optimal untuk Termux di Android")
        return False
    
    bot_dir = shlex.quote(str(Path(__file__).resolve().parent))

    # Seluruh start melewati ecosystem agar opsi watch/polling tidak hilang.
    startup_script = f"""#!/bin/bash
# Termux startup script
set -eu

# Ensure we're in the right directory
cd {bot_dir}

# Keep wifi awake
termux-wake-lock

# Terapkan ecosystem Telegram terbaru setiap kali Termux start.
pm2 startOrReload ecosystem.config.js --only d --update-env
pm2 save
"""
    
    termux_home = Path("/data/data/com.termux/files/home")
    script_path = termux_home / "run_bot.sh"
    boot_dir = termux_home / ".termux" / "boot"
    boot_script_path = boot_dir / "10-userbot-pm2"
    boot_log = termux_home / ".pm2" / "termux-boot.log"
    boot_script = f"""#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
sleep 20
mkdir -p {shlex.quote(str(boot_log.parent))}
bash {shlex.quote(str(script_path))} >> {shlex.quote(str(boot_log))} 2>&1
"""

    try:
        script_path.write_text(startup_script, encoding="utf-8")
        os.chmod(script_path, 0o755)
        boot_dir.mkdir(parents=True, exist_ok=True)
        boot_script_path.write_text(boot_script, encoding="utf-8")
        os.chmod(boot_script_path, 0o755)
        logger.info("✅ Startup script created: %s", script_path)
        logger.info("✅ Termux:Boot script created: %s", boot_script_path)
        return True
    except Exception as e:
        logger.error(f"❌ Error creating startup script: {e}")
        return False

def check_connectivity():
    """Check internet connectivity"""
    try:
        subprocess.run(['ping', '-c', '1', 'google.com'], 
                      timeout=3, 
                      stdout=subprocess.PIPE, 
                      stderr=subprocess.PIPE)
        return True
    except:
        return False

def monitor_bot():
    """Monitor bot health"""
    logger.info("📡 Starting bot monitoring...")
    
    while True:
        try:
            # Check connectivity
            if not check_connectivity():
                logger.warning("⚠️  No internet connection, retrying...")
                time.sleep(30)
                continue
            
            logger.info("✓ Internet OK")
            time.sleep(60)
            
        except KeyboardInterrupt:
            logger.info("⏹️  Monitoring stopped")
            break
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════╗
    ║  🤖 TELEGRAM USERBOT - TERMUX AUTO-START  ║
    ╚═══════════════════════════════════════════╝
    """)
    
    setup_termux_autorestart()
    
    print("""
    ✅ Setup selesai!
    
    📌 Cara menjalankan:
    1. Buka Termux
    2. Jalankan: bash ~/run_bot.sh
    3. Atau gunakan automation dengan Tasker
    
    📌 Untuk auto-start saat tablet boot:
    - Install Termux:Boot dari sumber yang sama dengan aplikasi Termux
    - Buka aplikasi Termux:Boot satu kali setelah instalasi
    - Script ~/.termux/boot/10-userbot-pm2 sudah dibuat otomatis
    - Log boot tersedia di ~/.pm2/termux-boot.log
    - Jangan jalankan `pm2 start index.py`; itu melewati ecosystem watch
    """)
