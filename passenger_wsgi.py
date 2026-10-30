"""WSGI entrypoint for cPanel Passenger.

This keeps the bot online through Telegram webhook requests instead of a
long-running polling process, which is the correct model for shared hosting.
"""
import json
import os
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.categorizer import categorize
from src.config import load_settings
from src.database import Database
from src.formatting import render_confirmation
from src.models import Transaction
from src.parser import ParseError, parse_message


def _send_message(chat_id, text):
    token = os.environ["BOT_TOKEN"]
    body = urlencode({"chat_id": chat_id, "text": text}).encode()
    req = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    with urlopen(req, timeout=20):
        pass


def _set_webhook():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        return
    body = urlencode({"url": "https://asistenq.com/family-finance/"}).encode()
    req = Request(f"https://api.telegram.org/bot{token}/setWebhook", data=body, method="POST")
    with urlopen(req, timeout=20):
        pass


def application(environ, start_response):
    if environ.get("REQUEST_METHOD") == "GET":
        try:
            _set_webhook()
        except Exception:
            pass
        payload = b"family-finance bot is online"
        start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", str(len(payload)))])
        return [payload]

    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
        update = json.loads(environ["wsgi.input"].read(length) or b"{}")
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        text = message.get("text") or ""
        settings = load_settings()
        chat_id = str(chat.get("id", ""))
        if chat_id in settings.allowed_chat_ids and text and not text.startswith("/"):
            db = Database(settings.database_path)
            db.initialize()
            parsed = parse_message(text, datetime.now(), settings.timezone)
            category = categorize(parsed.description, db.list_categories())
            item = db.add_transaction(Transaction(None, str(sender.get("id", "")), sender.get("username") or sender.get("first_name") or "user", chat_id, parsed.type, parsed.amount, parsed.description, category.name, parsed.transaction_date, datetime.now()))
            _send_message(chat_id, render_confirmation(item, sender.get("username") or sender.get("first_name") or "user"))
        elif chat_id in settings.allowed_chat_ids and text.startswith("/start"):
            _send_message(chat_id, "👋 Halo! Kirim contoh seperti: bensin 50rb atau gaji masuk 8jt")
        start_response("200 OK", [("Content-Type", "application/json")])
        return [b'{"ok":true}']
    except ParseError as exc:
        if chat_id:
            _send_message(chat_id, f"❓ {exc}")
        start_response("200 OK", [("Content-Type", "application/json")])
        return [b'{"ok":true}']
    except Exception:
        start_response("500 Internal Server Error", [("Content-Type", "text/plain")])
        return [b"internal error"]
