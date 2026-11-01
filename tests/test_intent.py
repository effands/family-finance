from src.intent import account_request_summary, classify_finance_intent


def test_account_request_is_not_classified_as_expense():
    text = "aku mau input bank baru BCA atas nama EFENDI Saldo 17.516.328"
    assert classify_finance_intent(text) == "account_add"
    assert account_request_summary(text) == "BCA"


def test_regular_transaction_stays_transaction():
    assert classify_finance_intent("belanja sayur 45rb") == "transaction"


def test_transfer_and_atm_have_their_own_intent():
    assert classify_finance_intent("tarik saldo dari ATM Mandiri") == "cash_withdrawal"
    assert classify_finance_intent("transfer dari BCA ke GoPay") == "transfer"
