"""Gemini Vision receipt extraction. Optional: the bot works without it."""
import json
import threading
from datetime import date
from google import genai
from google.genai import types

PROMPT = """Baca struk belanja ini. Balas HANYA JSON valid tanpa markdown:
{"amount": integer rupiah, "description": string, "date": "YYYY-MM-DD" or null, "category": string}
Jika nominal tidak jelas, amount harus 0. description singkat (nama toko/isi utama). category pilih salah satu: Makanan & Minuman, Transportasi, Rumah & Utilitas, Kesehatan, Pulsa & Digital, Anak, Belanja, Pemasukan, Lain-lain."""

def _clean_json(text: str) -> dict:
    text=text.strip().removeprefix("```json").removesuffix("```").strip()
    data=json.loads(text)
    amount=int(data.get("amount") or 0)
    return {"amount": amount, "description": str(data.get("description") or "Struk belanja").strip(), "date": data.get("date") or date.today().isoformat(), "category": str(data.get("category") or "Lain-lain").strip()}

class GeminiKeyPool:
    """Thread-safe round-robin key pool with per-request failover."""
    def __init__(self, api_keys: tuple[str, ...] = (), model: str = "gemini-3.8-flash"):
        self._lock=threading.Lock(); self.update(api_keys, model)
    def update(self, api_keys: tuple[str, ...], model: str):
        with getattr(self, "_lock", threading.Lock()):
            self.keys=tuple(dict.fromkeys(k.strip() for k in api_keys if k.strip())); self.model=model or "gemini-3.8-flash"; self.cursor=getattr(self, "cursor", 0) % max(1,len(self.keys)) if self.keys else 0
    def ordered(self):
        with self._lock:
            if not self.keys: return []
            start=self.cursor % len(self.keys); self.cursor=(start+1) % len(self.keys)
            return [self.keys[(start+i) % len(self.keys)] for i in range(len(self.keys))]
    def test(self) -> tuple[bool, str]:
        errors=[]
        for key in self.ordered():
            try:
                # Client dibuat dan ditutup per percobaan. SDK google-genai
                # dapat mewarisi transport yang sudah tertutup jika object
                # client disimpan/reused lintas request WSGI.
                with genai.Client(api_key=key) as client:
                    response=client.models.generate_content(model=self.model, contents="Tes koneksi. Jawab OK.")
                if response and response.text: return True, "Koneksi berhasil."
            except Exception as exc: errors.append(str(exc))
        return False, " | ".join(errors)[:500] or "Tidak ada respons dari Gemini."

def extract_receipt(image_bytes: bytes, api_keys: tuple[str,...], model: str, pool: GeminiKeyPool | None = None) -> dict:
    pool=pool or GeminiKeyPool(api_keys, model)
    pool.update(api_keys, model)
    if not pool.keys: raise RuntimeError("GEMINI_API_KEYS belum diisi")
    last=None
    for key in pool.ordered():
        try:
            with genai.Client(api_key=key) as client:
                response=client.models.generate_content(model=model, contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), PROMPT])
            return _clean_json(response.text or "")
        except Exception as exc:
            last=exc
    raise RuntimeError(f"Semua API key Gemini gagal: {last}")
