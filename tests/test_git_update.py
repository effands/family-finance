from datetime import date
from types import SimpleNamespace

import passenger_wsgi


def test_git_update_uses_current_branch_and_ff_only(monkeypatch, tmp_path):
    calls = []

    def fake_check_output(args, **kwargs):
        calls.append(args)
        if args[1:4] == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return "production\n"
        if args[1:4] == ["rev-parse", "--abbrev-ref", "--symbolic-full-name"]:
            return "origin/codex/wealth-ledger\n"
        return "abc123 - update\n"

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(passenger_wsgi.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(passenger_wsgi.subprocess, "run", fake_run)
    monkeypatch.setattr(passenger_wsgi, "load_settings", lambda: SimpleNamespace(database_path=str(tmp_path / "money.db")))
    monkeypatch.setattr(passenger_wsgi.os.path, "exists", lambda path: False)

    branch, commit, backup, output = passenger_wsgi._run_git_update(str(tmp_path))

    assert branch == "production ← origin/codex/wealth-ledger"
    assert commit == "abc123 - update"
    assert "origin" in calls[2] and "codex/wealth-ledger" in calls[2]
    assert "--ff-only" in calls[3]
    assert "codex/wealth-ledger" in calls[3]
    assert backup.endswith(f".pre-git-update-{date.today().isoformat()}")
