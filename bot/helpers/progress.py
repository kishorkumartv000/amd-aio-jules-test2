from __future__ import annotations

import asyncio
from typing import Optional

class ProgressReporter:
    """A simple class to hold the state of a multi-stage task."""
    def __init__(self, label: str = "Task", show_system_stats: bool = True):
        self.label = label
        self.stage: str = "Preparing"

        # Download state
        self.download_percent: int = 0
        self.tracks_done: int = 0
        self.tracks_total: Optional[int] = None

        # Zip state
        self.zip_done: int = 0
        self.zip_total: int = 0

        # Upload state
        self.upload_current: int = 0
        self.upload_total: int = 0
        self.file_index: Optional[int] = None
        self.file_total: Optional[int] = None

        self._show_system_stats = show_system_stats

    # --- Synchronous State Setters ---

    def set_stage(self, stage: str):
        self.stage = stage

    def set_total_tracks(self, total: int):
        if total is not None and total >= 0:
            self.tracks_total = int(total)

    def update_download(self, percent: Optional[int] = None, tracks_done: Optional[int] = None):
        if percent is not None:
            self.download_percent = max(0, min(100, int(percent)))
        if tracks_done is not None:
            self.tracks_done = max(0, int(tracks_done))

    def update_zip(self, done: int, total: int):
        self.zip_done = max(0, int(done))
        self.zip_total = max(0, int(total))

    def update_upload(self, current: int, total: int, file_index: Optional[int] = None, file_total: Optional[int] = None, label: Optional[str] = None):
        self.upload_current = max(0, int(current))
        self.upload_total = max(0, int(total))
        if file_index is not None:
            self.file_index = int(file_index)
        if file_total is not None:
            self.file_total = int(file_total)
        if label:
            self.stage = label

    # --- Asynchronous Renderer ---

    def _make_bar(self, percent: int) -> str:
        blocks = 10
        safe_percent = max(0, min(100, int(percent)))
        filled = int((safe_percent / 100) * blocks)
        return "".join(["▰" for _ in range(filled)] + ["▱" for _ in range(blocks - filled)])

    async def render(self) -> str:
        """Renders the current state into a status message string."""
        lines = []
        stage_emoji = {
            "Preparing": "🟡",
            "Downloading": "⬇️",
            "Processing": "🛠️",
            "Zipping": "🗜️",
            "Uploading": "⬆️",
            "Finalizing": "🧹",
            "Done": "✅",
        }
        lines.append(f"{stage_emoji.get(self.stage, '🔄')} {self.label} • {self.stage}")

        if self._show_system_stats:
            stats_line = await asyncio.to_thread(self._get_system_stats_sync)
            if stats_line:
                lines.append(stats_line)

        if self.stage in ("Downloading", "Processing") or self.download_percent > 0 or self.tracks_done > 0:
            bar = self._make_bar(self.download_percent)
            tracks = f"{self.tracks_done}/{self.tracks_total}" if self.tracks_total else f"{self.tracks_done}"
            lines.append(f"🎶 {bar} {self.download_percent}%  •  Tracks: {tracks}")

        if self.zip_total > 0:
            percent = int((self.zip_done / self.zip_total) * 100) if self.zip_total else 0
            bar = self._make_bar(percent)
            lines.append(f"🗜️ {bar} {percent}%  •  Files: {self.zip_done}/{self.zip_total}")

        if self.upload_total > 0:
            percent = int((self.upload_current / self.upload_total) * 100) if self.upload_total else 0
            bar = self._make_bar(percent)
            idx = f" ({self.file_index}/{self.file_total})" if self.file_index and self.file_total else ""
            lines.append(f"📤 {bar} {percent}%{idx}")

        return "\n".join(lines)

    def _get_system_stats_sync(self) -> str | None:
        """Synchronous method to get system stats. Meant to be run in a thread."""
        try:
            import psutil, shutil, os
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            base = os.getenv("LOCAL_STORAGE") or os.getcwd()
            du = shutil.disk_usage(base)

            mem_used = int(mem.used / (1024**3))
            mem_total = int(mem.total / (1024**3))
            disk_used = int(du.used / (1024**3))
            disk_total = int(du.total / (1024**3))

            return f"🖥️ CPU {cpu}% • RAM {mem_used}/{mem_total} GB • Disk {disk_used}/{disk_total} GB"
        except Exception:
            return None