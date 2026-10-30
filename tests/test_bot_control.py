from pathlib import Path

from src.bot_control import BotController


def test_status_is_off_when_pid_file_is_missing(tmp_path):
    controller = BotController(tmp_path)

    status = controller.status()

    assert status.running is False
    assert status.pid is None


def test_status_removes_stale_pid_file(tmp_path):
    (tmp_path / "data").mkdir()
    pid_file = tmp_path / "data" / "bot.pid"
    pid_file.write_text("999999999", encoding="utf-8")
    controller = BotController(tmp_path)

    status = controller.status()

    assert status.running is False
    assert not pid_file.exists()

