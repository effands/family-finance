"""Print-first professional reports backed by the same ledger totals as the UI."""

import html
from dataclasses import dataclass
from datetime import date

from .models import TransactionFilters
from .wealth import WealthLedger


@dataclass(frozen=True)
class ReportData:
    title: str
    period_label: str
    rows: list[dict]
    totals: dict[str, int]


def _period_label(start, end):
    if start and end:
        return f"{start.isoformat()} s/d {end.isoformat()}"
    return "Semua periode"


def build_professional_report(db, chat_id: str, report_type: str, start: date | None, end: date | None) -> ReportData:
    report_type = report_type if report_type in {"journal", "cashflow", "wealth", "reconciliation"} else "cashflow"
    period = _period_label(start, end)
    if report_type == "wealth":
        balances = WealthLedger(db).get_account_balances(chat_id, include_archived=True)
        rows = [{"akun": x.account_name, "jenis": x.account_type, "saldo": x.balance} for x in balances]
        summary = WealthLedger(db).get_wealth_summary(chat_id)
        return ReportData("Posisi Kekayaan", period, rows, {"wealth": summary.total_wealth, "liquid": summary.liquid_assets, "investments": summary.investments, "cash": summary.cash})
    transactions = db.list_transactions(TransactionFilters(chat_id, start=start, end=end))
    rows = [{"tanggal": x.transaction_date.isoformat(), "jenis": x.type, "uraian": x.description, "kategori": x.category, "nominal": x.amount, "pencatat": x.username or x.user_id or ""} for x in transactions]
    income = sum(x.amount for x in transactions if x.type == "income")
    expense = sum(x.amount for x in transactions if x.type == "expense")
    title = "Jurnal Transaksi" if report_type == "journal" else "Rekap Arus Kas"
    return ReportData(title, period, rows, {"income": income, "expense": expense, "net": income - expense, "count": len(rows)})


def _idr(value):
    return "Rp " + f"{int(value):,}".replace(",", ".")


def render_report_html(report: ReportData, print_mode: bool = False) -> str:
    headers = list(report.rows[0].keys()) if report.rows else []
    head = "".join(f"<th>{html.escape(str(x).replace('_', ' ').title())}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(_idr(v) if key in {'saldo', 'nominal'} else str(v))}</td>" for key, v in row.items()) + "</tr>" for row in report.rows)
    totals = "".join(f"<div class='report-total'><span>{html.escape(key.title())}</span><strong>{_idr(value) if isinstance(value, int) else html.escape(str(value))}</strong></div>" for key, value in report.totals.items())
    controls = "" if print_mode else "<button onclick='window.print()'>Print</button>"
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(report.title)}</title><style>
    body{{font-family:Arial,sans-serif;color:#172033;margin:32px}}h1{{margin-bottom:4px}}.muted{{color:#68738a}}button{{padding:9px 14px;border:0;border-radius:8px;background:#2563eb;color:white}}.totals{{display:flex;gap:14px;flex-wrap:wrap;margin:24px 0}}.report-total{{border:1px solid #dbe3ef;border-radius:10px;padding:12px 16px;min-width:140px}}.report-total span{{display:block;color:#68738a;font-size:12px;text-transform:uppercase}}table{{width:100%;border-collapse:collapse;margin-top:20px}}th,td{{border-bottom:1px solid #e5eaf1;padding:9px;text-align:left}}th{{background:#f4f7fb}}@media print{{button{{display:none}}body{{margin:10mm}}th{{background:#eee!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
    </style></head><body><div>{controls}</div><h1>{html.escape(report.title)}</h1><div class='muted'>Finance Family · Periode {html.escape(report.period_label)}</div><div class='totals'>{totals}</div><table><thead><tr>{head}</tr></thead><tbody>{body or '<tr><td colspan="8">Tidak ada data.</td></tr>'}</tbody></table></body></html>"""
