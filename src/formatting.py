from .models import Transaction

def format_rupiah(n:int)->str: return f"Rp {n:,.0f}".replace(",",".")
def render_confirmation(x:Transaction, actor:str)->str:
    label="Pemasukan" if x.type=="income" else "Pengeluaran"; emoji="💰" if x.type=="income" else "💸"
    return f"✅ Tercatat\n{emoji} {label}: {format_rupiah(x.amount)}\n📝 {x.description}\n🏷️ Kategori: {x.category}\n📅 {x.transaction_date:%d %b %Y}\n👤 Dari: @{actor.lstrip('@')}"
