"""Gemini Vision receipt extraction. Optional: the bot works without it."""
import json
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

def extract_receipt(image_bytes: bytes, api_keys: tuple[str,...], model: str) -> dict:
    if not api_keys: raise RuntimeError("GEMINI_API_KEYS belum diisi")
    last=None
    for key in api_keys:
        try:
            client=genai.Client(api_key=key)
            response=client.models.generate_content(model=model, contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), PROMPT])
            return _clean_json(response.text or "")
        except Exception as exc:
            last=exc
    raise RuntimeError(f"Semua API key Gemini gagal: {last}")
