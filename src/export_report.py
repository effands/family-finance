"""Export report generator for Excel (.xlsx) and PDF documents.

Finance Family — Dibuat oleh effands ~ ziqva.com team with love family @2026.
"""
import io
from datetime import date, datetime

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .formatting import format_rupiah
from .models import Transaction


def generate_excel(rows: list[Transaction], summary_data: dict, period_name: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rekap Keuangan"
    ws.views.sheetView[0].showGridLines = True

    # Color Palette & Styles
    navy_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    soft_blue_fill = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
    income_fill = PatternFill(start_color="ECFDF5", end_color="ECFDF5", fill_type="solid")
    expense_fill = PatternFill(start_color="FFF1F2", end_color="FFF1F2", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    font_title = Font(name="Segoe UI", size=15, bold=True, color="1E3A8A")
    font_subtitle = Font(name="Segoe UI", size=10, italic=True, color="64748B")
    font_header = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    font_kpi_label = Font(name="Segoe UI", size=9, bold=True, color="475569")
    font_kpi_val = Font(name="Segoe UI", size=12, bold=True)
    font_data = Font(name="Segoe UI", size=9.5)
    font_income = Font(name="Segoe UI", size=9.5, bold=True, color="059669")
    font_expense = Font(name="Segoe UI", size=9.5, bold=True, color="E11D48")
    font_footer = Font(name="Segoe UI", size=8.5, italic=True, color="64748B")

    thin_border_side = Side(style="thin", color="CBD5E1")
    border_all = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

    # 1. Title Block
    ws.cell(row=1, column=1, value="FINANCE FAMILY — LAPORAN KEUANGAN KELUARGA").font = font_title
    ws.cell(
        row=2,
        column=1,
        value=f"Periode: {period_name}  |  Dicetak: {datetime.now().strftime('%d/%m/%Y %H:%M')} WIB",
    ).font = font_subtitle

    # 2. Financial Summary KPI Card (Rows 4-5)
    income = summary_data.get("income", 0)
    expense = summary_data.get("expense", 0)
    balance = income - expense
    savings_rate = summary_data.get("savings_rate", 0)

    kpi_headers = ["Total Pemasukan", "Total Pengeluaran", "Arus Kas Bersih (Net)", "Rasio Tabungan", "Jumlah Transaksi"]
    kpi_values = [income, expense, balance, f"{savings_rate}%", len(rows)]

    for col_idx, (hdr, val) in enumerate(zip(kpi_headers, kpi_values), start=1):
        cell_h = ws.cell(row=4, column=col_idx, value=hdr)
        cell_h.font = font_kpi_label
        cell_h.fill = soft_blue_fill
        cell_h.alignment = Alignment(horizontal="center", vertical="center")
        cell_h.border = border_all

        cell_v = ws.cell(row=5, column=col_idx, value=val)
        cell_v.font = font_kpi_val
        cell_v.border = border_all
        cell_v.alignment = Alignment(horizontal="center", vertical="center")
        if isinstance(val, (int, float)):
            cell_v.number_format = '"Rp "#,##0'
            if hdr == "Total Pemasukan":
                cell_v.font = Font(name="Segoe UI", size=11, bold=True, color="059669")
            elif hdr == "Total Pengeluaran":
                cell_v.font = Font(name="Segoe UI", size=11, bold=True, color="E11D48")

    # 3. Transaction Ledger Table Headers (Row 7)
    headers = ["No", "ID", "Tanggal", "Jenis Transaksi", "Kategori", "Deskripsi Transaksi", "Nominal (IDR)", "Pencatat (Anggota)"]
    for col_idx, text in enumerate(headers, start=1):
        c = ws.cell(row=7, column=col_idx, value=text)
        c.font = font_header
        c.fill = navy_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border_all

    # 4. Transaction Rows
    current_row = 8
    for idx, tx in enumerate(rows, start=1):
        is_inc = tx.type == "income"
        type_label = "Pemasukan" if is_inc else "Pengeluaran"
        row_cells = [
            (idx, Alignment(horizontal="center")),
            (tx.id, Alignment(horizontal="center")),
            (tx.transaction_date.strftime("%d/%m/%Y"), Alignment(horizontal="center")),
            (type_label, Alignment(horizontal="center")),
            (tx.category, Alignment(horizontal="left")),
            (tx.description, Alignment(horizontal="left")),
            (tx.amount, Alignment(horizontal="right")),
            (tx.username or tx.user_id or "User", Alignment(horizontal="left")),
        ]

        row_fill = income_fill if is_inc else (zebra_fill if idx % 2 == 0 else PatternFill(fill_type=None))

        for col_idx, (val, align) in enumerate(row_cells, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = font_income if (col_idx == 7 and is_inc) else (font_expense if (col_idx == 7 and not is_inc) else font_data)
            cell.alignment = align
            cell.border = border_all
            if row_fill.fill_type:
                cell.fill = row_fill
            if col_idx == 7:
                cell.number_format = '"Rp "#,##0'

        current_row += 1

    # 5. Footer Signature Note
    current_row += 1
    ws.cell(
        row=current_row,
        column=1,
        value="Dokumen Resmi Pembukuan Keuangan Keluarga · Dibuat oleh effands ~ ziqva.com team with love family @2026",
    ).font = font_footer

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 11)
    ws.column_dimensions["F"].width = max(ws.column_dimensions["F"].width, 28)

    buff = io.BytesIO()
    wb.save(buff)
    return buff.getvalue()


def generate_pdf(rows: list[Transaction], summary_data: dict, period_name: str) -> bytes:
    buff = io.BytesIO()
    doc = SimpleDocTemplate(
        buff,
        pagesize=A4,
        leftMargin=32,
        rightMargin=32,
        topMargin=32,
        bottomMargin=32,
    )

    styles = getSampleStyleSheet()

    # Custom Clean Styles
    style_title = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#1e3a8a"),
        alignment=0,
        spaceAfter=2,
    )
    style_subtitle = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#475569"),
        alignment=0,
        spaceAfter=6,
    )
    style_kpi_label = ParagraphStyle(
        "KpiLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#64748b"),
        alignment=1,
    )
    style_kpi_val = ParagraphStyle(
        "KpiVal",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        alignment=1,
    )
    style_th = ParagraphStyle(
        "TableHead",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.white,
        alignment=1,
    )
    style_td = ParagraphStyle(
        "TableData",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#0f172a"),
    )
    style_td_center = ParagraphStyle(
        "TableDataCenter",
        parent=style_td,
        alignment=1,
    )
    style_td_right = ParagraphStyle(
        "TableDataRight",
        parent=style_td,
        alignment=2,
    )
    style_income = ParagraphStyle(
        "IncomeText",
        parent=style_td_right,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#059669"),
    )
    style_expense = ParagraphStyle(
        "ExpenseText",
        parent=style_td_right,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#e11d48"),
    )
    style_footer = ParagraphStyle(
        "DocFooter",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#64748b"),
        alignment=1,
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("FINANCE FAMILY — LAPORAN RESMI KEUANGAN KELUARGA", style_title))
    story.append(
        Paragraph(
            f"<b>Periode Pembukuan:</b> {period_name} &nbsp;|&nbsp; <b>Dicetak:</b> {datetime.now().strftime('%d %b %Y, %H:%M')} WIB &nbsp;|&nbsp; <b>Status Sistem:</b> Terverifikasi & Akuntabel",
            style_subtitle,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1e3a8a"), spaceAfter=8))

    # 2. KPI Summary Boxes Table
    income = summary_data.get("income", 0)
    expense = summary_data.get("expense", 0)
    balance = income - expense
    savings_rate = summary_data.get("savings_rate", 0)

    bal_color = "#059669" if balance > 0 else ("#e11d48" if balance < 0 else "#4f46e5")
    bal_status = "(Surplus)" if balance > 0 else ("(Defisit)" if balance < 0 else "(Nol)")

    kpi_data = [
        [
            Paragraph("TOTAL PEMASUKAN", style_kpi_label),
            Paragraph("TOTAL PENGELUARAN", style_kpi_label),
            Paragraph("ARUS KAS BERSIH (NET)", style_kpi_label),
            Paragraph("RETENSI TABUNGAN", style_kpi_label),
        ],
        [
            Paragraph(f"<font color='#059669'>{format_rupiah(income)}</font>", style_kpi_val),
            Paragraph(f"<font color='#e11d48'>{format_rupiah(expense)}</font>", style_kpi_val),
            Paragraph(f"<font color='{bal_color}'>{format_rupiah(balance)} {bal_status}</font>", style_kpi_val),
            Paragraph(f"<font color='#1e3a8a'>{savings_rate}%</font>", style_kpi_val),
        ],
    ]

    t_kpi = Table(kpi_data, colWidths=[132, 132, 138, 128])
    t_kpi.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(t_kpi)
    story.append(Spacer(1, 10))

    # 3. Transaction Data Table
    th_cells = [
        Paragraph("No", style_th),
        Paragraph("Tanggal", style_th),
        Paragraph("Jenis", style_th),
        Paragraph("Kategori", style_th),
        Paragraph("Deskripsi Transaksi", style_th),
        Paragraph("Nominal", style_th),
        Paragraph("Pencatat", style_th),
    ]

    rows_data = [th_cells]

    if not rows:
        empty_row = [Paragraph("Tidak ada catatan transaksi pada periode ini.", style_td_center)] * 7
        rows_data.append(empty_row)
    else:
        for idx, tx in enumerate(rows, start=1):
            is_inc = tx.type == "income"
            type_text = "Pemasukan" if is_inc else "Pengeluaran"
            sign = "+" if is_inc else "-"
            amt_style = style_income if is_inc else style_expense

            rows_data.append([
                Paragraph(str(idx), style_td_center),
                Paragraph(tx.transaction_date.strftime("%d/%m/%Y"), style_td_center),
                Paragraph(type_text, style_td_center),
                Paragraph(tx.category, style_td),
                Paragraph(tx.description, style_td),
                Paragraph(f"{sign} {format_rupiah(tx.amount)}", amt_style),
                Paragraph(tx.username or tx.user_id or "User", style_td),
            ])

    # Printable width A4: 595 - 64 = 531
    t_ledger = Table(rows_data, colWidths=[24, 52, 60, 84, 185, 78, 48], repeatRows=1)
    
    table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    for r_idx in range(1, len(rows_data)):
        if r_idx % 2 == 0:
            table_styles.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#f8fafc")))

    t_ledger.setStyle(TableStyle(table_styles))
    story.append(t_ledger)
    story.append(Spacer(1, 14))

    # 4. Signatures Block
    sig_data = [
        [
            Paragraph("Mengetahui,<br/><b>Kepala Keluarga</b><br/><br/><br/><br/>( ................................................. )", style_td_center),
            Paragraph("", style_td_center),
            Paragraph("Penyusun Dokumen,<br/><b>Pengelola Finansial</b><br/><br/><br/><br/>( ................................................. )", style_td_center),
        ]
    ]
    t_sig = Table(sig_data, colWidths=[200, 130, 200])
    t_sig.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(t_sig)
    story.append(Spacer(1, 10))

    # 5. Document Footer
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=5))
    story.append(
        Paragraph(
            "Finance Family · Dibuat oleh effands ~ ziqva.com team with love family @2026",
            style_footer,
        )
    )

    doc.build(story)
    return buff.getvalue()
