"""Verified export and import primitives for the family finance database."""

import csv
import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


TABLES = (
    "categories",
    "transactions",
    "financial_accounts",
    "ledger_operations",
    "ledger_entries",
    "account_preferences",
    "user_account_preferences",
    "transaction_details",
    "transaction_items",
    "legacy_ledger_links",
)
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ImportPreview:
    schema_version: int
    chat_id: str
    counts: dict[str, int]
    format: str


@dataclass(frozen=True)
class RestoreResult:
    mode: str
    inserted: int
    conflicts: int
    safety_backup_path: str | None = None


class BackupService:
    def __init__(self, db):
        self.db = db

    def _snapshot(self, chat_id: str) -> dict[str, Any]:
        if not chat_id:
            raise ValueError("chat_id wajib diisi")
        snapshot: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "chat_id": str(chat_id),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.db._conn() as conn:
            for table in TABLES:
                if table == "categories":
                    rows = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
                elif table == "transactions":
                    rows = conn.execute("SELECT * FROM transactions WHERE chat_id=? ORDER BY id", (chat_id,)).fetchall()
                elif table == "financial_accounts":
                    rows = conn.execute("SELECT * FROM financial_accounts WHERE chat_id=? ORDER BY id", (chat_id,)).fetchall()
                elif table == "ledger_operations":
                    rows = conn.execute("SELECT * FROM ledger_operations WHERE chat_id=? ORDER BY id", (chat_id,)).fetchall()
                elif table == "ledger_entries":
                    rows = conn.execute("SELECT * FROM ledger_entries WHERE chat_id=? ORDER BY id", (chat_id,)).fetchall()
                elif table == "account_preferences":
                    rows = conn.execute("SELECT * FROM account_preferences WHERE chat_id=? ORDER BY operation_kind", (chat_id,)).fetchall()
                elif table == "user_account_preferences":
                    rows = conn.execute("SELECT * FROM user_account_preferences WHERE chat_id=? ORDER BY user_id, operation_kind", (chat_id,)).fetchall()
                elif table == "transaction_details":
                    rows = conn.execute("SELECT d.* FROM transaction_details d JOIN transactions t ON t.id=d.transaction_id WHERE t.chat_id=? ORDER BY d.transaction_id", (chat_id,)).fetchall()
                elif table == "transaction_items":
                    rows = conn.execute("SELECT i.* FROM transaction_items i JOIN transactions t ON t.id=i.transaction_id WHERE t.chat_id=? ORDER BY i.transaction_id, i.id", (chat_id,)).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM legacy_ledger_links WHERE chat_id=? ORDER BY transaction_id", (chat_id,)).fetchall()
                snapshot[table] = [dict(row) for row in rows]
        snapshot["counts"] = {table: len(snapshot[table]) for table in TABLES}
        return snapshot

    @staticmethod
    def _json_bytes(snapshot: dict[str, Any]) -> bytes:
        return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
        if not rows:
            return b""
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue().encode("utf-8-sig")

    def export_snapshot(self, chat_id: str, output_format: str) -> bytes:
        output_format = output_format.lower().strip()
        snapshot = self._snapshot(chat_id)
        snapshot_bytes = self._json_bytes(snapshot)
        if output_format == "json":
            return snapshot_bytes
        if output_format == "csv":
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                for table in TABLES:
                    archive.writestr(table + ".csv", self._csv_bytes(snapshot[table]))
            return stream.getvalue()
        if output_format != "zip":
            raise ValueError("Format backup tidak didukung")
        files = {"snapshot.json": snapshot_bytes}
        files.update({table + ".csv": self._csv_bytes(snapshot[table]) for table in TABLES})
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "chat_id": str(chat_id),
            "exported_at": snapshot["exported_at"],
            "counts": snapshot["counts"],
            "checksums": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        }
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", self._json_bytes(manifest))
            for name, data in files.items():
                archive.writestr(name, data)
        return stream.getvalue()

    def _read_snapshot(self, payload: bytes, filename: str) -> tuple[dict[str, Any], str]:
        if filename.lower().endswith(".json"):
            snapshot = json.loads(payload.decode("utf-8"))
            return snapshot, "json"
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                for name, expected in manifest.get("checksums", {}).items():
                    actual = hashlib.sha256(archive.read(name)).hexdigest()
                    if actual != expected:
                        raise ValueError("Checksum backup tidak cocok")
                snapshot = json.loads(archive.read("snapshot.json").decode("utf-8"))
                return snapshot, "zip"
        except zipfile.BadZipFile as exc:
            raise ValueError("File backup bukan JSON atau ZIP yang valid") from exc

    def preview(self, payload: bytes, filename: str, chat_id: str) -> ImportPreview:
        snapshot, fmt = self._read_snapshot(payload, filename)
        if snapshot.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Versi schema backup tidak didukung")
        if str(snapshot.get("chat_id")) != str(chat_id):
            raise ValueError("Backup bukan milik ruang keluarga ini")
        for table in TABLES:
            if not isinstance(snapshot.get(table), list):
                raise ValueError("Struktur backup tidak lengkap")
        return ImportPreview(SCHEMA_VERSION, str(chat_id), {t: len(snapshot[t]) for t in TABLES}, fmt)

    def restore(self, payload: bytes, filename: str, chat_id: str, mode: str, actor: str, confirm_replace: bool = False) -> RestoreResult:
        if mode not in {"merge", "replace"}:
            raise ValueError("Mode restore tidak didukung")
        if mode == "replace" and not confirm_replace:
            raise ValueError("Restore replace memerlukan konfirmasi")
        snapshot, _ = self._read_snapshot(payload, filename)
        self.preview(payload, filename, chat_id)
        safety_path = None
        if mode == "replace":
            fd, safety_path = tempfile.mkstemp(prefix="money.pre-restore-", suffix=".db", dir=os.path.dirname(self.db.path) or None)
            os.close(fd)
            shutil.copy2(self.db.path, safety_path)
        inserted = 0
        conflicts = 0
        with self.db._conn() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if mode == "replace":
                    conn.execute("DELETE FROM transaction_items WHERE transaction_id IN (SELECT id FROM transactions WHERE chat_id=?)", (chat_id,))
                    conn.execute("DELETE FROM transaction_details WHERE transaction_id IN (SELECT id FROM transactions WHERE chat_id=?)", (chat_id,))
                    for table in ("legacy_ledger_links", "user_account_preferences", "account_preferences", "ledger_entries", "ledger_operations", "transactions", "financial_accounts"):
                        conn.execute("DELETE FROM " + table + " WHERE chat_id=?", (chat_id,))
                for table in TABLES:
                    rows = snapshot[table]
                    for row in rows:
                        columns = list(row.keys())
                        values = [row[column] for column in columns]
                        placeholders = ",".join("?" for _ in columns)
                        quoted = ",".join('"' + c.replace('"', '""') + '"' for c in columns)
                        before = conn.total_changes
                        conn.execute("INSERT OR IGNORE INTO " + table + " (" + quoted + ") VALUES (" + placeholders + ")", values)
                        if conn.total_changes > before:
                            inserted += 1
                        else:
                            conflicts += 1
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return RestoreResult(mode, inserted, conflicts, safety_path)
