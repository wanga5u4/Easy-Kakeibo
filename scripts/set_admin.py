import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from database import get_connection, init_db


def parse_args():
    parser = argparse.ArgumentParser(
        description="Grant or remove Easy Kakeibo administrator access.",
    )
    parser.add_argument("username", help="Existing username to update.")
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove administrator access instead of granting it.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    username = args.username.strip()
    if not username:
        print("Error: username cannot be empty.", file=sys.stderr)
        return 2

    init_db()
    with get_connection() as conn:
        user = conn.execute(
            "SELECT id, username, is_admin FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not user:
            print(f"Error: user '{username}' was not found.", file=sys.stderr)
            return 1

        new_value = 0 if args.remove else 1
        action = "Removing" if args.remove else "Granting"
        print(f"{action} administrator access for user id={user['id']} username='{user['username']}'.")
        conn.execute(
            "UPDATE users SET is_admin = ? WHERE id = ?",
            (new_value, user["id"]),
        )
        conn.commit()

    result = "removed" if args.remove else "granted"
    print(f"Administrator access {result} successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
