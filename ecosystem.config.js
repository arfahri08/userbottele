module.exports = {
  apps: [
    {
      name: "d",
      cwd: __dirname,
      script: "index.py",
      interpreter: "python",
      exec_mode: "fork",
      instances: 1,
      autorestart: true,
      restart_delay: 2000,
      min_uptime: 5000,
      max_restarts: 20,
      kill_timeout: 5000,

      // Batasi ke source/config agar session dan file runtime tidak memicu
      // restart. Folder modules tetap mencakup file plugin baru.
      watch: ["index.py", "config.py", ".env", "modules"],
      watch_delay: 2500,
      ignore_watch: [
        "[\\/]\\.git",
        "[\\/]\\.vscode",
        "__pycache__",
        "\\.pyc$",
        "[\\/]data",
        "[\\/]downloads",
        "[\\/]logs",
        "userbot_session.*\\.session",
      ],

      // Polling lebih andal untuk shared storage Android
      // (/storage/emulated/0) dibanding filesystem events biasa.
      watch_options: {
        usePolling: true,
        interval: 1500,
        binaryInterval: 1500,
        ignoreInitial: true,
        followSymlinks: false,
        awaitWriteFinish: {
          stabilityThreshold: 2000,
          pollInterval: 500,
        },
      },

      env: {
        PYTHONUNBUFFERED: "1",
        // Cadangan jika Chokidar/PM2 gagal membaca perubahan di shared
        // storage Android. Watcher Python akan exec ulang proses yang sama.
        INTERNAL_SOURCE_WATCH_ENABLED: "true",
        INTERNAL_SOURCE_WATCH_INTERVAL: "3",
        INTERNAL_SOURCE_WATCH_DEBOUNCE: "2",
      },
    },
  ],
};
