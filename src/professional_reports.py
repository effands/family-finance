"""Print-first professional reports backed by the same ledger totals as the UI."""

import html
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReportData:
    title: str
    period_label: str
    rows: list[dict]
    totals: dict[str, int]
    report_type: str = ""


def _period_label(start, end):
    if start and end:
        return f"{start.isoformat()} s/d {end.isoformat()}"
    return "Semua periode"


def build_professional_report(db, chat_id: str, report_type: str, start: date | None, end: date | None) -> ReportData:
    from .models import TransactionFilters
    from .wealth import WealthLedger

    report_type = report_type if report_type in {"journal", "cashflow", "wealth", "reconciliation"} else "cashflow"
    period = _period_label(start, end)
    if report_type == "wealth":
        balances = WealthLedger(db).get_account_balances(chat_id, include_archived=True)
        rows = [{"akun": x.account_name, "jenis": x.account_type, "saldo": x.balance} for x in balances]
        summary = WealthLedger(db).get_wealth_summary(chat_id)
        return ReportData(
            "Posisi Kekayaan",
            period,
            rows,
            {"wealth": summary.total_wealth, "liquid": summary.liquid_assets, "investments": summary.investments, "cash": summary.cash},
            report_type="wealth",
        )
    transactions = db.list_transactions(TransactionFilters(chat_id, start=start, end=end))
    rows = [{"tanggal": x.transaction_date.isoformat(), "jenis": x.type, "uraian": x.description, "kategori": x.category, "nominal": x.amount, "pencatat": x.username or x.user_id or ""} for x in transactions]
    income = sum(x.amount for x in transactions if x.type == "income")
    expense = sum(x.amount for x in transactions if x.type == "expense")
    title = "Jurnal Transaksi" if report_type == "journal" else "Rekap Arus Kas"
    return ReportData(
        title,
        period,
        rows,
        {"income": income, "expense": expense, "net": income - expense, "count": len(rows)},
        report_type=report_type,
    )


def _idr(value):
    return "Rp " + f"{int(value):,}".replace(",", ".")


def _format_date_indonesian(d: date) -> str:
    months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    return f"{d.day} {months[d.month - 1]} {d.year}"


def render_report_html(report: ReportData, print_mode: bool = False) -> str:
    today_str = _format_date_indonesian(date.today())
    report_kind = report.report_type or ("wealth" if report.title == "Posisi Kekayaan" else "journal" if report.title == "Jurnal Transaksi" else "cashflow")

    default_headers = {
        "Posisi Kekayaan": ["akun", "jenis", "saldo"],
        "Jurnal Transaksi": ["tanggal", "jenis", "uraian", "kategori", "nominal", "pencatat"],
        "Rekap Arus Kas": ["tanggal", "jenis", "uraian", "kategori", "nominal", "pencatat"],
    }
    headers = list(report.rows[0].keys()) if report.rows else default_headers.get(report.title, ["keterangan", "nominal"])

    # Header cells with proper alignment
    head_cells = []
    for h in headers:
        align_cls = "text-right" if h in {"saldo", "nominal"} else "text-left"
        label = "Kategori / Tipe" if h == "jenis" else ("Saldo Akhir" if h == "saldo" else str(h).replace("_", " ").title())
        head_cells.append(f"<th class='{align_cls}'>{html.escape(label)}</th>")
    head_html = "".join(head_cells)

    # Body rows with badges and right-aligned currencies
    def _render_cell_val(key: str, val):
        if key in {"saldo", "nominal"}:
            return f"<td class='text-right font-mono font-bold'>{html.escape(_idr(val))}</td>"
        if key == "jenis":
            val_str = str(val).lower()
            badge_map = {
                "bank": ("badge-bank", "Bank"),
                "ewallet": ("badge-ewallet", "E-Wallet"),
                "investment": ("badge-investment", "Investasi"),
                "cash": ("badge-cash", "Kas Fisik"),
                "income": ("badge-income", "Pemasukan"),
                "expense": ("badge-expense", "Pengeluaran"),
            }
            cls, text = badge_map.get(val_str, ("badge-neutral", str(val).title()))
            return f"<td><span class='badge {cls}'>{html.escape(text)}</span></td>"
        if key == "akun":
            return f"<td class='font-semibold text-ink'>{html.escape(str(val))}</td>"
        return f"<td>{html.escape(str(val))}</td>"

    body_rows = []
    for idx, row in enumerate(report.rows, 1):
        cells = "".join(_render_cell_val(k, v) for k, v in row.items())
        body_rows.append(f"<tr>{cells}</tr>")
    body_html = "".join(body_rows)

    # Empty table state
    empty_label = (
        "Belum ada akun keuangan yang tercatat. Tambahkan rekening bank, e-wallet, cash, atau investasi dari Wealth Center."
        if report.title == "Posisi Kekayaan"
        else "Belum ada transaksi pada periode ini. Pilih periode lain atau catat transaksi baru."
    )
    empty_state_html = f"""<tr class="empty-row"><td colspan="{len(headers)}">
        <div class="empty-state-box">
            <div class="empty-icon-wrap">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4Z"/></svg>
            </div>
            <div class="empty-title">Belum Ada Data Terpilih</div>
            <p class="empty-desc">{html.escape(empty_label)}</p>
            <div class="empty-action no-print">
                <a href="/keuangan/wealth" class="btn-empty-action">+ Buka Wealth Center</a>
            </div>
        </div>
    </td></tr>"""

    # Table footer total
    tfoot_html = ""
    if report.rows and report.title == "Posisi Kekayaan" and "wealth" in report.totals:
        tfoot_html = f"""<tfoot><tr class="table-total-row">
            <td colspan="{len(headers) - 1}" class="text-right text-muted font-bold text-uppercase">Total Saldo Konsolidasi</td>
            <td class="text-right font-mono font-bold text-accent">{html.escape(_idr(report.totals['wealth']))}</td>
        </tr></tfoot>"""

    # Metric KPI cards
    meta_cards = {
        "wealth": ("Total Kekayaan", "blue", "Valuasi konsolidasi seluruh akun", """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 2 7l10 5 10-5-10-5Z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/></svg>"""),
        "liquid": ("Aset Likuid", "emerald", "Rekening bank & saldo e-wallet", """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" x2="22" y1="10" y2="10"/></svg>"""),
        "investments": ("Investasi", "purple", "Portofolio instrumen investasi", """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>"""),
        "cash": ("Cash di Tangan", "amber", "Uang kas fisik & brankas", """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="12" x="2" y="6" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/></svg>"""),
        "income": ("Total Pemasukan", "emerald", "Total penerimaan kas periode ini", """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" x2="12" y1="5" y2="19"/><polyline points="19 12 12 19 5 12"/></svg>"""),
        "expense": ("Total Pengeluaran", "rose", "Total belanja & pengeluaran kas", """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" x2="12" y1="19" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>"""),
        "net": ("Arus Kas Bersih", "blue", "Surplus / defisit arus kas", """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/></svg>"""),
        "count": ("Jumlah Transaksi", "slate", "Total pencatatan transaksi", """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>"""),
    }

    cards_html = []
    for key, value in report.totals.items():
        title_lbl, tone, desc, icon_svg = meta_cards.get(key, (key.replace('_', ' ').title(), "slate", "", ""))
        val_str = _idr(value) if key != "count" and isinstance(value, int) else html.escape(str(value))
        cards_html.append(f"""
        <div class="report-card card-{tone}">
            <div class="card-bar"></div>
            <div class="card-top">
                <span class="card-label">{html.escape(title_lbl)}</span>
                <span class="card-icon">{icon_svg}</span>
            </div>
            <div class="card-val">{val_str}</div>
            <div class="card-desc">{html.escape(desc)}</div>
        </div>
        """)
    totals_html = "".join(cards_html)

    note = (
        "Laporan ini menampilkan saldo tercatat seluruh akun, termasuk aset likuid, investasi, dan cash di tangan."
        if report.title == "Posisi Kekayaan"
        else "Laporan ini disusun dari transaksi yang tercatat pada periode yang dipilih."
    )

    # Screen navigation toolbar
    screen_nav = ""
    if not print_mode:
        w_active = "active" if report_kind == "wealth" else ""
        c_active = "active" if report_kind == "cashflow" else ""
        j_active = "active" if report_kind == "journal" else ""
        screen_nav = f"""
        <div class="screen-toolbar no-print">
            <div class="toolbar-inner">
                <div class="toolbar-left">
                    <a href="/keuangan/wealth" class="btn-tool btn-back">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
                        <span>Kembali ke Wealth</span>
                    </a>
                    <span class="toolbar-sep"></span>
                    <nav class="report-tabs">
                        <a href="/keuangan/reports?type=wealth" class="tab-item {w_active}">Posisi Kekayaan</a>
                        <a href="/keuangan/reports?type=cashflow" class="tab-item {c_active}">Rekap Arus Kas</a>
                        <a href="/keuangan/reports?type=journal" class="tab-item {j_active}">Jurnal Transaksi</a>
                    </nav>
                </div>
                <div class="toolbar-right">
                    <button type="button" class="btn-tool btn-print" onclick="window.print()">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect width="12" height="8" x="6" y="14"/></svg>
                        <span>Cetak Dokumen</span>
                    </button>
                </div>
            </div>
        </div>
        """

    return f"""<!doctype html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{html.escape(report.title)} - Finance Family</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --font-sans: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
            --font-mono: 'JetBrains Mono', Consolas, monospace;
            --bg-page: #f1f5f9;
            --bg-surface: #ffffff;
            --bg-soft: #f8fafc;
            --ink: #0f172a;
            --ink-secondary: #334155;
            --muted: #64748b;
            --faint: #94a3b8;
            --line: #e2e8f0;
            --line-strong: #cbd5e1;
            --accent: #2563eb;
            --accent-soft: #eff6ff;
            --accent-border: #bfdbfe;
            --emerald: #059669;
            --emerald-soft: #ecfdf5;
            --emerald-border: #a7f3d0;
            --purple: #7c3aed;
            --purple-soft: #f5f3ff;
            --purple-border: #ddd6fe;
            --amber: #d97706;
            --amber-soft: #fffbeb;
            --amber-border: #fde68a;
            --rose: #e11d48;
            --rose-soft: #fff1f2;
            --rose-border: #fecdd3;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg-page);
            color: var(--ink);
            font-family: var(--font-sans);
            font-size: 14px;
            line-height: 1.55;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }}

        /* Screen Toolbar */
        .screen-toolbar {{
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(8px);
            border-bottom: 1px solid var(--line);
            position: sticky;
            top: 0;
            z-index: 50;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
        }}
        .toolbar-inner {{
            max-width: 1040px;
            margin: 0 auto;
            padding: 10px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }}
        .toolbar-left {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}
        .toolbar-sep {{
            width: 1px;
            height: 22px;
            background: var(--line);
        }}
        .btn-tool {{
            display: inline-flex;
            align-items: center;
            gap: 7px;
            padding: 7px 14px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.15s ease;
            border: 1px solid transparent;
            user-select: none;
        }}
        .btn-back {{
            background: var(--bg-soft);
            color: var(--ink-secondary);
            border-color: var(--line);
        }}
        .btn-back:hover {{
            background: #ffffff;
            color: var(--ink);
            border-color: var(--line-strong);
        }}
        .btn-print {{
            background: var(--accent);
            color: #ffffff;
            box-shadow: 0 2px 4px rgba(37, 99, 235, 0.25);
        }}
        .btn-print:hover {{
            background: #1d4ed8;
            box-shadow: 0 4px 8px rgba(37, 99, 235, 0.35);
            transform: translateY(-1px);
        }}
        .report-tabs {{
            display: inline-flex;
            background: #e2e8f0;
            padding: 3px;
            border-radius: 8px;
            gap: 3px;
        }}
        .tab-item {{
            padding: 5px 12px;
            font-size: 12.5px;
            font-weight: 600;
            color: var(--muted);
            border-radius: 6px;
            text-decoration: none;
            transition: all 0.15s ease;
        }}
        .tab-item:hover {{
            color: var(--ink);
        }}
        .tab-item.active {{
            background: #ffffff;
            color: var(--accent);
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
        }}

        /* Document Paper Shell */
        .report-shell {{
            max-width: 1040px;
            margin: 28px auto 60px;
            padding: 44px 52px;
            background: #ffffff;
            border-radius: 16px;
            border: 1px solid var(--line);
            box-shadow: 0 10px 30px -10px rgba(15, 23, 42, 0.08), 0 0 1px 1px rgba(15, 23, 42, 0.04);
        }}

        /* Document Header */
        .doc-header {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 24px;
            padding-bottom: 24px;
            border-bottom: 2px solid var(--line);
            margin-bottom: 24px;
        }}
        .doc-brand-lockup {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
        }}
        .doc-brand-mark {{
            width: 38px;
            height: 38px;
            border-radius: 10px;
            background: linear-gradient(135deg, #1e40af 0%, #2563eb 55%, #38bdf8 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            box-shadow: 0 4px 10px rgba(37, 99, 235, 0.25);
        }}
        .doc-brand-title {{
            font-size: 13px;
            font-weight: 800;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: var(--accent);
            line-height: 1.2;
        }}
        .doc-brand-desc {{
            font-size: 11.5px;
            color: var(--muted);
            font-weight: 500;
        }}
        .doc-title {{
            font-size: 32px;
            font-weight: 800;
            letter-spacing: -0.035em;
            color: var(--ink);
            line-height: 1.15;
            margin-bottom: 8px;
        }}
        .doc-meta-row {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 13px;
            color: var(--muted);
            flex-wrap: wrap;
        }}
        .doc-meta-pill {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: var(--bg-soft);
            padding: 4px 10px;
            border-radius: 6px;
            border: 1px solid var(--line);
        }}
        .doc-meta-pill strong {{
            color: var(--ink-secondary);
        }}

        .doc-badge-card {{
            text-align: right;
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 6px;
        }}
        .doc-status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: var(--emerald-soft);
            color: var(--emerald);
            border: 1px solid var(--emerald-border);
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }}
        .status-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--emerald);
        }}
        .doc-badge-meta {{
            font-size: 11.5px;
            color: var(--muted);
        }}

        /* Document Notice Banner */
        .doc-banner {{
            display: flex;
            align-items: flex-start;
            gap: 12px;
            background: linear-gradient(135deg, #f0f7ff 0%, #f8fafc 100%);
            border: 1px solid var(--accent-border);
            border-left: 4px solid var(--accent);
            padding: 13px 18px;
            border-radius: 8px;
            margin-bottom: 24px;
            color: var(--ink-secondary);
            font-size: 13px;
            line-height: 1.5;
        }}
        .doc-banner-icon {{
            color: var(--accent);
            flex-shrink: 0;
            margin-top: 1px;
        }}

        /* Metric KPI Cards Grid */
        .totals-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 14px;
            margin-bottom: 28px;
        }}
        .report-card {{
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 18px 18px 16px;
            position: relative;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
        }}
        .card-bar {{
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
        }}
        .card-blue .card-bar {{ background: linear-gradient(90deg, #1e40af, #3b82f6); }}
        .card-emerald .card-bar {{ background: linear-gradient(90deg, #059669, #34d399); }}
        .card-purple .card-bar {{ background: linear-gradient(90deg, #7c3aed, #a78bfa); }}
        .card-amber .card-bar {{ background: linear-gradient(90deg, #d97706, #fbbf24); }}
        .card-rose .card-bar {{ background: linear-gradient(90deg, #e11d48, #fb7185); }}
        .card-slate .card-bar {{ background: linear-gradient(90deg, #475569, #94a3b8); }}

        .card-top {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }}
        .card-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: var(--muted);
        }}
        .card-icon {{
            width: 30px;
            height: 30px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}
        .card-blue .card-icon {{ background: var(--accent-soft); color: var(--accent); }}
        .card-emerald .card-icon {{ background: var(--emerald-soft); color: var(--emerald); }}
        .card-purple .card-icon {{ background: var(--purple-soft); color: var(--purple); }}
        .card-amber .card-icon {{ background: var(--amber-soft); color: var(--amber); }}
        .card-rose .card-icon {{ background: var(--rose-soft); color: var(--rose); }}
        .card-slate .card-icon {{ background: var(--bg-soft); color: var(--muted); }}

        .card-val {{
            font-size: 23px;
            font-weight: 800;
            letter-spacing: -0.035em;
            color: var(--ink);
            line-height: 1.2;
            margin-bottom: 4px;
            font-variant-numeric: tabular-nums;
        }}
        .card-blue .card-val {{ color: #1e3a8a; }}
        .card-emerald .card-val {{ color: #047857; }}
        .card-purple .card-val {{ color: #6d28d9; }}
        .card-amber .card-val {{ color: #b45309; }}
        .card-rose .card-val {{ color: #be123c; }}

        .card-desc {{
            font-size: 11px;
            color: var(--faint);
            line-height: 1.35;
        }}

        /* Data Section & Table */
        .section-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }}
        .section-title {{
            font-size: 14px;
            font-weight: 700;
            color: var(--ink);
            letter-spacing: -0.01em;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .section-count {{
            background: var(--bg-soft);
            color: var(--muted);
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 9999px;
            border: 1px solid var(--line);
        }}
        .section-note {{
            font-size: 12px;
            color: var(--muted);
        }}

        .table-wrap {{
            width: 100%;
            overflow-x: auto;
            border: 1px solid var(--line);
            border-radius: 12px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
            margin-bottom: 32px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13.5px;
        }}
        thead {{
            background: var(--bg-soft);
            border-bottom: 2px solid var(--line);
        }}
        th {{
            padding: 12px 16px;
            color: var(--muted);
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            white-space: nowrap;
        }}
        td {{
            padding: 13px 16px;
            border-bottom: 1px solid var(--line);
            color: var(--ink-secondary);
            vertical-align: middle;
        }}
        tbody tr:last-child td {{
            border-bottom: none;
        }}
        tbody tr:hover td {{
            background: #fafcff;
        }}
        tfoot tr td {{
            background: var(--bg-soft);
            border-top: 2px solid var(--line-strong);
            padding: 14px 16px;
            font-size: 13.5px;
        }}

        .text-left {{ text-align: left; }}
        .text-right {{ text-align: right; }}
        .font-mono {{ font-family: var(--font-mono); }}
        .font-bold {{ font-weight: 700; }}
        .font-semibold {{ font-weight: 600; }}
        .text-ink {{ color: var(--ink); }}
        .text-muted {{ color: var(--muted); }}
        .text-accent {{ color: var(--accent); }}
        .text-uppercase {{ text-transform: uppercase; letter-spacing: 0.05em; font-size: 11.5px; }}

        /* Badges */
        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 3px 9px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.02em;
            line-height: 1.25;
            white-space: nowrap;
        }}
        .badge-bank {{ background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }}
        .badge-ewallet {{ background: #ecfeff; color: #0e7490; border: 1px solid #a5f3fc; }}
        .badge-investment {{ background: #f5f3ff; color: #6d28d9; border: 1px solid #ddd6fe; }}
        .badge-cash {{ background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }}
        .badge-income {{ background: var(--emerald-soft); color: var(--emerald); border: 1px solid var(--emerald-border); }}
        .badge-expense {{ background: var(--rose-soft); color: var(--rose); border: 1px solid var(--rose-border); }}
        .badge-neutral {{ background: var(--bg-soft); color: var(--muted); border: 1px solid var(--line); }}

        /* Empty State */
        .empty-row td {{
            padding: 44px 20px !important;
            text-align: center;
        }}
        .empty-state-box {{
            max-width: 440px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
        }}
        .empty-icon-wrap {{
            width: 52px;
            height: 52px;
            border-radius: 12px;
            background: var(--bg-soft);
            color: var(--muted);
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 12px;
            border: 1px solid var(--line);
        }}
        .empty-title {{
            font-size: 15px;
            font-weight: 700;
            color: var(--ink);
            margin-bottom: 6px;
        }}
        .empty-desc {{
            font-size: 13px;
            color: var(--muted);
            line-height: 1.5;
            margin-bottom: 16px;
        }}
        .btn-empty-action {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: var(--accent);
            color: #ffffff;
            font-size: 12.5px;
            font-weight: 600;
            padding: 8px 16px;
            border-radius: 8px;
            text-decoration: none;
            transition: all 0.15s ease;
        }}
        .btn-empty-action:hover {{
            background: #1d4ed8;
            transform: translateY(-1px);
        }}

        /* Formal Verification & Sign-off */
        .doc-sign-grid {{
            display: grid;
            grid-template-columns: 1.5fr 1fr 1fr;
            gap: 24px;
            padding-top: 24px;
            border-top: 1px solid var(--line);
            margin-bottom: 24px;
        }}
        .sign-disclaimer {{
            font-size: 11.5px;
            color: var(--muted);
            line-height: 1.6;
        }}
        .sign-disclaimer strong {{
            color: var(--ink-secondary);
        }}
        .sign-box {{
            background: var(--bg-soft);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 12px 14px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 84px;
        }}
        .sign-role {{
            font-size: 10.5px;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: var(--muted);
        }}
        .sign-line {{
            border-bottom: 1px dashed var(--line-strong);
            margin: 28px 0 6px;
        }}
        .sign-name {{
            font-size: 11px;
            color: var(--ink-secondary);
            font-weight: 600;
            text-align: center;
        }}

        /* Document Footer */
        .report-footer {{
            padding-top: 14px;
            border-top: 1px solid var(--line);
            display: flex;
            align-items: center;
            justify-content: space-between;
            color: var(--faint);
            font-size: 11px;
        }}

        /* Responsive */
        @media (max-width: 840px) {{
            .report-shell {{
                padding: 24px 20px 40px;
                margin: 16px 12px;
                border-radius: 12px;
            }}
            .totals-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
            .doc-header {{
                flex-direction: column;
                align-items: flex-start;
            }}
            .doc-badge-card {{
                text-align: left;
                align-items: flex-start;
            }}
            .doc-sign-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        /* print styles */
        @media print {{
            body {{
                background: #ffffff !important;
                color: #0f172a !important;
                font-size: 11px !important;
                line-height: 1.35 !important;
            }}
            .no-print {{
                display: none !important;
            }}
            .report-shell {{
                max-width: 100% !important;
                margin: 0 !important;
                padding: 0 !important;
                border: none !important;
                box-shadow: none !important;
                border-radius: 0 !important;
            }}
            .doc-header {{
                padding-bottom: 12px !important;
                margin-bottom: 12px !important;
                border-bottom: 1.5px solid #cbd5e1 !important;
            }}
            .doc-brand-mark {{
                width: 28px !important;
                height: 28px !important;
            }}
            .doc-brand-title {{
                font-size: 11px !important;
            }}
            .doc-brand-desc {{
                font-size: 9.5px !important;
            }}
            .doc-title {{
                font-size: 20px !important;
                margin-bottom: 4px !important;
            }}
            .doc-meta-row {{
                font-size: 10.5px !important;
                gap: 8px !important;
            }}
            .doc-meta-pill {{
                padding: 2px 6px !important;
            }}
            .doc-status-badge {{
                font-size: 9.5px !important;
                padding: 2px 8px !important;
            }}
            .doc-badge-meta {{
                font-size: 9.5px !important;
            }}
            .doc-banner {{
                background: #f8fafc !important;
                border-color: #cbd5e1 !important;
                padding: 7px 12px !important;
                font-size: 10px !important;
                margin-bottom: 12px !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
            .totals-grid {{
                gap: 8px !important;
                margin-bottom: 14px !important;
            }}
            .report-card {{
                padding: 8px 10px !important;
                border-color: #cbd5e1 !important;
                box-shadow: none !important;
                border-radius: 8px !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
            .card-top {{
                margin-bottom: 4px !important;
            }}
            .card-label {{
                font-size: 9px !important;
            }}
            .card-icon {{
                width: 22px !important;
                height: 22px !important;
            }}
            .card-icon svg {{
                width: 14px !important;
                height: 14px !important;
            }}
            .card-val {{
                font-size: 15px !important;
                margin-bottom: 2px !important;
            }}
            .card-desc {{
                font-size: 9px !important;
            }}
            .card-bar {{
                height: 2px !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
            .section-header {{
                margin-bottom: 6px !important;
            }}
            .section-title {{
                font-size: 11px !important;
            }}
            .section-note {{
                font-size: 9.5px !important;
            }}
            .table-wrap {{
                border-color: #cbd5e1 !important;
                box-shadow: none !important;
                margin-bottom: 14px !important;
                border-radius: 6px !important;
            }}
            table {{
                font-size: 10px !important;
            }}
            thead {{
                background: #f1f5f9 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
            th {{
                padding: 6px 10px !important;
                font-size: 9px !important;
            }}
            td {{
                padding: 5px 10px !important;
                border-bottom-color: #e2e8f0 !important;
            }}
            tfoot tr td {{
                padding: 6px 10px !important;
                font-size: 10px !important;
            }}
            .badge {{
                font-size: 8.5px !important;
                padding: 1px 6px !important;
                border-color: #94a3b8 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
            .doc-sign-grid {{
                padding-top: 10px !important;
                gap: 12px !important;
                margin-bottom: 8px !important;
                page-break-inside: avoid;
            }}
            .sign-disclaimer {{
                font-size: 9px !important;
                line-height: 1.4 !important;
            }}
            .sign-box {{
                background: #ffffff !important;
                border-color: #cbd5e1 !important;
                padding: 6px 10px !important;
                min-height: 52px !important;
                border-radius: 6px !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
            .sign-role {{
                font-size: 8.5px !important;
            }}
            .sign-line {{
                margin: 16px 0 3px !important;
            }}
            .sign-name {{
                font-size: 9px !important;
            }}
            .report-footer {{
                padding-top: 6px !important;
                font-size: 8.5px !important;
            }}
            tr {{
                page-break-inside: avoid;
            }}
            @page {{
                size: A4 portrait;
                margin: 8mm 10mm 8mm 10mm;
            }}
        }}
    </style>
</head>
<body>
    {screen_nav}
    <main class="report-shell">
        <header class="doc-header">
            <div>
                <div class="doc-brand-lockup">
                    <div class="doc-brand-mark">
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5Z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/></svg>
                    </div>
                    <div>
                        <div class="doc-brand-title">Finance Family</div>
                        <div class="doc-brand-desc">Laporan Keuangan & Pembukuan Keluarga</div>
                    </div>
                </div>
                <h1 class="doc-title">{html.escape(report.title)}</h1>
                <div class="doc-meta-row">
                    <span class="doc-meta-pill">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
                        Periode: <strong>{html.escape(report.period_label)}</strong>
                    </span>
                    <span class="doc-meta-pill">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                        Diterbitkan: <strong>{today_str}</strong>
                    </span>
                </div>
            </div>
            <div class="doc-badge-card">
                <span class="doc-status-badge">
                    <span class="status-dot"></span>
                    Dokumen Resmi
                </span>
                <span class="doc-badge-meta">Klasifikasi: Arsip Konfidensial</span>
                <span class="doc-badge-meta">Mata Uang: IDR (Rupiah)</span>
            </div>
        </header>

        <section class="doc-banner">
            <span class="doc-banner-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="16" y2="12"/><line x1="12" x2="12.01" y1="8" y2="8"/></svg>
            </span>
            <div>{html.escape(note)}</div>
        </section>

        <section class="totals-grid">
            {totals_html}
        </section>

        <section class="data-section">
            <div class="section-header">
                <div class="section-title">
                    <span>Rincian {html.escape(report.title)}</span>
                    <span class="section-count">{len(report.rows)} Catatan</span>
                </div>
                <div class="section-note">Standar Pembukuan Berpasangan</div>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>{head_html}</tr>
                    </thead>
                    <tbody>
                        {body_html if body_html else empty_state_html}
                    </tbody>
                    {tfoot_html}
                </table>
            </div>
        </section>

        <section class="doc-sign-grid">
            <div class="sign-disclaimer">
                <strong>Catatan Integritas Data:</strong>
                Laporan ini disusun secara otomatis melalui ledger tersentralisasi Finance Family. Digunakan sebagai dasar rekonsiliasi berkala dan arsip fisik/digital keluarga.
            </div>
            <div class="sign-box">
                <div class="sign-role">Disusun Oleh</div>
                <div class="sign-line"></div>
                <div class="sign-name">( Pengelola Keuangan )</div>
            </div>
            <div class="sign-box">
                <div class="sign-role">Diverifikasi & Disetujui</div>
                <div class="sign-line"></div>
                <div class="sign-name">( Kepala Keluarga )</div>
            </div>
        </section>

        <footer class="report-footer">
            <span>Dokumen dibuat dari pembukuan Finance Family</span>
            <span>Dicetak untuk arsip keluarga</span>
        </footer>
    </main>
</body>
</html>"""

