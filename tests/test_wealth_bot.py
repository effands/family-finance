import inspect

from src.main import accounts_cmd, backup_cmd, transfer_cmd, wealth_cmd


def test_wealth_commands_are_async_handlers():
    assert inspect.iscoroutinefunction(accounts_cmd)
    assert inspect.iscoroutinefunction(wealth_cmd)
    assert inspect.iscoroutinefunction(transfer_cmd)
    assert inspect.iscoroutinefunction(backup_cmd)
