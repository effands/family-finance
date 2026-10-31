"""Gemini Vision receipt extraction. Optional: the bot works without it."""
import json
import threading
import time
from datetime import date
from google import genai
from google.genai import types

GEMINI_TIMEOUT_MS = 120_000

PROMPT = """Baca struk belanja ini. Balas HANYA JSON valid tanpa markdown:
{"amount": integer rupiah, "description": string, "date": "YYYY-MM-DD" or null, "category": string}
Jika nominal tidak jelas, amount harus 0. description singkat (nama toko/isi utama). category pilih salah satu: Makanan & Minuman, Transportasi, Rumah & Utilitas, Kesehatan, Pulsa & Digital, Anak, Belanja, Pemasukan, Lain-lain."""

AUDIO_PROMPT = "Transkripsikan audio Bahasa Indonesia ini secara tepat. Balas hanya kalimat yang diucapkan, tanpa penjelasan tambahan."

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

def _clean_json(text: str) -> dict:
    text=text.strip().removeprefix("```json").removesuffix("```").strip()
    data=json.loads(text)
    amount=int(data.get("amount") or 0)
    return {"amount": amount, "description": str(data.get("description") or "Struk belanja").strip(), "date": data.get("date") or date.today().isoformat(), "category": str(data.get("category") or "Lain-lain").strip()}

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
