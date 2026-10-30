from dataclasses import dataclass
import os
from dotenv import load_dotenv

@dataclass(frozen=True)
class Settings:
    bot_token:str; allowed_chat_ids:set[str]; timezone:str="Asia/Jakarta"; database_path:str="data/money.db"; log_path:str="money-bot.log"; rate_limit:int=30

def load_settings()->Settings:
    load_dotenv(); token=os.getenv("BOT_TOKEN","").strip()
    if not token: raise RuntimeError("BOT_TOKEN belum diisi di file .env")
    return Settings(token,{x.strip() for x in os.getenv("ALLOWED_CHAT_IDS","").split(",") if x.strip()},os.getenv("TIMEZONE","Asia/Jakarta"),os.getenv("DATABASE_PATH","data/money.db"),os.getenv("LOG_PATH","money-bot.log"),int(os.getenv("RATE_LIMIT_PER_MINUTE","30")))
