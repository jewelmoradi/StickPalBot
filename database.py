import hashlib
import re
import sqlite3
from contextlib import closing
from pathlib import Path

DATABASE_FILE = Path(__file__).resolve().parent / "stickpal.db"


def get_connection():
    """Create a database connection with useful SQLite settings."""

    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    """Create the database tables and constraints if needed."""

    with closing(get_connection()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS packs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pack_name TEXT NOT NULL,
                pack_title TEXT NOT NULL,
                telegram_short_name TEXT NOT NULL UNIQUE,
                FOREIGN KEY (user_id)
                    REFERENCES users(user_id)
                    ON DELETE CASCADE
            )
            """
        )

        # Each user can have a particular internal pack name only once.
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_packs_user_pack_name
            ON packs(user_id, pack_name)
            """
        )

        connection.commit()


def register_user(user_id: int) -> None:
    """Register a Telegram user without creating duplicates."""

    with closing(get_connection()) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO users (user_id)
            VALUES (?)
            """,
            (user_id,),
        )
        connection.commit()


def normalize_pack_name(name: str) -> str:
    """Convert a pack name into a safe internal identifier."""

    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower())
    normalized = normalized.strip("_")

    if not normalized:
        raise ValueError(
            "The pack name must contain English letters or digits."
        )

    return normalized


def generate_telegram_short_name(pack_name: str, user_id: int, bot_username: str,) -> str:
    """Generate a unique, valid Telegram sticker-set short name."""

    slug = normalize_pack_name(pack_name)
    username = bot_username.removeprefix("@").lower()

    if not username:
        raise ValueError("The bot username cannot be empty.")

    # Telegram requires this suffix for bot-created sticker sets
    ending = f"_{user_id}_by_{username}"
    available_length = 64 - len(ending)

    if available_length < 7:
        raise ValueError("The generated Telegram short name would be too long.")

    if len(slug) > available_length:  # keep long names within Telegram's 64-character limit
        digest = hashlib.sha256(slug.encode("utf-8")).hexdigest()[:6]  # the hash helps distinguish different long names

        prefix_length = available_length - 7
        prefix = slug[:prefix_length].rstrip("_")
        slug = f"{prefix}_{digest}"

    return f"{slug}{ending}"


def create_pack(user_id: int, pack_name: str, pack_title: str, bot_username: str,) -> dict:
    """Save a named pack belonging to a particular user."""

    pack_name = normalize_pack_name(pack_name)
    pack_title = pack_title.strip()

    if not pack_title:
        raise ValueError("The pack title cannot be empty.")

    if len(pack_title) > 64:
        raise ValueError(
            "The pack title cannot exceed 64 characters."
        )

    telegram_short_name = generate_telegram_short_name(pack_name=pack_name, user_id=user_id, bot_username=bot_username,)

    register_user(user_id)

    try:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO packs (
                    user_id,
                    pack_name,
                    pack_title,
                    telegram_short_name
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    user_id,
                    pack_name,
                    pack_title,
                    telegram_short_name,
                ),
            )

            connection.commit()

            return {
                "id": cursor.lastrowid,
                "user_id": user_id,
                "pack_name": pack_name,
                "pack_title": pack_title,
                "telegram_short_name": telegram_short_name,
            }

    except sqlite3.IntegrityError as error:
        raise ValueError("This pack name already exists for the user,"
                         "or the Telegram short name is already in use.") from error


def get_pack(user_id: int, pack_name: str):
    """Find a pack by its owner's ID and internal name."""

    pack_name = normalize_pack_name(pack_name)

    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM packs
            WHERE user_id = ? AND pack_name = ?
            """,
            (user_id, pack_name),
        ).fetchone()

        return dict(row) if row else None


def get_pack_by_short_name(telegram_short_name: str):
    """Find a pack using its Telegram short name."""

    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM packs
            WHERE telegram_short_name = ?
            """,
            (telegram_short_name,),
        ).fetchone()

        return dict(row) if row else None


def list_packs(user_id: int) -> list[dict]:
    """Return all packs registered for one user."""

    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM packs
            WHERE user_id = ?
            ORDER BY id
            """,
            (user_id,),
        ).fetchall()

        return [dict(row) for row in rows]


if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully.")
