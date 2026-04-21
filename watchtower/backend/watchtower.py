"""
AlohaAI Emergency Watchtower - Core Logic
Ported from the Kivy desktop app for use in the FastAPI web backend.
"""

import os
import re
import requests
import anthropic
from typing import Optional, List, Dict, Callable
from dotenv import load_dotenv

load_dotenv()


class EmergencyReportGenerator:
    """Scrapes Facebook comments and generates emergency reports using Claude AI."""

    def __init__(self):
        self.fb_access_token = os.getenv("FACEBOOK_ACCESS_TOKEN")
        self.group_id = os.getenv("HAWAII_TRACKER_GROUP_ID")
        self.fb_base_url = "https://graph.facebook.com/v21.0"

        self.claude_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.claude_client = (
            anthropic.Anthropic(api_key=self.claude_api_key)
            if self.claude_api_key
            else None
        )

        self.validation_errors: List[str] = []
        if not self.fb_access_token:
            self.validation_errors.append("FACEBOOK_ACCESS_TOKEN not found in .env")
        if not self.group_id:
            self.validation_errors.append("HAWAII_TRACKER_GROUP_ID not found in .env")
        if not self.claude_api_key:
            self.validation_errors.append("ANTHROPIC_API_KEY not found in .env")

    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0

    # ── URL Parsing ───────────────────────────────────────────────────────────

    def extract_post_id_from_url(self, url: str) -> Optional[str]:
        """Extract post ID from a Facebook URL."""
        clean_url = url.split("?")[0].split("#")[0]
        post_match = re.search(r"/(?:permalink|posts)/(\d+)", clean_url)
        if post_match:
            return post_match.group(1)
        numbers = re.findall(r"\d{15,}", clean_url)
        if numbers:
            return numbers[-1]
        return None

    # ── Facebook Scraping ─────────────────────────────────────────────────────

    def scrape_comments(
        self,
        post_id: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> List[Dict]:
        """Fetch all comments from a Facebook post via Graph API pagination."""
        all_comments: List[Dict] = []
        url = f"{self.fb_base_url}/{post_id}/comments"
        params = {
            "fields": "message,created_time",
            "limit": 100,
            "access_token": self.fb_access_token,
        }

        try:
            while True:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                comments = data.get("data", [])
                for comment in comments:
                    all_comments.append(
                        {
                            "timestamp": comment.get("created_time", ""),
                            "comment": comment.get("message", ""),
                        }
                    )

                if progress_callback:
                    progress_callback(f"Retrieved {len(all_comments)} comments…")

                paging = data.get("paging", {})
                next_url = paging.get("next")
                if not next_url:
                    break

                url = next_url
                params = {}

        except requests.exceptions.HTTPError as e:
            if progress_callback:
                error_msg = str(e)
                if hasattr(e, "response") and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get("error", {}).get("message", str(e))
                    except Exception:
                        pass
                progress_callback(f"Facebook API error: {error_msg}")

        except requests.exceptions.RequestException as e:
            if progress_callback:
                progress_callback(f"Network error: {str(e)}")

        return all_comments

    # ── Text Chunking ─────────────────────────────────────────────────────────

    def split_text(self, text: str, max_chars: int = 15000) -> List[str]:
        """Split text into chunks that fit within max_chars."""
        chunks: List[str] = []
        current_chunk = ""
        for line in text.split("\n"):
            # Guard against a single line exceeding max_chars
            if len(line) >= max_chars:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                # Hard-split the oversized line
                for i in range(0, len(line), max_chars - 1):
                    chunks.append(line[i : i + max_chars - 1] + "\n")
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

    # ── Claude API ────────────────────────────────────────────────────────────

    def call_claude(self, prompt: str, max_tokens: int = 4096) -> Optional[str]:
        """Make a call to Claude API."""
        try:
            message = self.claude_client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except Exception as e:
            raise Exception(f"Claude API error: {str(e)}")

    # ── Report Generation ─────────────────────────────────────────────────────

    def generate_report(
        self,
        comments: List[Dict],
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Optional[str]:
        """Two-stage map-reduce report generation via Claude AI."""
        if not comments:
            return None

        # Format comments into a single text block
        formatted_comments = ""
        for entry in comments:
            timestamp = entry.get("timestamp", "No timestamp")
            comment = entry.get("comment", "")
            formatted_comments += f"[{timestamp}] {comment}\n\n"

        chunks = self.split_text(formatted_comments, max_chars=15000)
        num_chunks = len(chunks)

        if progress_callback:
            progress_callback(f"Processing {num_chunks} chunk(s) of comments…")

        # ── Stage 1: Organize by district ─────────────────────────────────
        map_prompt_template = """
<task>Organize Facebook comments by geographic district</task>

<context>
<topic>Natural Disaster / Emergency Events</topic>
<source>Facebook Group comments about emergencies on Hawaii Island</source>
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
1. Organize each comment by district based on location mentioned
2. Create a separate list of urgent comments that show:
   - Direct impact on human safety
   - Impact on essential services (roads, power, water)
   - Active emergencies requiring immediate attention
3. EXCLUDE routine maintenance, scheduled work, or non-emergency information
</instructions>

<output_format>
Return organized data in simple text format by district, followed by urgent items list.
</output_format>
"""

        organized_chunks: List[str] = []
        for i, chunk in enumerate(chunks):
            if progress_callback and num_chunks > 1:
                progress_callback(f"Analyzing chunk {i + 1} of {num_chunks}…")
            prompt = map_prompt_template.format(text=chunk)
            result = self.call_claude(prompt)
            if result:
                organized_chunks.append(result)

        combined_text = "\n\n".join(organized_chunks)

        # ── Stage 2: Write final report ───────────────────────────────────
        combine_prompt = f"""
<task>Create a professional Facebook post for emergency updates</task>

<audience>
<primary>Hawaii County Civil Defense</primary>
<secondary>Emergency Operations Center</secondary>
<platform>Facebook</platform>
</audience>

<input_data>
{combined_text}
</input_data>

<strict_requirements>
<requirement>Use professional tone appropriate for civil defense</requirement>
<requirement>Include ONLY areas with actual incidents or emergencies</requirement>
<requirement>EXCLUDE districts with no reported issues</requirement>
<requirement>Keep post concise and readable</requirement>
<requirement>Use bullet points or short paragraphs</requirement>
<requirement>Start with a brief situation overview</requirement>
<requirement>ONLY include active emergencies, NOT routine activities</requirement>
</strict_requirements>

<format_structure>
<opening>Brief timestamp and situation summary (1-2 sentences)</opening>
<affected_areas>List ONLY districts with active incidents (bullet points)</affected_areas>
<priority_items>Highlight immediate safety concerns if any exist</priority_items>
<closing>Brief closing statement with contact info reminder</closing>
</format_structure>

<exclusions>
- Do NOT include districts with no incidents
- Do NOT include "All systems normal" statements
- Do NOT include routine maintenance unless it affects emergency access
- Do NOT use formal report headers like "PRIORITY 1" or numbered sections
- Do NOT create a lengthy formatted report structure
</exclusions>

<example_tone>
"We're monitoring [number] active situations across Hawaii Island. [Brief description]. Stay safe and check back for updates."
</example_tone>
"""

        if progress_callback:
            progress_callback("Generating final emergency report…")

        output = self.call_claude(combine_prompt, max_tokens=8000)
        return output
