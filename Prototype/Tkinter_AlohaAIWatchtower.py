"""
AlohaAI Emergency Watchtower - Tkinter GUI Application
Combines Facebook scraping, AI analysis, and GUI interface with markdown rendering
"""

import sys
import os

import multiprocessing
# Required for Windows executable
multiprocessing.freeze_support()

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
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


class MarkdownText(tk.Text):
    """Custom Text widget that renders basic markdown formatting"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        # Configure tags for markdown formatting
        self.tag_configure('h1', font=('TkDefaultFont', 16, 'bold'))
        self.tag_configure('h2', font=('TkDefaultFont', 14, 'bold'))
        self.tag_configure('h3', font=('TkDefaultFont', 12, 'bold'))
        self.tag_configure('bold', font=('TkDefaultFont', 10, 'bold'))
        self.tag_configure('italic', font=('TkDefaultFont', 10, 'italic'))
        self.tag_configure('urgent', foreground='#FF3333')
        self.tag_configure('bullet', lmargin1=20, lmargin2=30)
        self.tag_configure('header_info', foreground='#888888')

    def set_markdown_text(self, md_text):
        """Convert markdown to formatted text with tags"""
        self.config(state='normal')
        self.delete('1.0', tk.END)

        lines = md_text.split('\n')

        for line in lines:
            # Check for headers
            if line.startswith('### '):
                self.insert(tk.END, line[4:] + '\n', 'h3')
            elif line.startswith('## '):
                self.insert(tk.END, line[3:] + '\n', 'h2')
            elif line.startswith('# '):
                self.insert(tk.END, line[2:] + '\n', 'h1')
            elif line.startswith('- ') or line.startswith('* '):
                # Bullet points
                bullet_text = '  \u2022 ' + line[2:]
                self._insert_formatted_line(bullet_text, 'bullet')
            else:
                self._insert_formatted_line(line)

        self.config(state='disabled')

    def _insert_formatted_line(self, line, base_tag=None):
        """Insert a line with inline formatting (bold, italic, urgent)"""
        # Pattern to find **bold**, *italic*, and urgent keywords
        pattern = r'(\*\*.*?\*\*|\*.*?\*|urgent|priority|emergency|critical)'

        parts = re.split(pattern, line, flags=re.IGNORECASE)

        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                # Bold text
                text = part[2:-2]
                tags = ('bold',) if not base_tag else (base_tag, 'bold')
                self.insert(tk.END, text, tags)
            elif part.startswith('*') and part.endswith('*') and len(part) > 2:
                # Italic text
                text = part[1:-1]
                tags = ('italic',) if not base_tag else (base_tag, 'italic')
                self.insert(tk.END, text, tags)
            elif part.lower() in ('urgent', 'priority', 'emergency', 'critical'):
                # Urgent keywords
                tags = ('urgent',) if not base_tag else (base_tag, 'urgent')
                self.insert(tk.END, part, tags)
            else:
                # Regular text
                if base_tag:
                    self.insert(tk.END, part, base_tag)
                else:
                    self.insert(tk.END, part)

        self.insert(tk.END, '\n')

    def append_text(self, text):
        """Append text to the widget"""
        self.config(state='normal')
        self.insert(tk.END, text)
        self.see(tk.END)
        self.config(state='disabled')


class WatchtowerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title('AlohaAI Emergency Watchtower')
        self.root.geometry('900x700')
        self.root.minsize(700, 500)

        # Color scheme (dark theme)
        self.bg_color = '#1f1f1f'
        self.fg_color = '#ffffff'
        self.accent_color = '#e61919'
        self.secondary_bg = '#2a2a2a'
        self.disabled_color = '#666666'
        self.success_color = '#33cc33'
        self.warning_color = '#e68a1a'
        self.error_color = '#ff0000'

        # Configure root window
        self.root.configure(bg=self.bg_color)

        # Configure ttk styles
        self.setup_styles()

        # Initialize backend
        self.generator = EmergencyReportGenerator()
        self.current_report = None
        self.run_thread = None

        # Set output directory based on executable or script mode
        if hasattr(sys, '_MEIPASS'):
            self.output_dir = Path(sys.executable).parent / 'watchtower_reports'
        else:
            self.output_dir = Path('watchtower_reports')

        self.output_dir.mkdir(exist_ok=True)

        # Build UI
        self.build_ui()

        # Check credentials on startup
        if not self.generator.is_valid():
            self.root.after(1000, lambda: self.show_error_popup(
                "Configuration Error",
                "Missing environment variables:\n\n" + "\n".join(self.generator.validation_errors) +
                "\n\nPlease ensure your .env file contains:\n" +
                "- FACEBOOK_ACCESS_TOKEN\n" +
                "- HAWAII_TRACKER_GROUP_ID\n" +
                "- ANTHROPIC_API_KEY"
            ))

    def setup_styles(self):
        """Configure ttk styles for dark theme"""
        style = ttk.Style()

        # Try to use a theme that supports customization
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        # Configure frame style
        style.configure('Dark.TFrame', background=self.bg_color)

        # Configure label styles
        style.configure('Dark.TLabel',
                       background=self.bg_color,
                       foreground=self.fg_color,
                       font=('TkDefaultFont', 10))

        style.configure('Header.TLabel',
                       background=self.bg_color,
                       foreground=self.accent_color,
                       font=('TkDefaultFont', 16, 'bold'))

        style.configure('Section.TLabel',
                       background=self.bg_color,
                       foreground=self.accent_color,
                       font=('TkDefaultFont', 12, 'bold'))

        # Configure button styles
        style.configure('Accent.TButton',
                       background=self.accent_color,
                       foreground=self.fg_color,
                       font=('TkDefaultFont', 11),
                       padding=(10, 8))

        style.map('Accent.TButton',
                 background=[('active', '#cc1515'), ('disabled', '#4d0d0d')])

        style.configure('Secondary.TButton',
                       background='#990d0d',
                       foreground=self.fg_color,
                       font=('TkDefaultFont', 11),
                       padding=(10, 8))

        style.configure('Dark.TButton',
                       background='#404040',
                       foreground=self.fg_color,
                       font=('TkDefaultFont', 11),
                       padding=(10, 8))

        style.map('Dark.TButton',
                 background=[('active', '#505050'), ('disabled', '#2a2a2a')])

    def build_ui(self):
        """Build the main UI"""
        # Main container
        main_frame = ttk.Frame(self.root, style='Dark.TFrame', padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        self.build_header(main_frame)

        # Input section
        self.build_input_section(main_frame)

        # Control section
        self.build_control_section(main_frame)

        # Status section
        self.build_status_section(main_frame)

        # Output section
        self.build_output_section(main_frame)

    def build_header(self, parent):
        """Build header section"""
        header_frame = ttk.Frame(parent, style='Dark.TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 10))

        header_label = ttk.Label(
            header_frame,
            text='AlohaAI Emergency Watchtower',
            style='Header.TLabel'
        )
        header_label.pack()

    def build_input_section(self, parent):
        """Build input section"""
        input_frame = ttk.Frame(parent, style='Dark.TFrame')
        input_frame.pack(fill=tk.X, pady=(0, 10))

        # URL label
        url_label = ttk.Label(
            input_frame,
            text='Facebook Post URL:',
            style='Dark.TLabel'
        )
        url_label.pack(anchor=tk.W)

        # URL entry
        self.fb_link_input = tk.Entry(
            input_frame,
            font=('TkDefaultFont', 11),
            bg=self.secondary_bg,
            fg=self.fg_color,
            insertbackground=self.accent_color,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightcolor=self.accent_color,
            highlightbackground='#404040'
        )
        self.fb_link_input.pack(fill=tk.X, pady=(5, 0), ipady=8)
        self.fb_link_input.insert(0, '')
        self.fb_link_input.bind('<FocusIn>', lambda e: self._on_entry_focus(e, True))
        self.fb_link_input.bind('<FocusOut>', lambda e: self._on_entry_focus(e, False))

    def _on_entry_focus(self, event, focused):
        """Handle entry focus styling"""
        if focused:
            event.widget.config(highlightbackground=self.accent_color)
        else:
            event.widget.config(highlightbackground='#404040')

    def build_control_section(self, parent):
        """Build control buttons section"""
        control_frame = ttk.Frame(parent, style='Dark.TFrame')
        control_frame.pack(fill=tk.X, pady=(0, 10))

        # Generate button
        self.generate_btn = tk.Button(
            control_frame,
            text='Generate Report',
            font=('TkDefaultFont', 11),
            bg=self.accent_color,
            fg=self.fg_color,
            activebackground='#cc1515',
            activeforeground=self.fg_color,
            relief=tk.FLAT,
            cursor='hand2',
            command=self.generate_report
        )
        self.generate_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5), ipady=8)

        # Save button
        self.save_btn = tk.Button(
            control_frame,
            text='Save Report',
            font=('TkDefaultFont', 11),
            bg='#990d0d',
            fg=self.fg_color,
            activebackground='#800a0a',
            activeforeground=self.fg_color,
            relief=tk.FLAT,
            cursor='hand2',
            state=tk.DISABLED,
            disabledforeground='#666666',
            command=self.save_report
        )
        self.save_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5, ipady=8)

        # Clear button
        self.clear_btn = tk.Button(
            control_frame,
            text='Clear',
            font=('TkDefaultFont', 11),
            bg='#404040',
            fg=self.fg_color,
            activebackground='#505050',
            activeforeground=self.fg_color,
            relief=tk.FLAT,
            cursor='hand2',
            command=self.clear_output
        )
        self.clear_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0), ipady=8)

    def build_status_section(self, parent):
        """Build status section"""
        status_frame = ttk.Frame(parent, style='Dark.TFrame')
        status_frame.pack(fill=tk.X, pady=(0, 10))

        # Status header
        status_header = ttk.Label(
            status_frame,
            text='Status',
            style='Section.TLabel'
        )
        status_header.pack(anchor=tk.W)

        # Status grid
        grid_frame = ttk.Frame(status_frame, style='Dark.TFrame')
        grid_frame.pack(fill=tk.X, pady=(5, 0))

        # Status row
        status_label = ttk.Label(grid_frame, text='Status:', style='Dark.TLabel')
        status_label.grid(row=0, column=0, sticky=tk.W, padx=(0, 10))

        self.status_value = tk.Label(
            grid_frame,
            text='Ready',
            font=('TkDefaultFont', 10),
            bg=self.bg_color,
            fg=self.disabled_color
        )
        self.status_value.grid(row=0, column=1, sticky=tk.W)

        # Comments row
        comments_label = ttk.Label(grid_frame, text='Comments:', style='Dark.TLabel')
        comments_label.grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=(5, 0))

        self.comment_count_value = tk.Label(
            grid_frame,
            text='0',
            font=('TkDefaultFont', 10),
            bg=self.bg_color,
            fg=self.fg_color
        )
        self.comment_count_value.grid(row=1, column=1, sticky=tk.W, pady=(5, 0))

    def build_output_section(self, parent):
        """Build output section"""
        output_frame = ttk.Frame(parent, style='Dark.TFrame')
        output_frame.pack(fill=tk.BOTH, expand=True)

        # Output header
        output_header = ttk.Label(
            output_frame,
            text='Emergency Report',
            style='Section.TLabel'
        )
        output_header.pack(anchor=tk.W)

        # Output text area with scrollbar
        text_frame = ttk.Frame(output_frame, style='Dark.TFrame')
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        # Scrollbar
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Text widget with markdown support
        self.output_display = MarkdownText(
            text_frame,
            font=('TkDefaultFont', 10),
            bg='#262626',
            fg=self.fg_color,
            insertbackground=self.fg_color,
            relief=tk.FLAT,
            wrap=tk.WORD,
            padx=15,
            pady=15,
            yscrollcommand=scrollbar.set,
            state=tk.DISABLED
        )
        self.output_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.output_display.yview)

        # Set initial text
        self.output_display.config(state='normal')
        self.output_display.insert('1.0', 'Enter a Facebook post URL and click "Generate Report" to begin...\n')
        self.output_display.config(state='disabled')

    def update_status(self, status, color):
        """Update the status indicator"""
        self.status_value.config(text=status, fg=color)

    def log_progress(self, message):
        """Add progress message to output"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.output_display.append_text(f'[{timestamp}] {message}\n')

    def generate_report(self):
        """Start report generation"""
        fb_link = self.fb_link_input.get().strip()
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
        self.output_display.config(state='normal')
        self.output_display.delete('1.0', tk.END)
        self.output_display.config(state='disabled')
        self.current_report = None
        self.save_btn.config(state=tk.DISABLED)

        # Disable generate button
        self.generate_btn.config(state=tk.DISABLED, bg='#4d0d0d')

        # Start processing in background thread
        self.run_thread = threading.Thread(target=self.run_analysis, args=(fb_link,))
        self.run_thread.daemon = True
        self.run_thread.start()

    def run_analysis(self, post_url):
        """Background thread for analysis"""
        try:
            self.root.after(0, lambda: self.update_status('Extracting post ID...', self.warning_color))

            # Extract post ID
            post_id = self.generator.extract_post_id_from_url(post_url)
            if not post_id:
                self.root.after(0, lambda: self.log_progress('ERROR: Could not extract post ID from URL'))
                self.root.after(0, lambda: self.update_status('Error', self.error_color))
                self.root.after(0, lambda: self.generate_btn.config(state=tk.NORMAL, bg=self.accent_color))
                return

            full_post_id = f"{self.generator.group_id}_{post_id}"
            self.root.after(0, lambda: self.log_progress(f'Post ID: {full_post_id}'))

            # Scrape comments
            self.root.after(0, lambda: self.update_status('Scraping comments...', self.warning_color))

            def progress_callback(msg):
                self.root.after(0, lambda m=msg: self.log_progress(m))

            comments = self.generator.scrape_comments(full_post_id, progress_callback)

            if not comments:
                self.root.after(0, lambda: self.log_progress('ERROR: No comments retrieved'))
                self.root.after(0, lambda: self.update_status('Error', self.error_color))
                self.root.after(0, lambda: self.generate_btn.config(state=tk.NORMAL, bg=self.accent_color))
                return

            self.root.after(0, lambda: self.comment_count_value.config(text=str(len(comments))))
            self.root.after(0, lambda: self.log_progress(f'Total comments retrieved: {len(comments)}'))
            self.root.after(0, lambda: self.log_progress(''))

            # Generate report
            self.root.after(0, lambda: self.update_status('Analyzing with AI...', self.warning_color))

            report = self.generator.generate_report(comments, progress_callback)

            if not report:
                self.root.after(0, lambda: self.log_progress('ERROR: Failed to generate report'))
                self.root.after(0, lambda: self.update_status('Error', self.error_color))
                self.root.after(0, lambda: self.generate_btn.config(state=tk.NORMAL, bg=self.accent_color))
                return

            # Display report with markdown rendering
            self.current_report = report
            self.root.after(0, lambda r=report: self.display_report(r))
            self.root.after(0, lambda: self.update_status('Complete', self.success_color))
            self.root.after(0, lambda: self.save_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.generate_btn.config(state=tk.NORMAL, bg=self.accent_color))

        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda m=error_msg: self.log_progress(f'ERROR: {m}'))
            self.root.after(0, lambda: self.update_status('Error', self.error_color))
            self.root.after(0, lambda: self.generate_btn.config(state=tk.NORMAL, bg=self.accent_color))

    def display_report(self, report):
        """Display the markdown-formatted report"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Build header
        header_text = f'Emergency Report\n'
        header_text += f'Generated: {timestamp}\n'
        header_text += '=' * 60 + '\n\n'

        self.output_display.set_markdown_text(header_text + report)

    def save_report(self):
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

    def clear_output(self):
        """Clear the output display"""
        self.output_display.config(state='normal')
        self.output_display.delete('1.0', tk.END)
        self.output_display.insert('1.0', 'Enter a Facebook post URL and click "Generate Report" to begin...\n')
        self.output_display.config(state='disabled')
        self.current_report = None
        self.save_btn.config(state=tk.DISABLED)
        self.comment_count_value.config(text='0')
        self.update_status('Ready', self.disabled_color)

    def show_popup(self, title, message):
        """Show informational popup"""
        messagebox.showinfo(title, message)

    def show_error_popup(self, title, message):
        """Show error popup"""
        messagebox.showerror(title, message)


class EmergencyWatchtowerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.gui = WatchtowerGUI(self.root)

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = EmergencyWatchtowerApp()
    app.run()