"""Session Manager — create, validate, refresh, and invalidate user sessions.

Architecture
────────────
Tokens are random URL-safe strings stored in MySQL `user_sessions`.
The browser persists the token in the URL query param `_t` so it survives
page refreshes. Every page load validates the token server-side — the client
is never trusted for role or identity, only for presenting the token.

Lifetime rules
──────────────
  Default session : SESSION_TTL_HOURS hours from creation
  Remember Me     : REMEMBER_ME_DAYS days from creation
  Inactivity gate : INACTIVITY_HOURS hours without any page load
                    (only enforced for non-remember-me sessions)
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional

SESSION_TTL_HOURS  = 8    # hours — standard session
REMEMBER_ME_DAYS   = 30   # days  — remember-me session
INACTIVITY_HOURS   = 2    # hours — auto-expire if no activity (standard only)
CLEANUP_BATCH      = 500  # max rows to delete per cleanup call


class SessionManager:
    """Handles all session lifecycle operations against the MySQL backend."""

    def __init__(self, db_manager) -> None:
        self._db = db_manager

    # ── Creation ─────────────────────────────────────────────────────────────

    def create_session(self, user_id: str, remember_me: bool = False) -> str:
        """Generate a new token, persist it, and return it.

        Args:
            user_id:     The authenticated user's ID.
            remember_me: If True, token lives for REMEMBER_ME_DAYS; otherwise SESSION_TTL_HOURS.

        Returns:
            A URL-safe opaque token string.
        """
        token = secrets.token_urlsafe(32)
        if remember_me:
            expires_at = datetime.now() + timedelta(days=REMEMBER_ME_DAYS)
        else:
            expires_at = datetime.now() + timedelta(hours=SESSION_TTL_HOURS)

        self._db._execute(
            """INSERT INTO user_sessions (token, user_id, expires_at, remember_me)
               VALUES (%s, %s, %s, %s)""",
            (token, user_id, expires_at, remember_me),
        )
        return token

    # ── Validation ───────────────────────────────────────────────────────────

    def validate_session(self, token: str) -> Optional[Dict]:
        """Validate a token and return the user dict, or None if invalid.

        Checks performed:
          1. Token exists in DB
          2. expires_at has not passed
          3. User account is still active
          4. Role field is present
          5. Inactivity gate (standard sessions only)

        Side-effect: updates `last_activity` on success.
        """
        if not token:
            return None

        df = self._db._query_to_df(
            """SELECT u.user_id, u.email, u.name, u.role,
                      s.remember_me, s.expires_at, s.last_activity
               FROM user_sessions s
               JOIN users u ON s.user_id = u.user_id
               WHERE s.token = %s
                 AND s.expires_at > NOW()
                 AND u.status = 'active'""",
            (token,),
        )

        if df.empty:
            return None

        row = df.iloc[0].to_dict()

        # Require role field — corrupted row guard
        if not row.get("role"):
            self.invalidate_session(token)
            return None

        # Inactivity check (standard sessions only)
        if not row.get("remember_me"):
            last_activity = row.get("last_activity")
            if last_activity is not None:
                idle_seconds = (datetime.now() - last_activity).total_seconds()
                if idle_seconds > INACTIVITY_HOURS * 3600:
                    self.invalidate_session(token)
                    return None

        # Refresh last_activity timestamp
        self._db._execute(
            "UPDATE user_sessions SET last_activity = NOW() WHERE token = %s",
            (token,),
        )

        return {
            "user_id":     str(row["user_id"]),
            "email":       str(row["email"]),
            "name":        str(row["name"]),
            "role":        str(row["role"]),
            "remember_me": bool(row.get("remember_me", False)),
        }

    # ── Invalidation ─────────────────────────────────────────────────────────

    def invalidate_session(self, token: str) -> None:
        """Delete a specific session token (logout or forced expiry)."""
        if token:
            self._db._execute(
                "DELETE FROM user_sessions WHERE token = %s", (token,)
            )

    def invalidate_all_for_user(self, user_id: str) -> None:
        """Invalidate every session for a user (e.g., password change, account lock)."""
        self._db._execute(
            "DELETE FROM user_sessions WHERE user_id = %s", (user_id,)
        )

    # ── Maintenance ──────────────────────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """Delete expired sessions. Called periodically by the background worker.

        Returns:
            Number of rows removed.
        """
        df = self._db._query_to_df(
            "SELECT COUNT(*) AS cnt FROM user_sessions WHERE expires_at <= NOW()"
        )
        count = int(df.iloc[0]["cnt"]) if not df.empty else 0
        if count:
            self._db._execute(
                f"DELETE FROM user_sessions WHERE expires_at <= NOW() LIMIT {CLEANUP_BATCH}"
            )
        return count

    # ── Introspection ────────────────────────────────────────────────────────

    def get_active_sessions(self, user_id: str) -> int:
        """Return the count of currently valid sessions for a user."""
        df = self._db._query_to_df(
            "SELECT COUNT(*) AS cnt FROM user_sessions WHERE user_id = %s AND expires_at > NOW()",
            (user_id,),
        )
        return int(df.iloc[0]["cnt"]) if not df.empty else 0
