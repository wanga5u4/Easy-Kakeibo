import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "accounting.db"
DEFAULT_BACKUP_DIR = BASE_DIR / "backups"


def resolve_path(value, default):
    path = Path(value) if value else default
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def get_retention_days():
    raw_value = os.environ.get("BACKUP_RETENTION_DAYS", "14")
    try:
        days = int(raw_value)
    except ValueError:
        raise ValueError("BACKUP_RETENTION_DAYS must be an integer")
    if days < 0:
        raise ValueError("BACKUP_RETENTION_DAYS must be zero or greater")
    return days


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [backup_database] %(message)s",
    )


def create_backup(now=None):
    now = now or datetime.now()
    database_path = resolve_path(os.environ.get("DATABASE_PATH"), DEFAULT_DB_PATH)
    backup_dir = resolve_path(os.environ.get("BACKUP_DIR"), DEFAULT_BACKUP_DIR)
    retention_days = get_retention_days()

    if not database_path.exists():
        raise FileNotFoundError("Database file does not exist")
    if not database_path.is_file():
        raise ValueError("Database path is not a file")

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"accounting-{now.strftime('%Y-%m-%d-%H%M%S')}.db"

    with sqlite3.connect(database_path) as source_conn:
        with sqlite3.connect(backup_path) as backup_conn:
            source_conn.backup(backup_conn)

    cleanup_old_backups(backup_dir, retention_days, keep_path=backup_path, now=now)
    logging.info("Backup created: %s", backup_path)
    return backup_path


def cleanup_old_backups(backup_dir, retention_days, keep_path=None, now=None):
    now = now or datetime.now()
    cutoff = now - timedelta(days=retention_days)
    keep_path = keep_path.resolve() if keep_path else None
    deleted = []

    for path in backup_dir.glob("accounting-*.db"):
        if keep_path and path.resolve() == keep_path:
            continue
        modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        if modified_at < cutoff:
            path.unlink()
            deleted.append(path)
            logging.info("Deleted expired backup: %s", path)

    return deleted


def main():
    configure_logging()
    try:
        create_backup()
    except Exception as exc:
        logging.error("Backup failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
