# dette er koden som laster opp all data om alle poller fra hovedprogrammet, over på en sqlite database lagret lokalt.

import os
import sqlite3
from typing import Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "polls.db")

#starter databasen
def init_db() -> None:
    """Create the polls table if it does not already exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS polls (
                id TEXT PRIMARY KEY,
                caption TEXT NOT NULL,
                score_a INTEGER NOT NULL DEFAULT 0,
                score_b INTEGER NOT NULL DEFAULT 0,
                score_meh INTEGER NOT NULL DEFAULT 0,
                image_path TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        cursor = conn.execute("PRAGMA table_info(polls)")
        columns = {row[1] for row in cursor.fetchall()}
        if "image_path" not in columns:
            conn.execute("ALTER TABLE polls ADD COLUMN image_path TEXT")
            conn.commit()

#lagrer pollen som en helhet. og legger den inn i table som de andre 
def save_poll_record(poll: Dict[str, int | str]) -> None:
    """Insert or update a poll row."""
    poll_id = poll.get("id")
    if not poll_id:
        return

    caption = poll.get("caption") or ""
    score_a = int(poll.get("score_a", 0))
    score_b = int(poll.get("score_b", 0))
    score_meh = int(poll.get("score_meh", 0))
    image_path = poll.get("image_path")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO polls (id, caption, score_a, score_b, score_meh, image_path, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                caption=excluded.caption,
                score_a=excluded.score_a,
                score_b=excluded.score_b,
                score_meh=excluded.score_meh,
                image_path=excluded.image_path,
                updated_at=CURRENT_TIMESTAMP
            """,
            (poll_id, caption, score_a, score_b, score_meh, image_path),
        )
        conn.commit()

#henter ut en spesifik poll med poll_id
def fetch_poll(poll_id: str) -> Optional[Dict[str, int | str]]:
    """Return a single poll by id."""
    if not poll_id:
        return None

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT id, caption, score_a, score_b, score_meh, image_path FROM polls WHERE id = ?",
            (poll_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

#henter ut alle pollene som har blitt lagret hittil
def fetch_all_polls() -> List[Dict[str, int | str]]:
    """Return all polls ordered by last update."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT id, caption, score_a, score_b, score_meh, image_path FROM polls ORDER BY updated_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

#bildehåndtering. For å laste opp bilde (link til hvor bildet ligger lagret) til databasen og linke det opp til riktig poll
def update_image_path(poll_id: str, image_path: Optional[str]) -> None:
    if not poll_id:
        return
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE polls
            SET image_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (image_path, poll_id),
        )
        conn.commit()

#mulighet for å hente poll etter hvilken caption den har. dette er hovedsakelig for å kunne endre navnet på poller.
def fetch_poll_by_caption(caption: str) -> Optional[Dict[str, int | str]]:
    """Return the newest poll matching the given caption (case-insensitive)."""
    if not caption:
        return None
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT id, caption, score_a, score_b, score_meh, image_path
            FROM polls
            WHERE caption = ?
            COLLATE NOCASE
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (caption,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
