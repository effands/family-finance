"""Gemini Vision receipt extraction. Optional: the bot works without it."""
import json
import threading
import time
from datetime import date
from google import genai
from google.genai import types

GEMINI_TIMEOUT_MS = 120_000

PROMPT = """Baca foto/screenshot transaksi ini. Balas HANYA JSON valid tanpa markdown:
{"amount": integer rupiah, "description": string, "date": "YYYY-MM-DD" or null, "time": "HH:MM" or null, "location": string or null, "transaction_kind":"purchase|transfer|income|expense", "direction":"in|out|unknown", "bank":string or null, "source_bank":string or null, "destination_bank":string or null, "sender":string or null, "recipient":string or null, "recipient_account_identifier":string or null, "reference":string or null, "category": string, "items":[{"name":string,"quantity":number,"unit":string or null,"unit_price":integer,"subtotal":integer,"category":string}]}
Untuk struk belanja, items berisi setiap barang yang terbaca beserta jumlah, harga satuan, dan subtotal. Jangan mengarang item yang tidak terbaca. Untuk transfer, isi bank, sumber/tujuan, pengirim/penerima, referensi, jam, dan lokasi bila terlihat. direction=in berarti uang masuk, out berarti keluar. Nominal dalam rupiah dan 0 jika tidak jelas. category pilih: Makanan & Minuman, Transportasi, Rumah & Utilitas, Kesehatan, Pulsa & Digital, Anak, Belanja, Pemasukan, Lain-lain."""

AUDIO_PROMPT = "Transkripsikan audio Bahasa Indonesia ini secara tepat. Balas hanya kalimat yang diucapkan, tanpa penjelasan tambahan."

TEXT_PROMPT = """Pahami pesan keuangan Bahasa Indonesia berikut dan balas HANYA JSON valid tanpa markdown.
Kembalikan tepat schema ini:
{"type":"income|expense","amount":integer,"description":string,"date":"YYYY-MM-DD" or null,"category":string,"keywords":[string]}
amount harus dalam rupiah dan 0 jika nominal tidak ditemukan. description adalah ringkasan singkat yang tetap menyebut sumber/tujuan penting.
Pilih category dari daftar kategori yang diberikan jika cocok. Jika tidak ada yang cocok, buat nama kategori baru yang singkat dan spesifik; keywords berisi 2-5 kata kunci Bahasa Indonesia untuk kategori baru.
Jangan membuat kategori baru hanya karena variasi penulisan. Jangan gunakan kategori "Lain-lain" jika bisa membuat kategori yang bermakna.
"""

REQUEST_PROMPT = """Pahami maksud pesan pengguna Bahasa Indonesia. Balas HANYA JSON valid:
{"intent":"account_add|expense|income|transfer|cash_withdrawal|question|unknown","question":string or null,"name":string or null,"account_type":"bank|ewallet|cash|investment" or null,"provider":string or null,"holder_name":string or null,"account_identifier":string or null,"opening_balance":integer or null,"amount":integer or null,"description":string or null,"source_hint":string or null}
Jika pengguna ingin menambah akun, isi field akun yang disebut. Jika ada data penting yang kurang, isi question dengan satu pertanyaan pendek dan jelas. Jangan mengarang data.
"""

def transcribe_audio(audio_bytes: bytes, api_keys: tuple[str, ...], model: str, pool=None) -> str:
    pool = pool or GeminiKeyPool(api_keys, model)
    pool.update(api_keys, model)
    last = None
    for key in pool.ordered():
        client = None
        try:
            client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=45_000))
            response = client.models.generate_content(
                model=model,
                contents=[AUDIO_PROMPT, types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg")],
            )
            text = (response.text or "").strip()
            if text:
                return text
        except Exception as exc:
            last = exc
        finally:
            if client is not None and hasattr(client, "close"):
                client.close()
    raise RuntimeError(f"Transkripsi Gemini gagal: {last}")

def interpret_text(text: str, categories: list[str], api_keys: tuple[str, ...], model: str, pool=None) -> dict:
    """Interpret a long natural-language finance message as structured data."""
    pool = pool or GeminiKeyPool(api_keys, model)
    pool.update(api_keys, model)
    if not pool.keys:
        raise RuntimeError("GEMINI_API_KEYS belum diisi")
    prompt = TEXT_PROMPT + "\nKategori yang sudah tersedia: " + ", ".join(categories) + "\nPesan pengguna:\n" + text
    last = None
    for key in pool.ordered():
        client = None
        try:
            client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
            )
            data = json.loads((response.text or "").strip().removeprefix("```json").removesuffix("```").strip())
            result = {
                "type": "income" if str(data.get("type", "expense")).casefold() == "income" else "expense",
                "amount": int(data.get("amount") or 0),
                "description": str(data.get("description") or "Tanpa deskripsi").strip()[:240],
                "date": data.get("date") or date.today().isoformat(),
                "category": str(data.get("category") or "Lain-lain").strip()[:80],
                "keywords": [str(x).strip().casefold() for x in (data.get("keywords") or []) if str(x).strip()],
            }
            date.fromisoformat(result["date"])
            if not result["category"] or any(ord(ch) < 32 for ch in result["category"]):
                raise ValueError("Kategori hasil AI tidak valid")
            if result["amount"] <= 0:
                raise ValueError("Nominal belum terbaca")
            return result
        except Exception as exc:
            last = exc
        finally:
            if client is not None and hasattr(client, "close"):
                client.close()
    raise RuntimeError(f"Interpretasi teks Gemini gagal: {last}")


def interpret_request(text: str, api_keys: tuple[str, ...], model: str, pool=None) -> dict:
    """Classify arbitrary finance text and extract account/source fields."""
    pool = pool or GeminiKeyPool(api_keys, model)
    pool.update(api_keys, model)
    if not pool.keys:
        raise RuntimeError("GEMINI_API_KEYS belum diisi")
    last = None
    for key in pool.ordered():
        client = None
        try:
            client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))
            response = client.models.generate_content(
                model=model,
                contents=REQUEST_PROMPT + "\nPesan pengguna:\n" + text,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
            )
            data = json.loads((response.text or "").strip())
            allowed = {"account_add", "expense", "income", "transfer", "cash_withdrawal", "question", "unknown"}
            intent = str(data.get("intent") or "unknown").casefold()
            return {
                "intent": intent if intent in allowed else "unknown",
                "question": str(data.get("question") or "").strip()[:240],
                "name": str(data.get("name") or "").strip()[:100],
                "account_type": str(data.get("account_type") or "").strip().casefold(),
                "provider": str(data.get("provider") or "").strip()[:100],
                "holder_name": str(data.get("holder_name") or "").strip()[:100],
                "account_identifier": str(data.get("account_identifier") or "").strip()[:60],
                "opening_balance": data.get("opening_balance"),
                "amount": data.get("amount"),
                "description": str(data.get("description") or "").strip()[:240],
                "source_hint": str(data.get("source_hint") or "").strip()[:100],
            }
        except Exception as exc:
            last = exc
        finally:
            if client is not None and hasattr(client, "close"):
                client.close()
    raise RuntimeError(f"Analisa pesan Gemini gagal: {last}")

def _clean_json(text: str) -> dict:
    text=text.strip().removeprefix("```json").removesuffix("```").strip()
    data=json.loads(text)
    amount=int(data.get("amount") or 0)
    if amount < 0 or amount > 10_000_000_000:
        raise ValueError("Nominal hasil AI tidak valid")
    parsed_date = data.get("date") or date.today().isoformat()
    try:
        date.fromisoformat(parsed_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("Tanggal hasil AI tidak valid") from exc
    items = []
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        try:
            quantity = float(item.get("quantity") or 1)
            unit_price = int(item.get("unit_price") or 0)
            subtotal = int(item.get("subtotal") or 0)
            if quantity <= 0 or unit_price < 0 or subtotal < 0:
                continue
            name = str(item.get("name") or "Item tidak dikenal").strip()[:160]
            if name:
                items.append({"name": name, "quantity": quantity, "unit": item.get("unit"), "unit_price": unit_price, "subtotal": subtotal, "category": str(item.get("category") or data.get("category") or "Lain-lain").strip()[:80]})
        except (TypeError, ValueError):
            continue
    result = {"amount": amount, "description": str(data.get("description") or "Struk belanja").strip()[:240], "date": parsed_date, "category": str(data.get("category") or "Lain-lain").strip()[:80]}
    extra_keys = ("time", "location", "transaction_kind", "direction", "bank", "source_bank", "destination_bank", "sender", "recipient", "recipient_account_identifier", "reference")
    if items or any(key in data for key in extra_keys):
        result.update({"time": data.get("time"), "location": data.get("location"), "transaction_kind": data.get("transaction_kind") or "purchase", "direction": data.get("direction") or "unknown", "bank": data.get("bank"), "source_bank": data.get("source_bank"), "destination_bank": data.get("destination_bank"), "sender": data.get("sender"), "recipient": data.get("recipient"), "recipient_account_identifier": data.get("recipient_account_identifier"), "reference": data.get("reference"), "items": items})
    return result

class GeminiKeyPool:
    """Thread-safe round-robin key pool with per-request failover."""
    def __init__(self, api_keys: tuple[str, ...] = (), model: str = "gemini-3.6-flash"):
        self._lock=threading.Lock(); self.update(api_keys, model)
    def update(self, api_keys: tuple[str, ...], model: str):
        with getattr(self, "_lock", threading.Lock()):
            self.keys=tuple(dict.fromkeys(k.strip() for k in api_keys if k.strip())); self.model=model or "gemini-3.6-flash"; self.cursor=getattr(self, "cursor", 0) % max(1,len(self.keys)) if self.keys else 0
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
                client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))
                response=client.models.generate_content(model=self.model, contents="Tes koneksi. Jawab OK.")
                if hasattr(client, "close"):
                    client.close()
                if response and response.text: return True, "Koneksi berhasil."
            except Exception as exc: errors.append(str(exc))
        return False, " | ".join(errors)[:500] or "Tidak ada respons dari Gemini."

def extract_receipt(image_bytes: bytes, api_keys: tuple[str,...], model: str, pool: GeminiKeyPool | None = None) -> dict:
    pool=pool or GeminiKeyPool(api_keys, model)
    pool.update(api_keys, model)
    if not pool.keys: raise RuntimeError("GEMINI_API_KEYS belum diisi")
    last=None
    # Telegram biasanya mengirim JPEG, tetapi tetap deteksi format agar PNG/WEBP
    # dari pengguna tidak dikirim dengan MIME type yang salah.
    mime_type = "image/png" if image_bytes.startswith(b"\x89PNG") else "image/webp" if image_bytes.startswith(b"RIFF") else "image/jpeg"
    models = list(dict.fromkeys([model, "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]))
    for key in pool.ordered():
        for candidate in models:
            for attempt in range(2):
                client = None
                try:
                    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))
                    response=client.models.generate_content(
                        model=candidate,
                        contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type), PROMPT],
                        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
                    )
                    return _clean_json(response.text or "")
                except Exception as exc:
                    last=exc
                    detail = str(exc).lower()
                    # 503/429 biasanya sementara atau model sedang padat;
                    # coba ulang sebentar lalu pindah ke model cadangan.
                    if attempt == 0 and ("503" in detail or "504" in detail or "deadline" in detail or "unavailable" in detail or "429" in detail or "resource_exhausted" in detail):
                        time.sleep(1)
                        continue
                    break
                finally:
                    if client is not None and hasattr(client, "close"):
                        client.close()
    raise RuntimeError(f"Semua API key Gemini gagal: {last}")
