from dataclasses import dataclass
import os
import sqlite3
from dotenv import load_dotenv

@dataclass(frozen=True)
class Settings:
    bot_token: str
    allowed_chat_ids: set[str]
    timezone: str = "Asia/Jakarta"
    database_path: str = "data/money.db"
    log_path: str = "money-bot.log"
    rate_limit: int = 30
    gemini_api_keys: tuple[str, ...] = ()
    gemini_model: str = "gemini-3.6-flash"


def load_settings(custom_db_path: str | None = None) -> Settings:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN belum diisi di file .env")
    
    db_path = custom_db_path or os.getenv("DATABASE_PATH", "data/money.db")
    db_gemini_keys = ""
    db_gemini_model = ""
    try:
        if os.path.exists(db_path):
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT value FROM app_settings WHERE key='gemini_api_keys'")
                row = cur.fetchone()
                if row:
                    db_gemini_keys = row[0]
                cur.execute("SELECT value FROM app_settings WHERE key='gemini_model'")
                row_model = cur.fetchone()
                if row_model:
                    db_gemini_model = row_model[0]
    except Exception:
        pass

    raw_keys = db_gemini_keys or os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
    keys = tuple(x.strip() for x in raw_keys.split(",") if x.strip())
    model = db_gemini_model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    return Settings(
        token,
        {x.strip() for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()},
        os.getenv("TIMEZONE", "Asia/Jakarta"),
        db_path,
        os.getenv("LOG_PATH", "money-bot.log"),
        int(os.getenv("RATE_LIMIT_PER_MINUTE", "30")),
        keys,
        model
    )
