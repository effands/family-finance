from datetime import date, datetime, timedelta
from .database import Database
from .formatting import format_rupiah
from .models import TransactionFilters

MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

def period(kind, now):
    if " " in kind:
        a,b=kind.split(" ",1); return date.fromisoformat(a), date.fromisoformat(b), f"{a} s/d {b}"
    if kind in ("hari","day"): return now.date(), now.date(), "Hari ini"
    if kind in ("minggu","week"): return now.date()-timedelta(days=now.weekday()), now.date()+timedelta(days=6-now.weekday()), "Minggu ini"
    if kind in ("bulan","month"): return now.date().replace(day=1), (now.date().replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1), f"{MONTHS[now.month-1]} {now.year}"
    if kind=="all": return None,None,"Semua transaksi"
    if len(kind)==7 and kind[4]=="-":
        y,m=map(int,kind.split("-")); start=date(y,m,1); end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1); return start,end,f"{MONTHS[m-1]} {y}"
    raise ValueError("Format periode tidak dikenali")

def build_report(db:Database, kind:str, chat_id:str, now:datetime, user_id=None)->str:
    start,end,title=period(kind,now); rows=db.list_transactions(TransactionFilters(chat_id,start,end,user_id)); income=sum(x.amount for x in rows if x.type=="income"); expense=sum(x.amount for x in rows if x.type=="expense")
    out=[f"📊 LAPORAN KEUANGAN — {title}","━━━━━━━━━━━━━━━━━━━━━━",f"💰 Pemasukan : {format_rupiah(income)}",f"💸 Pengeluaran : {format_rupiah(expense)}",f"📈 Saldo : {format_rupiah(income-expense)}","━━━━━━━━━━━━━━━━━━━━━━","Detail Pengeluaran per Kategori:"]
    cats={};
    for x in rows:
        if x.type=="expense": cats[x.category]=cats.get(x.category,0)+x.amount
    for k,v in sorted(cats.items(), key=lambda z:-z[1]): out.append(f"• {k}: {format_rupiah(v)} ({round(v*100/expense) if expense else 0}%)")
    users={}
    for x in rows:
        if x.type=="expense": users[x.username or x.user_id]=users.get(x.username or x.user_id,0)+x.amount
    out += ["━━━━━━━━━━━━━━━━━━━━━━",f"🧾 Total Transaksi: {len(rows)}","👤 Per User:"]+[f"• {k} : {format_rupiah(v)}" for k,v in users.items()]
    return "\n".join(out)

def build_recap(db,kind,chat_id,now,user_id=None): return build_report(db,kind,chat_id,now,user_id)
