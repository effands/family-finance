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
    labels = {"wealth": "Total kekayaan", "liquid": "Aset likuid", "investments": "Investasi", "cash": "Cash di tangan", "income": "Pemasukan", "expense": "Pengeluaran", "net": "Arus kas bersih", "count": "Jumlah transaksi"}
    totals = "".join(f"<div class='report-total'><span>{html.escape(labels.get(key, key.title()))}</span><strong>{_idr(value) if key != 'count' and isinstance(value, int) else html.escape(str(value))}</strong></div>" for key, value in report.totals.items())
    empty_label = "Belum ada akun keuangan yang tercatat." if report.title == "Posisi Kekayaan" else "Belum ada transaksi pada periode ini."
    controls = "" if print_mode else "<button onclick='window.print()'>Print</button>"
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(report.title)}</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 "Plus Jakarta Sans",Inter,Arial,sans-serif}}.report-shell{{max-width:1180px;margin:0 auto;padding:38px 42px 42px;background:#fff;min-height:100vh}}.report-actions{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:34px;padding-bottom:22px;border-bottom:3px solid var(--ink)}}.report-kicker{{font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}}h1{{margin:8px 0 4px;font-size:clamp(30px,4vw,48px);letter-spacing:-.055em;line-height:1.05}}.muted{{color:var(--muted);font-size:14px}}button{{border:0;border-radius:7px;background:var(--accent);color:#fff;padding:10px 16px;font-weight:800;cursor:pointer}}button:hover{{background:#0d4cc2}}.totals{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0 0 34px}}.report-total{{padding:17px 18px;border:1px solid var(--line);border-radius:10px;background:#fff}}.report-total span{{display:block;margin-bottom:8px;color:var(--muted);font-size:11px;font-weight:800;letter-spacing:.04em;text-transform:uppercase}}.report-total strong{{font-size:22px;letter-spacing:-.04em}}.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:10px}}table{{width:100%;min-width:620px;border-collapse:collapse}}th,td{{padding:13px 15px;border-bottom:1px solid #e7edf4;text-align:left;white-space:nowrap}}th{{background:#f6f8fb;color:var(--muted);font-size:10px;letter-spacing:.06em;text-transform:uppercase}}td{{font-variant-numeric:tabular-nums}}tr:last-child td{{border-bottom:0}}.empty-row td{{padding:34px 20px;text-align:center;color:var(--muted);font-weight:600}}.report-footer{{margin-top:42px;padding-top:14px;border-top:1px solid var(--line);display:flex;justify-content:space-between;color:var(--muted);font-size:11px}}@media(max-width:700px){{.report-shell{{padding:24px 18px 44px}}.report-actions{{margin-bottom:28px}}.totals{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media print{{body{{background:#fff}}.report-shell{{max-width:none;padding:0;min-height:0}}.report-actions button{{display:none}}.report-actions{{margin-bottom:24px}}.report-total, .table-wrap{{border-color:#cbd5e1;box-shadow:none}}th{{background:#eef2f6!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}}@page{{size:A4 portrait;margin:12mm}}}}
    </style></head><body><main class='report-shell'><div class='report-actions'><div><div class='report-kicker'>Finance Family · Laporan Keuangan</div><h1>{html.escape(report.title)}</h1><div class='muted'>Periode {html.escape(report.period_label)}</div></div>{controls}</div><div class='totals'>{totals}</div><div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{body or f'<tr class="empty-row"><td colspan="8">{empty_label}</td></tr>'}</tbody></table></div><footer class='report-footer'><span>Dokumen dibuat dari pembukuan Finance Family</span><span>Dicetak untuk arsip keluarga</span></footer></main></body></html>"""
