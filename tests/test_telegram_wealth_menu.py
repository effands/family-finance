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


def test_add_account_flow_collects_fields_and_requires_confirmation():
    menu = WealthTelegramMenu()
    menu.handle_callback("chat-1", "user-1", "wealth:account:add")
    values = ["Mandiri Operasional", "bank", "Bank Mandiri", "Keluarga", "1234", "100000000"]
    reply = None
    for value in values:
        reply = menu.handle_text("chat-1", "user-1", value)
    assert reply.action == "confirm"
    assert reply.payload["name"] == "Mandiri Operasional"
    assert "✅ Konfirmasi" in [button["text"] for row in reply.keyboard["inline_keyboard"] for button in row]


def test_confirm_callback_returns_account_create_action():
    menu = WealthTelegramMenu()
    menu.handle_callback("chat-1", "user-1", "wealth:account:add")
    for value in ["GoPay", "ewallet", "GoPay", "Keluarga", "0812", "500000"]:
        menu.handle_text("chat-1", "user-1", value)
    reply = menu.handle_callback("chat-1", "user-1", "wealth:confirm")
    assert reply.action == "account_create"
    assert reply.payload["account_type"] == "ewallet"


def test_account_list_is_a_distinct_data_action():
    reply = WealthTelegramMenu().handle_callback("chat-1", "user-1", "wealth:account:list")
    assert reply.action == "account_list"


def test_transfer_flow_requires_confirmation_with_four_fields():
    menu = WealthTelegramMenu()
    menu.handle_callback("chat-1", "user-1", "wealth:transfer")
    menu.handle_callback("chat-1", "user-1", "wealth:transfer:start")
    reply = None
    for value in ["1", "2", "3000000", "Pindah kebutuhan bulanan"]:
        reply = menu.handle_text("chat-1", "user-1", value)
    assert reply.action == "confirm"
    assert reply.payload["source_account_id"] == "1"


def test_atm_withdrawal_flow_uses_cash_destination():
    menu = WealthTelegramMenu()
    menu.handle_callback("chat-1", "user-1", "wealth:cash:withdraw")
    for value in ["1", "2", "3000000", "Tarik ATM"]:
        reply = menu.handle_text("chat-1", "user-1", value)
    assert reply.action == "confirm"
    assert reply.payload["operation_type"] == "cash_withdrawal"


def test_reconcile_and_default_flows_require_confirmation():
    menu = WealthTelegramMenu()
    menu.handle_callback("chat-1", "user-1", "wealth:account:reconcile")
    for value in ["1", "97000000", "Saldo m-banking"]:
        reply = menu.handle_text("chat-1", "user-1", value)
    assert reply.action == "confirm"
    assert reply.payload["actual_balance"] == "97000000"
    menu.handle_callback("chat-1", "user-1", "wealth:settings:default")
    for value in ["expense", "1"]:
        reply = menu.handle_text("chat-1", "user-1", value)
    assert reply.action == "confirm"
    assert reply.payload["operation_kind"] == "expense"


def test_archive_flow_returns_archive_action():
    menu = WealthTelegramMenu()
    menu.handle_callback("chat-1", "user-1", "wealth:account:archive")
    reply = menu.handle_text("chat-1", "user-1", "3")
    assert reply.action == "confirm"
    assert reply.payload["account_id"] == "3"


def test_investment_flow_creates_investment_account_with_confirmation():
    menu = WealthTelegramMenu()
    menu.handle_callback("chat-1", "user-1", "wealth:investment:add")
    for value in ["SBN ST014", "Bank Mandiri", "Keluarga", "ST014", "10000000"]:
        reply = menu.handle_text("chat-1", "user-1", value)
    assert reply.action == "confirm"
    assert reply.payload["account_type"] == "investment"


def test_guided_account_input_asks_for_next_field_instead_of_placeholder_message():
    menu = WealthTelegramMenu()
    menu.handle_callback("chat-1", "user-1", "wealth:account:add")
    reply = menu.handle_text("chat-1", "user-1", "Mandiri Operasional")
    assert "nama bank/provider" in reply.text.casefold()
    assert "implementasi alur lengkap" not in reply.text.casefold()


def test_guided_transfer_input_asks_for_next_field():
    menu = WealthTelegramMenu()
    menu.handle_callback("chat-1", "user-1", "wealth:transfer:start")
    reply = menu.handle_text("chat-1", "user-1", "1")
    assert "nominal transfer" in reply.text.casefold()
    assert "implementasi alur lengkap" not in reply.text.casefold()


def test_account_request_skips_fields_already_read_from_sentence():
    menu = WealthTelegramMenu()
    reply = menu.begin_account_request("chat-1", "user-1", {
        "name": "BCA", "account_type": "bank", "provider": "BCA",
        "holder_name": "EFENDI", "opening_balance": "17516328",
    })
    assert "nomor rekening" in reply.text.casefold()
