from src.intent import account_request_summary, classify_finance_intent, extract_account_fields


def test_account_request_is_not_classified_as_expense():
    text = "aku mau input bank baru BCA atas nama EFENDI Saldo 17.516.328"
    assert classify_finance_intent(text) == "account_add"
    assert account_request_summary(text) == "BCA"


def test_regular_transaction_stays_transaction():
    assert classify_finance_intent("belanja sayur 45rb") == "transaction"


def test_transfer_and_atm_have_their_own_intent():
    assert classify_finance_intent("tarik saldo dari ATM Mandiri") == "cash_withdrawal"
    assert classify_finance_intent("transfer dari BCA ke GoPay") == "transfer"


def test_account_intent_can_request_missing_balance_and_detect_provider_type():
    assert classify_finance_intent("tambah bank baru BCA atas nama EFENDI") == "account_add"
    assert extract_account_fields("tambah e-wallet GoPay atas nama EFENDI saldo 500rb")["account_type"] == "ewallet"
    assert extract_account_fields("buat rekening BCA saldo 1,5 juta atas nama EFENDI")["opening_balance"] == "1500000"


def test_account_fields_are_extracted_from_one_sentence():
    fields = extract_account_fields("aku mau input bank baru BCA atas nama EFENDI saldo 17.516.328 norek 1234")
    assert fields["provider"] == "BCA"
    assert fields["holder_name"] == "EFENDI"
    assert fields["opening_balance"] == "17516328"
    assert fields["account_identifier"] == "1234"


def test_missing_account_identifier_is_not_invented_from_sentence_text():
    fields = extract_account_fields("aku mau input bank baru BCA atas nama EFENDI saldo 17.516.328")
    assert "account_identifier" not in fields
