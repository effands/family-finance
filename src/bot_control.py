"""Small process controller for the Telegram polling worker.

The web app and bot run under the same hosting account.  This module keeps the
control surface deliberately small and does not require psutil/systemd, which
are commonly unavailable on shared hosting.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


@dataclass(frozen=True)
class BotStatus:
    running: bool
    pid: int | None


class BotController:
    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self.pid_file = self.root / "data" / "bot.pid"
        self.log_file = self.root / "bot.log"

    def _read_pid(self) -> int | None:
        try:
            return int(self.pid_file.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError, OSError):
            return None

    @staticmethod
    def _is_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False

    def status(self) -> BotStatus:
        pid = self._read_pid()
        if pid is not None and self._is_alive(pid):
            return BotStatus(True, pid)
        if self.pid_file.exists():
            self.pid_file.unlink(missing_ok=True)
        return BotStatus(False, None)

    def start(self) -> BotStatus:
        current = self.status()
        if current.running:
            return current
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        log = self.log_file.open("a", encoding="utf-8")
        kwargs = {
            "cwd": str(self.root),
            "stdin": subprocess.DEVNULL,
            "stdout": log,
            "stderr": subprocess.STDOUT,
            "close_fds": True,
        }
        if os.name != "nt":
            kwargs["start_new_session"] = True
        process = subprocess.Popen([sys.executable, "-m", "src.main"], **kwargs)
        self.pid_file.write_text(str(process.pid), encoding="utf-8")
        time.sleep(0.25)
        return self.status()

    def stop(self) -> BotStatus:
        current = self.status()
        if not current.running:
            return current
        try:
            os.kill(current.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(20):
            if not self._is_alive(current.pid):
                break
            time.sleep(0.1)
        self.pid_file.unlink(missing_ok=True)
        return self.status()

    def restart(self) -> BotStatus:
        self.stop()
        return self.start()
