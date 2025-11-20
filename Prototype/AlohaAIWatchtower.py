"""
AlohaAI Emergency Watchtower - Integrated GUI Application
Combines Facebook scraping, AI analysis, and GUI interface with markdown rendering
"""

import sys
import os

# Fix for PyInstaller on Windows
if hasattr(sys, '_MEIPASS'):
    # Running as compiled executable
    os.environ['KIVY_NO_CONSOLELOG'] = '1'
    # Add the temporary directory to the path
    os.chdir(sys._MEIPASS)

import multiprocessing
# Required for Windows executable
multiprocessing.freeze_support()

import kivy
kivy.require('2.0.0')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.uix.popup import Popup
from kivy.core.window import Window

import requests
import anthropic
import json
import re
import threading
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, List, Dict

# Load environment variables
# Handle both development and executable environments
if hasattr(sys, '_MEIPASS'):
    # Running as executable - look for .env in the same directory as the exe
    env_path = Path(sys.executable).parent / '.env'
else:
    # Running as script - look for .env in current directory
    env_path = Path('.env')

if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()  # Try default locations


class MarkdownLabel(Label):
    """Custom label that renders basic markdown formatting"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.markup = True

    def set_markdown_text(self, md_text):
        """Convert markdown to Kivy markup"""
        # Convert markdown to Kivy markup
        text = md_text

        # Headers (## Header -> [b][size=18sp]Header[/size][/b])
        text = re.sub(r'^### (.+)$', r'[b][size=16sp]\1[/size][/b]', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'[b][size=18sp]\1[/size][/b]', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'[b][size=20sp]\1[/size][/b]', text, flags=re.MULTILINE)

        # Bold (**text** -> [b]text[/b])
        text = re.sub(r'\*\*(.+?)\*\*', r'[b]\1[/b]', text)

        # Italic (*text* -> [i]text[/i])
        text = re.sub(r'\*(.+?)\*', r'[i]\1[/i]', text)

        # Bullet points (- item -> • item)
        text = re.sub(r'^- (.+)$', r'  • \1', text, flags=re.MULTILINE)
        text = re.sub(r'^\* (.+)$', r'  • \1', text, flags=re.MULTILINE)

        # Highlight urgent/priority items in red
        text = re.sub(r'(urgent|priority|emergency|critical)', r'[color=#FF3333]\1[/color]', text, flags=re.IGNORECASE)

        self.text = text


class EmergencyReportGenerator:
    """Backend: Scrapes Facebook comments and generates emergency reports using Claude AI"""

    def __init__(self):
        # Facebook Graph API setup
        self.fb_access_token = os.getenv('FACEBOOK_ACCESS_TOKEN')
        self.group_id = os.getenv('HAWAII_TRACKER_GROUP_ID')
        self.fb_base_url = 'https://graph.facebook.com/v21.0'

        # Claude AI setup
        self.claude_api_key = os.getenv('ANTHROPIC_API_KEY')
        self.claude_client = anthropic.Anthropic(api_key=self.claude_api_key) if self.claude_api_key else None

        # Validate credentials
        self.validation_errors = []
        if not self.fb_access_token:
            self.validation_errors.append("FACEBOOK_ACCESS_TOKEN not found in .env file")
        if not self.group_id:
            self.validation_errors.append("HAWAII_TRACKER_GROUP_ID not found in .env file")
        if not self.claude_api_key:
            self.validation_errors.append("ANTHROPIC_API_KEY not found in .env file")

    def is_valid(self):
        """Check if all credentials are available"""
        return len(self.validation_errors) == 0

    def extract_post_id_from_url(self, url: str) -> Optional[str]:
        """Extract post ID from Facebook URL"""
        clean_url = url.split('?')[0].split('#')[0]
        post_match = re.search(r'/(?:permalink|posts)/(\d+)', clean_url)
        if post_match:
            return post_match.group(1)
        numbers = re.findall(r'\d{15,}', clean_url)
        if numbers:
            return numbers[-1]
        return None

    def scrape_comments(self, post_id: str, progress_callback=None) -> List[Dict]:
        """Fetch all comments from a Facebook post"""
        all_comments = []
        url = f'{self.fb_base_url}/{post_id}/comments'
        params = {
            'fields': 'message,created_time',
            'limit': 100,
            'access_token': self.fb_access_token
        }

        page_count = 0

        try:
            while True:
                page_count += 1
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                comments = data.get('data', [])
                for comment in comments:
                    all_comments.append({
                        'timestamp': comment.get('created_time', ''),
                        'comment': comment.get('message', '')
                    })

                if progress_callback:
                    progress_callback(f"Retrieved {len(all_comments)} comments...")

                paging = data.get('paging', {})
                next_url = paging.get('next')
                if not next_url:
                    break

                url = next_url
                params = {}

            return all_comments

        except requests.exceptions.HTTPError as e:
            if progress_callback:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('error', {}).get('message', str(e))
                    except:
                        pass
                progress_callback(f"ERROR: {error_msg}")
            return all_comments

    def split_text(self, text: str, max_chars: int = 15000) -> List[str]:
        """Split text into chunks for Claude processing"""
        chunks = []
        current_chunk = ""
        lines = text.split('\n')
        for line in lines:
            if len(current_chunk) + len(line) < max_chars:
                current_chunk += line + '\n'
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line + '\n'
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    def call_claude(self, prompt: str, max_tokens: int = 4096) -> Optional[str]:
        """Make a call to Claude API"""
        try:
            message = self.claude_client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except Exception as e:
            raise Exception(f"Claude API error: {str(e)}")

    def generate_report(self, comments: List[Dict], progress_callback=None) -> Optional[str]:
        """Generate emergency report from comments using Claude AI"""
        if not comments:
            return None

        formatted_comments = ""
        for entry in comments:
            timestamp = entry.get("timestamp", "No timestamp")
            comment = entry.get("comment", "")
            formatted_comments += f"[{timestamp}] {comment}\n\n"

        chunks = self.split_text(formatted_comments, max_chars=15000)
        num_chunks = len(chunks)

        if progress_callback:
            progress_callback(f"Analyzing {num_chunks} chunk(s) of comments...")

        map_prompt_template = """
<task>Organize Facebook comments by geographic district</task>

<context>
<topic>Natural Disaster</topic>
<source>Facebook Group comments about natural disasters on Hawaii Island</source>
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
Return organized data in a simple text format by district, followed by urgent items list.
</output_format>
"""

        organized_chunks = []
        for i, chunk in enumerate(chunks):
            if progress_callback and num_chunks > 1:
                progress_callback(f"Processing chunk {i + 1}/{num_chunks}...")
            map_prompt = map_prompt_template.format(text=chunk)
            result = self.call_claude(map_prompt)
            if result:
                organized_chunks.append(result)

        combined_text = "\n\n".join(organized_chunks)

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
<requirement>Keep post concise</requirement>
<requirement>Use bullet points or short paragraphs for readability</requirement>
<requirement>Start with brief situation overview</requirement>
<requirement>ONLY include information about active emergencies, NOT routine activities</requirement>
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
            progress_callback("Generating final report...")

        output = self.call_claude(combine_prompt, max_tokens=8000)
        return output


class WatchtowerGUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 10
        self.spacing = 10

        # HVERI color scheme
        from kivy.graphics import Color, Rectangle
        with self.canvas.before:
            Color(0.12, 0.12, 0.12, 1)
            self.bg_rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)

        # Initialize backend
        self.generator = EmergencyReportGenerator()
        self.current_report = None
        self.run_thread = None

        # Set output directory based on executable or script mode
        if hasattr(sys, '_MEIPASS'):
            # Running as executable - save reports next to the exe
            self.output_dir = Path(sys.executable).parent / 'watchtower_reports'
        else:
            # Running as script
            self.output_dir = Path('watchtower_reports')

        self.output_dir.mkdir(exist_ok=True)

        # Build UI
        self.build_ui()

        # Check credentials on startup
        if not self.generator.is_valid():
            Clock.schedule_once(lambda dt: self.show_error_popup(
                "Configuration Error",
                "Missing environment variables:\n\n" + "\n".join(self.generator.validation_errors) +
                "\n\nPlease ensure your .env file contains:\n" +
                "- FACEBOOK_ACCESS_TOKEN\n" +
                "- HAWAII_TRACKER_GROUP_ID\n" +
                "- ANTHROPIC_API_KEY"
            ), 1)

    def _update_rect(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size

    def build_ui(self):
        # Header
        header = Label(
            text='AlohaAI Emergency Watchtower',
            size_hint_y=None,
            height=60,
            bold=True,
            font_size='20sp',
            color=(0.9, 0.1, 0.1, 1)
        )
        self.add_widget(header)

        # Input section
        input_section = self.build_input_section()
        self.add_widget(input_section)

        # Control section
        control_section = self.build_control_section()
        self.add_widget(control_section)

        # Status section
        status_section = self.build_status_section()
        self.add_widget(status_section)

        # Output section (Markdown-rendered report)
        output_section = self.build_output_section()
        self.add_widget(output_section)

    def build_input_section(self):
        layout = BoxLayout(orientation='vertical', size_hint_y=None, height=100, spacing=10)

        link_label = Label(
            text='Facebook Post URL:',
            size_hint_y=None,
            height=30,
            font_size='16sp',
            halign='left',
            valign='middle',
            color=(1, 1, 1, 1)
        )
        link_label.bind(size=link_label.setter('text_size'))
        layout.add_widget(link_label)

        self.fb_link_input = TextInput(
            hint_text='https://facebook.com/groups/hawaiitracker/posts/...',
            size_hint_y=None,
            height=45,
            font_size='15sp',
            multiline=False,
            background_color=(0.2, 0.2, 0.2, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(0.9, 0.1, 0.1, 1)
        )
        layout.add_widget(self.fb_link_input)

        return layout

    def build_control_section(self):
        layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=10)

        self.generate_btn = Button(
            text='Generate Report',
            font_size='16sp',
            background_color=(0.9, 0.1, 0.1, 1),
            color=(1, 1, 1, 1),
            background_normal=''
        )
        self.generate_btn.bind(on_press=self.generate_report)

        self.save_btn = Button(
            text='Save Report',
            font_size='16sp',
            background_color=(0.6, 0.05, 0.05, 1),
            color=(1, 1, 1, 1),
            background_normal='',
            disabled=True
        )
        self.save_btn.bind(on_press=self.save_report)

        self.clear_btn = Button(
            text='Clear',
            font_size='16sp',
            background_color=(0.25, 0.25, 0.25, 1),
            color=(1, 1, 1, 1),
            background_normal=''
        )
        self.clear_btn.bind(on_press=self.clear_output)

        layout.add_widget(self.generate_btn)
        layout.add_widget(self.save_btn)
        layout.add_widget(self.clear_btn)

        return layout

    def build_status_section(self):
        layout = BoxLayout(orientation='vertical', size_hint_y=None, height=120, spacing=8)

        status_label = Label(
            text='Status',
            size_hint_y=None,
            height=30,
            bold=True,
            font_size='18sp',
            color=(0.9, 0.1, 0.1, 1)
        )
        layout.add_widget(status_label)

        status_grid = GridLayout(cols=2, size_hint_y=None, height=80, spacing=8)

        label1 = Label(text='Status:', halign='left', font_size='15sp', color=(1, 1, 1, 1))
        label1.bind(size=label1.setter('text_size'))
        status_grid.add_widget(label1)

        self.status_value = Label(text='Ready', halign='left', color=(0.5, 0.5, 0.5, 1), font_size='15sp')
        self.status_value.bind(size=self.status_value.setter('text_size'))
        status_grid.add_widget(self.status_value)

        label2 = Label(text='Comments:', halign='left', font_size='15sp', color=(1, 1, 1, 1))
        label2.bind(size=label2.setter('text_size'))
        status_grid.add_widget(label2)

        self.comment_count_value = Label(text='0', halign='left', font_size='15sp', color=(1, 1, 1, 1))
        self.comment_count_value.bind(size=self.comment_count_value.setter('text_size'))
        status_grid.add_widget(self.comment_count_value)

        layout.add_widget(status_grid)
        return layout

    def build_output_section(self):
        layout = BoxLayout(orientation='vertical', spacing=8)

        output_label = Label(
            text='Emergency Report',
            size_hint_y=None,
            height=35,
            bold=True,
            font_size='18sp',
            color=(0.9, 0.1, 0.1, 1)
        )
        layout.add_widget(output_label)

        # Scrollable output with dark background
        from kivy.graphics import Color, Rectangle
        scroll = ScrollView(do_scroll_x=False)

        output_container = BoxLayout()
        with output_container.canvas.before:
            Color(0.15, 0.15, 0.15, 1)
            output_container.bg_rect = Rectangle(size=output_container.size, pos=output_container.pos)
        output_container.bind(size=lambda obj, val: setattr(obj.bg_rect, 'size', val),
                            pos=lambda obj, val: setattr(obj.bg_rect, 'pos', val))

        self.output_display = MarkdownLabel(
            text='Enter a Facebook post URL and click "Generate Report" to begin...\n',
            size_hint_y=None,
            halign='left',
            valign='top',
            font_size='14sp',
            padding=(15, 15),
            color=(1, 1, 1, 1)
        )
        self.output_display.bind(texture_size=self.output_display.setter('size'))
        self.output_display.bind(width=lambda *x: self.output_display.setter('text_size')(self.output_display, (self.output_display.width - 30, None)))

        output_container.add_widget(self.output_display)
        scroll.add_widget(output_container)
        layout.add_widget(scroll)

        return layout

    def update_status(self, status, color):
        """Update the status indicator"""
        self.status_value.text = status
        self.status_value.color = color

    def log_progress(self, message):
        """Add progress message to output"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        current_text = self.output_display.text
        self.output_display.text = f'{current_text}[{timestamp}] {message}\n'

    def generate_report(self, instance):
        fb_link = self.fb_link_input.text.strip()
        if not fb_link:
            self.show_error_popup('Error', 'Please enter a Facebook post URL')
            return

        if not self.generator.is_valid():
            self.show_error_popup('Configuration Error',
                'Missing API credentials. Check your .env file.')
            return

        if self.run_thread and self.run_thread.is_alive():
            self.show_error_popup('Busy', 'A report is already being generated. Please wait...')
            return

        # Clear previous output
        self.output_display.text = ''
        self.current_report = None
        self.save_btn.disabled = True

        # Disable generate button
        self.generate_btn.disabled = True

        # Start processing in background thread
        self.run_thread = threading.Thread(target=self.run_analysis, args=(fb_link,))
        self.run_thread.daemon = True
        self.run_thread.start()

    def run_analysis(self, post_url):
        """Background thread for analysis"""
        try:
            Clock.schedule_once(lambda dt: self.update_status('Extracting post ID...', (0.9, 0.5, 0.1, 1)), 0)

            # Extract post ID
            post_id = self.generator.extract_post_id_from_url(post_url)
            if not post_id:
                Clock.schedule_once(lambda dt: self.log_progress('ERROR: Could not extract post ID from URL'), 0)
                Clock.schedule_once(lambda dt: self.update_status('Error', (1, 0, 0, 1)), 0)
                Clock.schedule_once(lambda dt: setattr(self.generate_btn, 'disabled', False), 0)
                return

            full_post_id = f"{self.generator.group_id}_{post_id}"
            Clock.schedule_once(lambda dt: self.log_progress(f'Post ID: {full_post_id}'), 0)

            # Scrape comments
            Clock.schedule_once(lambda dt: self.update_status('Scraping comments...', (0.9, 0.5, 0.1, 1)), 0)

            def progress_callback(msg):
                Clock.schedule_once(lambda dt: self.log_progress(msg), 0)

            comments = self.generator.scrape_comments(full_post_id, progress_callback)

            if not comments:
                Clock.schedule_once(lambda dt: self.log_progress('ERROR: No comments retrieved'), 0)
                Clock.schedule_once(lambda dt: self.update_status('Error', (1, 0, 0, 1)), 0)
                Clock.schedule_once(lambda dt: setattr(self.generate_btn, 'disabled', False), 0)
                return

            Clock.schedule_once(lambda dt: setattr(self.comment_count_value, 'text', str(len(comments))), 0)
            Clock.schedule_once(lambda dt: self.log_progress(f'Total comments retrieved: {len(comments)}'), 0)
            Clock.schedule_once(lambda dt: self.log_progress(''), 0)

            # Generate report
            Clock.schedule_once(lambda dt: self.update_status('Analyzing with AI...', (0.9, 0.5, 0.1, 1)), 0)

            report = self.generator.generate_report(comments, progress_callback)

            if not report:
                Clock.schedule_once(lambda dt: self.log_progress('ERROR: Failed to generate report'), 0)
                Clock.schedule_once(lambda dt: self.update_status('Error', (1, 0, 0, 1)), 0)
                Clock.schedule_once(lambda dt: setattr(self.generate_btn, 'disabled', False), 0)
                return

            # Display report with markdown rendering
            self.current_report = report
            Clock.schedule_once(lambda dt: self.display_report(report), 0)
            Clock.schedule_once(lambda dt: self.update_status('Complete', (0.2, 0.8, 0.2, 1)), 0)
            Clock.schedule_once(lambda dt: setattr(self.save_btn, 'disabled', False), 0)
            Clock.schedule_once(lambda dt: setattr(self.generate_btn, 'disabled', False), 0)

        except Exception as e:
            error_msg = str(e)
            Clock.schedule_once(lambda dt: self.log_progress(f'ERROR: {error_msg}'), 0)
            Clock.schedule_once(lambda dt: self.update_status('Error', (1, 0, 0, 1)), 0)
            Clock.schedule_once(lambda dt: setattr(self.generate_btn, 'disabled', False), 0)

    def display_report(self, report):
        """Display the markdown-formatted report"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Clear and show formatted report
        self.output_display.text = ''
        header_text = f'[b][size=18sp]Emergency Report[/size][/b]\n'
        header_text += f'[color=#888888]Generated: {timestamp}[/color]\n'
        header_text += '[color=#888888]' + '=' * 60 + '[/color]\n\n'

        self.output_display.set_markdown_text(header_text + report)

    def save_report(self, instance):
        """Save the current report to file"""
        if not self.current_report:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = self.output_dir / f"emergency_report_{file_timestamp}.txt"

        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(f"Generated: {timestamp}\n")
                f.write("=" * 80 + "\n\n")
                f.write(self.current_report.strip())

            self.show_popup('Report Saved', f'Report saved to:\n{output_filename}')
        except Exception as e:
            self.show_error_popup('Save Error', f'Failed to save report:\n{str(e)}')

    def clear_output(self, instance):
        """Clear the output display"""
        self.output_display.text = 'Enter a Facebook post URL and click "Generate Report" to begin...\n'
        self.current_report = None
        self.save_btn.disabled = True
        self.comment_count_value.text = '0'
        self.update_status('Ready', (0.5, 0.5, 0.5, 1))

    def show_popup(self, title, message):
        """Show informational popup"""
        from kivy.graphics import Color, Rectangle
        popup_container = BoxLayout(padding=20)
        with popup_container.canvas.before:
            Color(0.15, 0.15, 0.15, 1)
            popup_container.bg_rect = Rectangle(size=popup_container.size, pos=popup_container.pos)
        popup_container.bind(size=lambda obj, val: setattr(obj.bg_rect, 'size', val),
                           pos=lambda obj, val: setattr(obj.bg_rect, 'pos', val))

        content = Label(
            text=message,
            font_size='15sp',
            color=(1, 1, 1, 1),
            halign='center',
            valign='middle'
        )
        content.bind(size=content.setter('text_size'))
        popup_container.add_widget(content)

        popup = Popup(
            title=title,
            content=popup_container,
            size_hint=(0.7, 0.4),
            title_color=(0.2, 0.8, 0.2, 1),
            separator_color=(0.2, 0.8, 0.2, 1)
        )
        popup.open()

    def show_error_popup(self, title, message):
        """Show error popup"""
        from kivy.graphics import Color, Rectangle
        popup_container = BoxLayout(padding=20)
        with popup_container.canvas.before:
            Color(0.15, 0.15, 0.15, 1)
            popup_container.bg_rect = Rectangle(size=popup_container.size, pos=popup_container.pos)
        popup_container.bind(size=lambda obj, val: setattr(obj.bg_rect, 'size', val),
                           pos=lambda obj, val: setattr(obj.bg_rect, 'pos', val))

        content = Label(
            text=message,
            font_size='15sp',
            color=(1, 1, 1, 1),
            halign='center',
            valign='middle'
        )
        content.bind(size=content.setter('text_size'))
        popup_container.add_widget(content)

        popup = Popup(
            title=title,
            content=popup_container,
            size_hint=(0.7, 0.5),
            title_color=(0.9, 0.1, 0.1, 1),
            separator_color=(0.9, 0.1, 0.1, 1)
        )
        popup.open()


class EmergencyWatchtowerApp(App):
    def build(self):
        self.title = 'AlohaAI Emergency Watchtower'
        Window.size = (900, 700)
        return WatchtowerGUI()


if __name__ == '__main__':
    EmergencyWatchtowerApp().run()