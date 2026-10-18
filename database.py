import re
import sqlite3
from contextlib import closing
from pathlib import Path

DATABASE_FILE = Path(__file__).resolve().parent / "stickpal.db"


def get_connection():
    """Create a SQLite connection with foreign keys enabled."""

    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    """Create the tables and indexes needed by StickPalBot."""

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
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
            """
        )

        # each user can have a particular internal pack name only once
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_packs_user_pack_name
            ON packs(user_id, pack_name)
            """
        )

        # we need to remember which pack each user has selected
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS selected_packs (
                user_id INTEGER PRIMARY KEY,
                pack_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE CASCADE
            )
            """
        )

        connection.commit()


def register_user(user_id: int) -> None:
    """Register a Telegram user without creating duplicates."""

    with closing(get_connection()) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO users (user_id) VALUES (?)
            """,
            (user_id,),
        )
        connection.commit()


def normalize_pack_name(title: str) -> str:
    """Convert a pack's visible title into a safe internal identifier."""

    normalized = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return (normalized or "sticker_pack")[:32].rstrip("_") or "sticker_pack"


def generate_telegram_short_name(pack_name: str, user_id: int, bot_username: str,) -> str:
    """Generate a unique, valid Telegram sticker-set short name."""

    username = bot_username.removeprefix("@").lower()

    if not username or not re.fullmatch(r"[a-z0-9_]+", username):
        raise ValueError("The bot username is invalid.")

    # Telegram requires this suffix for bot-created sticker sets
    suffix = f"_{user_id}_by_{username}"
    available_length = 64 - len(suffix)

    if available_length < 1:
        raise ValueError("The generated Telegram short name would be too long.")

    slug = pack_name[:available_length].rstrip("_") or "p"
    short_name = f"{slug}{suffix}"

    if len(short_name) > 64:  # keep long names within Telegram's 64-character limit
        raise ValueError("The Telegram short name would be too long.")

    return short_name


def create_pack(user_id: int, pack_title: str, bot_username: str,) -> dict:
    """Create a named pack belonging to a particular user, automatically suffixing duplicate slugs."""

    pack_title = pack_title.strip()

    if not pack_title:
        raise ValueError("The pack title cannot be empty.")

    if len(pack_title) > 64:
        raise ValueError(
            "The pack title cannot exceed 64 characters."
        )

    register_user(user_id)
    base_name = normalize_pack_name(pack_title)

    with closing(get_connection()) as connection:
        for number in range(1, 10000):
            candidate = (
                base_name if number == 1
                else f"{base_name[:26].rstrip('_')}{number}"
            )

            exists = connection.execute(
                """
                SELECT 1 FROM packs
                WHERE user_id = ? AND pack_name = ?
                """,
                (user_id, candidate),
            ).fetchone()

            if exists:
                continue

            short_name = generate_telegram_short_name(candidate, user_id, bot_username,)

            try:
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
                    (user_id, candidate, pack_title, short_name),
                )

                connection.commit()

                return {
                    "id": cursor.lastrowid,
                    "user_id": user_id,
                    "pack_name": candidate,
                    "pack_title": pack_title,
                    "telegram_short_name": short_name,
                }


            except sqlite3.IntegrityError:
                continue

    raise ValueError("I couldn't generate a unique name for this pack.")


def list_packs(user_id: int) -> list[dict]:
    """Return all packs owned by the specified user ."""

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


def get_pack_by_id(user_id: int, pack_id: int):
    """Find a pack only if it belongs to the specified user."""

    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT id, user_id, pack_name, pack_title, telegram_short_name
            FROM packs
            WHERE id = ? AND user_id = ?
            """,
            (pack_id, user_id),
        ).fetchone()

        return dict(row) if row else None


if __name__ == "__main__":
    initialize_database()
    print(f"Database initialized: {DATABASE_FILE}")
