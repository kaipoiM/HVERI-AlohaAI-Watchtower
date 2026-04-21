"""
AlohaAI Emergency Watchtower - Core Logic
Citizen submission storage (SQLite) + Claude AI report generation.
No Facebook / Graph API dependency.
"""

import os
import sqlite3
import anthropic
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Callable
from dotenv import load_dotenv

load_dotenv()

# ── Database path ─────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).parent.parent / "watchtower.db"


# ── Database Manager ──────────────────────────────────────────────────────────

class DatabaseManager:
    """Handles all SQLite operations for submissions and event context."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # rows accessible by column name
        return conn

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    ref_code      TEXT    NOT NULL,
                    incident_type TEXT    NOT NULL,
                    district      TEXT    NOT NULL,
                    location      TEXT,
                    description   TEXT    NOT NULL,
                    severity      TEXT    NOT NULL DEFAULT 'low',
                    evacuation    TEXT,
                    reporter_name TEXT,
                    timestamp     TEXT    NOT NULL,
                    processed     INTEGER NOT NULL DEFAULT 0,
                    mod_status    TEXT    NOT NULL DEFAULT 'pending'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_context (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary    TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    username             TEXT    NOT NULL UNIQUE,
                    email                TEXT    NOT NULL UNIQUE,
                    password_hash        TEXT    NOT NULL,
                    must_change_password INTEGER NOT NULL DEFAULT 1,
                    created_at           TEXT    NOT NULL,
                    last_login           TEXT
                )
            """)
            conn.commit()

    # ── Admin accounts ────────────────────────────────────────────────────────

    def get_admin_by_login(self, login: str) -> Optional[Dict]:
        """Fetch admin by email or username."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM admins WHERE email = ? OR username = ?",
                (login, login),
            ).fetchone()
        return dict(row) if row else None

    def get_admin_by_id(self, admin_id: int) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM admins WHERE id = ?", (admin_id,)
            ).fetchone()
        return dict(row) if row else None

    def create_admin(self, username: str, email: str, password_hash: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO admins (username, email, password_hash, created_at)
                   VALUES (?, ?, ?, ?)""",
                (username, email, password_hash, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        return cursor.lastrowid

    def update_password(self, admin_id: int, password_hash: str, must_change: int = 0):
        with self._connect() as conn:
            conn.execute(
                "UPDATE admins SET password_hash = ?, must_change_password = ? WHERE id = ?",
                (password_hash, must_change, admin_id),
            )
            conn.commit()

    def update_last_login(self, admin_id: int):
        with self._connect() as conn:
            conn.execute(
                "UPDATE admins SET last_login = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), admin_id),
            )
            conn.commit()

    def list_admins(self) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, username, email, must_change_password, created_at, last_login FROM admins"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_admin(self, admin_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM admins WHERE id = ?", (admin_id,))
            conn.commit()
        return cursor.rowcount > 0

    # ── Submissions ───────────────────────────────────────────────────────────

    def insert_submission(self, data: Dict) -> int:
        """Insert a new citizen submission. Returns the new row id."""
        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT INTO submissions
                    (ref_code, incident_type, district, location, description,
                     severity, evacuation, reporter_name, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["ref_code"],
                data["incident_type"],
                data["district"],
                data.get("location") or None,
                data["description"],
                data.get("severity") or "low",
                data.get("evacuation") or None,
                data.get("reporter_name") or None,
                data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            ))
            conn.commit()
            return cursor.lastrowid

    def get_pending(self) -> List[Dict]:
        """Return all unprocessed submissions (processed = 0)."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM submissions
                WHERE processed = 0
                ORDER BY timestamp ASC
            """).fetchall()
        return [dict(r) for r in rows]

    def mark_processed(self, ids: List[int]):
        """Mark a list of submission IDs as processed (processed = 1)."""
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        with self._connect() as conn:
            conn.execute(
                f"UPDATE submissions SET processed = 1 WHERE id IN ({placeholders})",
                ids,
            )
            conn.commit()

    def get_all(self) -> List[Dict]:
        """Return all submissions, newest first (for the admin submissions tab)."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM submissions
                ORDER BY timestamp DESC
            """).fetchall()
        return [dict(r) for r in rows]

    def delete_submission(self, submission_id: int) -> bool:
        """Hard-delete a submission. Returns True if a row was deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM submissions WHERE id = ?", (submission_id,)
            )
            conn.commit()
        return cursor.rowcount > 0

    def get_counts(self) -> Dict:
        """Return pending and total submission counts."""
        with self._connect() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) FROM submissions WHERE processed = 0"
            ).fetchone()[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM submissions"
            ).fetchone()[0]
        return {"pending": pending, "total": total}

    # ── Event Context ─────────────────────────────────────────────────────────

    def get_latest_context(self) -> Optional[str]:
        """Return the most recent event context summary, or None."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT summary FROM event_context
                ORDER BY id DESC LIMIT 1
            """).fetchone()
        return row["summary"] if row else None

    def save_context(self, summary: str):
        """Append a new event context summary."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO event_context (summary, created_at) VALUES (?, ?)",
                (summary, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()


# ── Report Generator ──────────────────────────────────────────────────────────

class EmergencyReportGenerator:
    """Generates emergency reports from citizen submissions using Claude AI."""

    def __init__(self):
        self.claude_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.claude_client = (
            anthropic.Anthropic(api_key=self.claude_api_key)
            if self.claude_api_key
            else None
        )
        self.db = DatabaseManager()

        self.validation_errors: List[str] = []
        if not self.claude_api_key:
            self.validation_errors.append("ANTHROPIC_API_KEY not found in .env")

    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0

    # ── Claude API ────────────────────────────────────────────────────────────

    def call_claude(self, prompt: str, max_tokens: int = 4096) -> Optional[str]:
        """Make a single call to Claude API."""
        try:
            message = self.claude_client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except Exception as e:
            raise Exception(f"Claude API error: {str(e)}")

    # ── Submission Formatting ─────────────────────────────────────────────────

    def format_submissions(self, submissions: List[Dict]) -> str:
        """
        Convert a list of submission dicts into a structured text block
        for the Claude prompt. Groups by district for readability.
        """
        # Group by district
        by_district: Dict[str, List[Dict]] = {}
        for sub in submissions:
            d = sub.get("district", "Unknown")
            by_district.setdefault(d, []).append(sub)

        lines = []
        for district, subs in sorted(by_district.items()):
            lines.append(f"\n=== {district} ===")
            for sub in subs:
                lines.append(f"  REF: {sub.get('ref_code', '—')}")
                lines.append(f"  Type: {sub.get('incident_type', '—')}")
                lines.append(f"  Severity: {sub.get('severity', '—')}")
                lines.append(f"  Location: {sub.get('location') or 'Not specified'}")
                lines.append(f"  Description: {sub.get('description', '—')}")
                evac = sub.get("evacuation")
                if evac:
                    lines.append(f"  Evacuation: {evac}")
                lines.append(f"  Submitted: {sub.get('timestamp', '—')}")
                lines.append("")

        return "\n".join(lines)

    # ── Text Chunking ─────────────────────────────────────────────────────────

    def split_text(self, text: str, max_chars: int = 15000) -> List[str]:
        """Split text into chunks that fit within max_chars."""
        chunks: List[str] = []
        current_chunk = ""
        for line in text.split("\n"):
            if len(line) >= max_chars:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                for i in range(0, len(line), max_chars - 1):
                    chunks.append(line[i: i + max_chars - 1] + "\n")
                continue
            if len(current_chunk) + len(line) + 1 < max_chars:
                current_chunk += line + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line + "\n"
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    # ── Report Generation ─────────────────────────────────────────────────────

    def generate_report(
        self,
        submissions: List[Dict],
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Optional[str]:
        """
        Two-stage map-reduce report generation.

        Stage 1: Organise each chunk of submissions by district and flag urgency.
        Stage 2: Synthesise a final civil-defense briefing from the stage-1 output,
                 injecting prior event context if available.

        After a successful report the processed submissions are marked in the DB
        and a new context summary is saved for use by the next report cycle.
        """
        if not submissions:
            return None

        formatted = self.format_submissions(submissions)
        chunks = self.split_text(formatted, max_chars=15000)
        num_chunks = len(chunks)

        if progress_callback:
            progress_callback(f"Processing {num_chunks} chunk(s) of submissions…")

        # ── Stage 1: Organise by district ─────────────────────────────────
        map_prompt_template = """
<task>Organise citizen emergency submissions by geographic district</task>

<context>
<topic>Natural Disaster / Emergency Events</topic>
<source>Structured citizen reports submitted via AlohaAI Watchtower web form</source>
</context>

<input_data>
{text}
</input_data>

<districts>
<district name="North Kohala">Halaula, Hawi, Kapaau, Puakea Ranch, Mahukona, Kaholena, Kohala Ranch, Upolu, Halawa, Makapala, Niulii, Pulolu</district>
<district name="South Kohala">Kawaihae, Hapuna, Puako, Waikoloa, Waimea, Waikii, Puukapu</district>
<district name="Hamakua">Waipio, Kukuihaele, Ahualoa, Honokaa, Paauhau, Kalopa, Paauilo, Kukuaiau, Niupea</district>
<district name="North Hilo">Ookala, Waipunalei, Laupahoehoe, Papaaloa, Kapehu, Pohakupuka, Ninole, Umauma</district>
<district name="South Hilo">Hakalau, Honomu, Pepeekeo, Onomea, Papaikou, Paukaa, Puueo, Wainaku, Keaukaha, Panaewa, Kaiwiki, Piihonua, Kaumana, Sunrise Ridge, Waiakea Uka</district>
<district name="Puna">Kurtistown, Hawaiian Paradise Park, HPP, Hawaiian Acres, Orchidland, Hawaiian Beaches, Ainaloa, Nanawale Estates, Kapoho, Pohoiki, Leilani Estates, Opihikao, Kehena, Kaimu, Mountain View, Glenwood, Fern Acres, Volcano, Kalapana</district>
<district name="Ka'u">Wood Valley, Pahala, Punaluu, Naalehu, Waiohinu, Ka Lae, Kamaoa, Ocean View, Manuka</district>
<district name="South Kona">Honomalino, Milolii, Papa Bay, Kona, Hookena, Kealia, Honaunau, Keei, Napoopoo, Captain Cook, Kealakekua</district>
<district name="North Kona">Honalo, Keauhou, Alii Heights, Hualalai, Kailua-Kona, Kealakehe, Kaloko, Makalawena, Holulaloa, Kaupulehu, Kukio, Puulani Ranch, Makalei Estates</district>
</districts>

<instructions>
1. List each submission under its correct district.
2. Flag any item as URGENT if it describes:
   - Direct threat to human life or safety
   - Blocked evacuation routes
   - Loss of essential services (power, water, roads) at scale
   - Active and ongoing emergency requiring immediate response
3. Exclude anything that appears to be a test submission or spam.
</instructions>

<output_format>
Plain text, grouped by district. Append an URGENT ITEMS section at the end listing the most critical items across all districts.
</output_format>
"""

        organized_chunks: List[str] = []
        for i, chunk in enumerate(chunks):
            if progress_callback and num_chunks > 1:
                progress_callback(f"Analysing chunk {i + 1} of {num_chunks}…")
            prompt = map_prompt_template.format(text=chunk)
            result = self.call_claude(prompt)
            if result:
                organized_chunks.append(result)

        combined_text = "\n\n".join(organized_chunks)

        # ── Inject prior event context if available ────────────────────────
        prior_context = self.db.get_latest_context()
        prior_context_block = prior_context if prior_context else "No previous reports this event."

        # ── Stage 2: Final report ─────────────────────────────────────────
        combine_prompt = (
            "You are summarising citizen-submitted emergency reports for administrators "
            "and first responders during a natural disaster on Hawaii Island.\n\n"
            "Your goal is to produce a clear, scannable real-time summary that lets readers "
            "instantly see what is happening by district and identify the highest-priority "
            "items that need immediate attention.\n\n"
            "Write for a mixed audience — civil defense coordinators, emergency responders, "
            "and community administrators. Assume they are busy and need to act fast.\n\n"
            "**What has already been reported (previous cycles):**\n"
            f"{prior_context_block}\n"
            "Use this only for situational awareness. Do not repeat it in the new report "
            "unless conditions in those areas have changed or worsened.\n\n"
            "**New submissions this cycle:**\n"
            f"{combined_text}\n\n"
            "**Format:**\n"
            "- Open with 1-2 sentences: what is happening, how many new reports, when\n"
            "- If any high-severity or evacuation reports exist, list them first under **\u26a0 Priority Items**\n"
            "- Then list affected districts as headers, with bullet points per incident "
            "(type, location if known, brief description)\n"
            "- Skip districts with no new reports entirely\n"
            "- End with a one-line count: e.g. *12 reports processed — 3 high severity, 2 evacuation notices*\n\n"
            "Keep the language plain and direct. No bureaucratic phrasing. No filler. "
            "If something is urgent, say so clearly."
        )

        if progress_callback:
            progress_callback("Generating final emergency report…")

        report = self.call_claude(combine_prompt, max_tokens=8000)
        if not report:
            return None

        # ── Mark submissions as processed ─────────────────────────────────
        processed_ids = [s["id"] for s in submissions]
        self.db.mark_processed(processed_ids)

        # ── Generate and save updated context summary ──────────────────────
        context_prompt = f"""
Summarise the following emergency report into a compact paragraph (3-5 sentences max)
suitable for use as prior context in the next report cycle. Focus on: which districts
were affected, what types of incidents occurred, and any ongoing situations that
coordinators should remain aware of.

Report:
{report}
"""
        if progress_callback:
            progress_callback("Saving event context summary…")
        context_summary = self.call_claude(context_prompt, max_tokens=512)
        if context_summary:
            self.db.save_context(context_summary)

        return report
