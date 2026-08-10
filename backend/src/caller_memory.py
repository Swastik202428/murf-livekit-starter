import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DB_FILE = (
    Path(__file__).resolve().parents[1]
    / "caller_memory.db"
)


# ============================================================
# TIME
# ============================================================

def _now_iso() -> str:
    """Return current UTC time as ISO formatted string."""
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db() -> sqlite3.Connection:
    """
    Initialize the SQLite database.

    The database stores limited, structured caller memory.
    """

    DB_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS callers (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            language_preference TEXT,
            facts TEXT,
            last_interaction TEXT
        )
        """
    )

    conn.commit()

    return conn


# ============================================================
# FACT HELPERS
# ============================================================

def _load_facts(
    facts_text: str | None,
) -> dict[str, str]:
    """
    Convert stored JSON facts into a Python dictionary.
    """

    if not facts_text:
        return {}

    try:
        data = json.loads(facts_text)

        if isinstance(data, dict):
            return {
                str(key): str(value)
                for key, value in data.items()
            }

        return {}

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return {}


def _serialize_facts(
    facts: dict[str, str] | None,
) -> str:
    """
    Convert facts dictionary into JSON.

    ensure_ascii=False keeps Hindi and other Unicode
    characters readable inside SQLite.
    """

    return json.dumps(
        facts or {},
        ensure_ascii=False,
    )


# ============================================================
# DATABASE ROW -> PYTHON RECORD
# ============================================================

def _row_to_record(
    row: sqlite3.Row,
) -> dict[str, Any]:
    """
    Convert a SQLite row into a normal Python dictionary.
    """

    return {
        "user_id": row["user_id"],
        "name": row["name"] or "",
        "language_preference": (
            row["language_preference"] or ""
        ),
        "facts": _load_facts(
            row["facts"]
        ),
        "last_interaction": (
            row["last_interaction"] or ""
        ),
    }


# ============================================================
# LOOKUP CALLER
# ============================================================

def lookup_caller(
    conn: sqlite3.Connection,
    user_id: str,
) -> dict[str, Any] | None:
    """
    Retrieve saved memory for a caller.

    Returns None when no memory exists.
    """

    if not user_id:
        return None

    row = conn.execute(
        """
        SELECT
            user_id,
            name,
            language_preference,
            facts,
            last_interaction
        FROM callers
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    if row is None:
        return None

    return _row_to_record(row)


# ============================================================
# SAVE CALLER
# ============================================================

def save_caller(
    conn: sqlite3.Connection,
    user_id: str,
    name: str | None = None,
    language_preference: str | None = None,
    facts: dict[str, str] | None = None,
    last_interaction: str | None = None,
) -> dict[str, Any]:
    """
    Save or update structured caller memory.

    Existing facts are preserved and new facts are merged.

    This function does NOT store full conversation transcripts.
    """

    if not user_id:
        raise ValueError(
            "user_id is required to save caller memory"
        )

    existing = lookup_caller(
        conn,
        user_id,
    )

    # ========================================================
    # NEW CALLER
    # ========================================================

    if existing is None:

        existing = {
            "user_id": user_id,
            "name": name or "",
            "language_preference": (
                language_preference or ""
            ),
            "facts": facts or {},
            "last_interaction": (
                last_interaction or _now_iso()
            ),
        }

    # ========================================================
    # EXISTING CALLER
    # ========================================================

    else:

        # Update name only when a new value exists.
        if name:
            existing["name"] = name

        # Update language preference only when supplied.
        if language_preference:
            existing["language_preference"] = (
                language_preference
            )

        # Merge new facts with existing facts.
        if facts:

            existing["facts"] = {
                **existing.get("facts", {}),
                **facts,
            }

        # Always update the last interaction timestamp.
        existing["last_interaction"] = (
            last_interaction or _now_iso()
        )

    # ========================================================
    # SAVE TO SQLITE
    # ========================================================

    conn.execute(
        """
        INSERT OR REPLACE INTO callers (
            user_id,
            name,
            language_preference,
            facts,
            last_interaction
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            existing["user_id"],
            existing["name"],
            existing["language_preference"],
            _serialize_facts(
                existing["facts"]
            ),
            existing["last_interaction"],
        ),
    )

    conn.commit()

    return existing


# ============================================================
# UPDATE MEMORY
# ============================================================

def update_caller_facts(
    conn: sqlite3.Connection,
    user_id: str,
    facts: dict[str, str],
) -> dict[str, Any] | None:
    """
    Add or update specific caller facts.

    This is useful when the agent wants to remember something
    new without changing the caller's name or language.
    """

    if not user_id:
        return None

    if not facts:
        return lookup_caller(
            conn,
            user_id,
        )

    existing = lookup_caller(
        conn,
        user_id,
    )

    if existing is None:
        return save_caller(
            conn,
            user_id=user_id,
            facts=facts,
        )

    merged_facts = {
        **existing.get("facts", {}),
        **facts,
    }

    return save_caller(
        conn,
        user_id=user_id,
        facts=merged_facts,
    )


# ============================================================
# UPDATE LAST INTERACTION
# ============================================================

def update_last_interaction(
    conn: sqlite3.Connection,
    user_id: str,
) -> dict[str, Any] | None:
    """
    Update only the last interaction timestamp.
    """

    if not user_id:
        return None

    existing = lookup_caller(
        conn,
        user_id,
    )

    if existing is None:
        return None

    existing["last_interaction"] = _now_iso()

    conn.execute(
        """
        UPDATE callers
        SET last_interaction = ?
        WHERE user_id = ?
        """,
        (
            existing["last_interaction"],
            user_id,
        ),
    )

    conn.commit()

    return existing


# ============================================================
# DELETE CALLER MEMORY
# ============================================================

def delete_caller(
    conn: sqlite3.Connection,
    user_id: str,
) -> bool:
    """
    Delete all saved memory for a caller.

    Returns True when memory was deleted.
    """

    if not user_id:
        return False

    cursor = conn.execute(
        """
        DELETE FROM callers
        WHERE user_id = ?
        """,
        (user_id,),
    )

    conn.commit()

    return cursor.rowcount > 0


# ============================================================
# FORMAT MEMORY FOR THE AGENT
# ============================================================

def format_caller_memory(
    caller: dict[str, Any] | None,
) -> str:
    """
    Convert caller memory into a short readable context
    that can be supplied to the AI agent.
    """

    if not caller:
        return ""

    lines: list[str] = []

    name = caller.get("name")

    if name:
        lines.append(
            f"Caller name: {name}"
        )

    language = caller.get(
        "language_preference"
    )

    if language:
        lines.append(
            f"Preferred language: {language}"
        )

    facts = caller.get("facts") or {}

    if facts:

        for key, value in facts.items():

            if value:
                lines.append(
                    f"{key}: {value}"
                )

    last_interaction = caller.get(
        "last_interaction"
    )

    if last_interaction:
        lines.append(
            f"Last interaction: {last_interaction}"
        )

    return "\n".join(lines)
