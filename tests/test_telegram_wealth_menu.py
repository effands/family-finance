from src.telegram_wealth import WealthTelegramMenu


def test_main_menu_uses_button_first_navigation():
    reply = WealthTelegramMenu().main_menu("chat-1", "user-1")
    labels = [button["text"] for row in reply.keyboard["inline_keyboard"] for button in row]
    assert "🏦 Kelola Akun & Saldo" in labels
    assert "📈 Investasi" in labels
    assert "🔄 Transfer Dana" in labels
    assert all(not button["text"].startswith("/") for row in reply.keyboard["inline_keyboard"] for button in row)


def test_account_menu_has_sensitive_operations_and_cancel():
    menu = WealthTelegramMenu()
    reply = menu.handle_callback("chat-1", "user-1", "wealth:accounts")
    labels = [button["text"] for row in reply.keyboard["inline_keyboard"] for button in row]
    assert "➕ Tambah Akun" in labels
    assert "🏧 Tarik Tunai ATM" in labels
    assert "🔁 Rekonsiliasi Saldo" in labels
    assert "❌ Batalkan" not in labels
    flow = menu.handle_callback("chat-1", "user-1", "wealth:account:add")
    assert flow.action == "input"
    assert "❌ Batalkan" in [button["text"] for row in flow.keyboard["inline_keyboard"] for button in row]


def test_cancel_clears_user_session_without_affecting_another_user():
    menu = WealthTelegramMenu()
    menu.handle_callback("chat-1", "user-1", "wealth:account:add")
    menu.handle_callback("chat-1", "user-2", "wealth:investment:add")
    menu.handle_callback("chat-1", "user-1", "wealth:cancel")
    assert menu.handle_text("chat-1", "user-1", "Mandiri") is None
    assert menu.handle_text("chat-1", "user-2", "SBN ST014").action == "input"


def test_callback_is_safe_to_repeat():
    menu = WealthTelegramMenu()
    first = menu.handle_callback("chat-1", "user-1", "wealth:accounts")
    second = menu.handle_callback("chat-1", "user-1", "wealth:accounts")
    assert first.text == second.text
    assert first.keyboard == second.keyboard
