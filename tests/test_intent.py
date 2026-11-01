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


def test_crypto_is_saved_as_investment_portfolio_type():
    assert extract_account_fields("tambah crypto Bitcoin saldo 2 juta")["account_type"] == "investment"


def test_tambahkan_bank_sentence_is_account_request():
    text = "tambahkan bank yaitu BANK RAYA norek 001001627681318 saldo 1427980 atas nama efendi"
    assert classify_finance_intent(text) == "account_add"
    fields = extract_account_fields(text)
    assert fields["provider"] == "BANK RAYA"
    assert fields["account_identifier"] == "001001627681318"
    assert fields["holder_name"] == "efendi"


def test_explicit_dana_provider_is_extracted_from_add_sentence():
    fields = extract_account_fields("tambahkan DANA saldo 128.000 atas nama EFENDI")
    assert fields["account_type"] == "ewallet"
    assert fields["provider"] == "DANA"
    assert fields["name"] == "DANA"
    assert fields["holder_name"] == "EFENDI"
    assert fields["opening_balance"] == "128000"


def test_bank_number_is_not_absorbed_into_provider_name():
    fields = extract_account_fields("tambah akun bank mandiri 1440016945088 saldo 211645141 atas nama efendi")
    assert fields["provider"] == "bank mandiri"
    assert fields["name"] == "bank mandiri"
    assert fields["account_identifier"] == "1440016945088"


def test_danamon_is_not_mistaken_for_dana_wallet():
    fields = extract_account_fields("tambah akun bank danamon 003636204954 saldo 404118 nama efendi")
    assert fields["account_type"] == "bank"
    assert fields["provider"] == "bank danamon"
