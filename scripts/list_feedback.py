import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from database import get_connection, init_db  # noqa: E402

ALLOWED_STATUSES = {"new", "reviewing", "resolved", "closed"}


def parse_args():
    parser = argparse.ArgumentParser(description="List submitted user feedback.")
    parser.add_argument("--status", choices=sorted(ALLOWED_STATUSES))
    parser.add_argument("--limit", type=int, default=50)
    return parser.parse_args()


def truncate(value, length=80):
    text = value or ""
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "..."


def main():
    args = parse_args()
    limit = min(max(args.limit, 1), 200)
    where_sql = ""
    params = []
    if args.status:
        where_sql = "WHERE status = ?"
        params.append(args.status)
    params.append(limit)

    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, user_id, feedback_type, title, status, created_at, contact, content
            FROM feedback
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    if not rows:
        print("No feedback found.")
        return

    for row in rows:
        print(f"ID: {row['id']}")
        print(f"User ID: {row['user_id']}")
        print(f"Type: {row['feedback_type']}")
        print(f"Title: {row['title']}")
        print(f"Status: {row['status']}")
        print(f"Created: {row['created_at']}")
        print(f"Contact: {row['contact'] or '-'}")
        print(f"Summary: {truncate(row['content'])}")
        print("-" * 40)


if __name__ == "__main__":
    main()
