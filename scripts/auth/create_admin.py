from __future__ import annotations

import argparse
import getpass
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

from backend.infrastructure.database.postgres import database_connection, init_database
from backend.modules.auth.service import _validate_registration


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update an administrator account.")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--email", default="admin@xfdemo.local")
    parser.add_argument("--display-name", default="系统管理员")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    password = getpass.getpass("Admin password: ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n")
    _validate_registration(args.username, args.email, password, args.display_name)
    init_database()

    with database_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO users (
                    id, username, username_normalized, email, email_normalized,
                    display_name, password_hash, role, is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'admin', TRUE)
                ON CONFLICT (username_normalized) DO UPDATE SET
                    username = EXCLUDED.username,
                    email = EXCLUDED.email,
                    email_normalized = EXCLUDED.email_normalized,
                    display_name = EXCLUDED.display_name,
                    password_hash = EXCLUDED.password_hash,
                    role = 'admin',
                    is_active = TRUE,
                    updated_at = NOW()
                RETURNING username, email, role
                """,
                (
                    str(uuid.uuid4()),
                    args.username,
                    args.username.casefold(),
                    args.email,
                    args.email.casefold(),
                    args.display_name,
                    generate_password_hash(password, method="scrypt"),
                ),
            )
            user = cursor.fetchone()

    print(f"Administrator ready: {user['username']} ({user['email']})")


if __name__ == "__main__":
    main()
