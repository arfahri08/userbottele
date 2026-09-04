<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=32&duration=2800&pause=900&color=F05A47&center=true&vCenter=true&width=700&lines=Modulogic+by+Fahri;Telegram+Automation+%7C+Telethon;Build.+Automate.+Stay+Curious." alt="Modulogic by Fahri animated title">
</p>

<p align="center">
  <strong>Modular tools for a smarter Telegram workflow.</strong><br>
  Built with Python and Telethon for personal automation.
</p>

<p align="center">
  <a href="https://github.com/arfahri08/userbottele"><img src="https://img.shields.io/github/stars/arfahri08/userbottele?style=for-the-badge&logo=github&label=Stars&color=F5B942" alt="GitHub stars"></a>
  <a href="https://github.com/arfahri08/userbottele/network/members"><img src="https://img.shields.io/github/forks/arfahri08/userbottele?style=for-the-badge&logo=github&label=Forks&color=4C9AFF" alt="GitHub forks"></a>
  <a href="https://github.com/arfahri08/userbottele"><img src="https://img.shields.io/github/last-commit/arfahri08/userbottele?style=for-the-badge&logo=git&label=Updated&color=36B37E" alt="Last commit"></a>
</p>

<p align="center">
  <a href="https://www.instagram.com/antoniusfahri"><img src="https://img.shields.io/badge/Instagram-antoniusfahri-E4405F?style=for-the-badge&logo=instagram&logoColor=white" alt="Instagram Antonius Fahri"></a>
  <a href="https://www.linkedin.com/in/a-rachman-fahri-9998443b8"><img src="https://img.shields.io/badge/LinkedIn-A._Rachman_Fahri-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn A. Rachman Fahri"></a>
</p>

> **Catatan penting:** project ini dirancang untuk penggunaan pribadi pada akun Anda sendiri. Hormati privasi, hak cipta, aturan Telegram, dan izin pemilik konten.

## Tentang Modulogic

Modulogic adalah userbot Telegram modular yang menjaga otomasi tetap teratur: setiap fitur hidup sebagai plugin terpisah, konfigurasi tetap jelas, dan data pribadi tetap berada di lingkungan lokal Anda.

## Fitur

- Arsitektur runtime tunggal berbasis Telethon.
- Auto-load plugin dari folder `modules/`.
- Auto-reply, AFK, reminder, menu, ping, purge, dan get ID.
- Anti-delete untuk pesan private yang terhapus.
- Anti-view-once untuk media yang diterima secara private.
- Penanganan restricted/no-forward media, termasuk album.
- Deteksi paid media tanpa mencoba melewati paywall Telegram.
- Downloader dan pengambil media dari link Telegram.
- Tujuan terpusat untuk log dan media: Saved Messages atau channel pribadi Anda.
- Media manager, poll/reaction tools, QR generator, permission guard, dan health monitor.

## Persyaratan

- Python 3.10 atau lebih baru
- Akun Telegram pribadi
- API ID dan API hash dari [my.telegram.org](https://my.telegram.org)
- Channel pribadi opsional untuk menampung log dan media

## Instalasi Lokal

### 1. Clone repository

```bash
git clone https://github.com/arfahri08/userbottele.git
cd userbottele
```

### 2. Buat virtual environment

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 -m pip install -r requirements.txt
```

Linux, macOS, atau Termux:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Untuk fitur musik, instal tambahan:

```bash
python3 -m pip install -r requirements-music.txt
```

Untuk mengaktifkan pembacaan QR dari gambar (`.readqr`), instal dependency opsional:

```bash
python3 -m pip install -r requirements-qr.txt
```

Fitur `.qr` untuk membuat QR tetap tersedia tanpa dependency OpenCV. OpenCV hanya diperlukan oleh `.readqr`.

### 3. Siapkan environment

Salin `.env.example` menjadi `.env`, lalu isi nilai milik Anda sendiri:

```bash
cp .env.example .env
```

Di Windows PowerShell, gunakan:

```powershell
Copy-Item .env.example .env
```

Nilai yang wajib diganti:

- `API_ID`: API ID dari akun Telegram Anda.
- `API_HASH`: API hash dari akun Telegram Anda.
- `PHONE_NUMBER`: nomor Telegram Anda dengan kode negara, misalnya `+62...`.

Jangan pernah memasukkan API hash, nomor telepon, password, token, atau file session ke repository publik.

### 4. Atur channel tujuan (opsional)

Secara default, log dan media dikirim ke Saved Messages. Untuk memindahkannya ke channel pribadi:

1. Tambahkan akun userbot sebagai anggota channel dan beri izin mengirim media.
2. Jalankan userbot.
3. Ketik `.id` di channel tersebut.
4. Salin `Channel ID` yang ditampilkan.
5. Buka `config.py` dan isi:

```python
SAVED_MESSAGES_TARGET_ID = -1001234567890
```

Atau atur melalui `.env`:

```env
SAVED_MESSAGES_TARGET=-1001234567890
```

Nilai `.env` akan meng-override nilai di `config.py`. Jika nilainya `0`, output kembali ke Saved Messages.

### 5. Jalankan

```bash
python index.py
```

Pada login pertama, masukkan kode verifikasi Telegram. File `userbot_session.session` akan dibuat secara lokal dan sengaja tidak diikutkan ke Git.

## Menjalankan di Termux

Gunakan script yang tersedia:

```bash
bash setup_termux.sh
bash QUICK_START_TERMUX.sh
```

Pastikan `.env` dan file session hanya berada di perangkat/server pribadi Anda.

## Konfigurasi Fitur

Fitur dapat diaktifkan atau dimatikan melalui `.env` dengan nilai `True` atau `False`, misalnya:

```env
ANTI_DELETE_ENABLED=True
ANTI_VIEWONCE_ENABLED=True
RESTRICTED_CHANNEL_ENABLED=True
LOGGER_ENABLED=True
TELEGRAM_MEDIA_LINK_ENABLED=True
```

Lihat `.env.example` untuk daftar konfigurasi yang tersedia.

## Command Tambahan

```text
.disk                         Lihat ukuran folder downloads/
.cleanup 7                    Hapus file downloads yang lebih lama dari 7 hari
.poll Pertanyaan | Ya | Tidak Buat poll Telegram
.react 👍                     Beri reaction pada pesan yang direply
.qr https://contoh.com        Buat QR code dari teks atau link
.readqr                       Baca QR dari gambar yang direply
.health                       Lihat koneksi, uptime, RAM, dan CPU
```

Untuk membatasi command agar hanya berjalan di chat tertentu, isi `COMMAND_ALLOWED_CHAT_IDS` dengan ID chat yang dipisahkan koma. Kosong berarti command tetap tersedia di semua chat, tetapi hanya command outgoing dari akun userbot yang diproses.

## Keamanan Sebelum Repository Publik

File berikut sengaja diabaikan oleh Git:

- `.env` dan konfigurasi environment lokal
- File session Telegram
- Password SFTP/FTP dan file kunci pribadi
- Folder `downloads/` dan cache runtime
- Log serta riwayat identitas lokal

Sebelum push, periksa file yang akan dikirim:

```bash
git status --short
git diff --cached --name-only
```

Jika credential pernah terlanjur masuk commit, segera cabut atau rotate credential tersebut. Menghapus file pada commit terbaru saja tidak menghapusnya dari seluruh riwayat Git.

## Update ke GitHub

```bash
git add -A
git commit -m "Describe your change"
git push
```

## Lisensi

Tambahkan lisensi yang sesuai sebelum mendistribusikan project ini secara luas.

## Kontak

Ikuti update dan project lainnya:

- Instagram: [@antoniusfahri](https://www.instagram.com/antoniusfahri)
- LinkedIn: [A. Rachman Fahri](https://www.linkedin.com/in/a-rachman-fahri-9998443b8)
