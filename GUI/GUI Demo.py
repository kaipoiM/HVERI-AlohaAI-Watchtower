"""
AlohaAI Watchtower - Kivy GUI Prototype
Monitors Facebook Group posts for location-specific impacts during incidents
"""

import kivy
kivy.require('2.0.0')


# GUI imports for Matt
# import os
# os.environ['KIVY_GL_BACKEND'] = 'angle_sdl2'

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.uix.popup import Popup
import json
import threading
from datetime import datetime
from pathlib import Path

class WatchtowerGUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 10
        self.spacing = 10

        # HVERI color scheme
        from kivy.graphics import Color, Rectangle
        with self.canvas.before:
            Color(0.12, 0.12, 0.12, 1)  # Medium dark background
            self.bg_rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)

        # State management
        self.is_running = False
        self.run_thread = None
        self.state_file = Path('watchtower_state.json')
        self.output_dir = Path('watchtower_outputs')
        self.output_dir.mkdir(exist_ok=True)

        # Load previous state
        self.load_state()

        # Build UI
        self.build_ui()

    def _update_rect(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size

    def build_ui(self):
        # Header
        header = Label(
            text='AlohaAI Watchtower - Emergency Response Monitor',
            size_hint_y=None,
            height=60,
            bold=True,
            font_size='20sp',
            color=(0.9, 0.1, 0.1, 1)  # HVERI red
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

        # Output section
        output_section = self.build_output_section()
        self.add_widget(output_section)

    def build_input_section(self):
        layout = BoxLayout(orientation='vertical', size_hint_y=None, height=150, spacing=10)

        # Facebook link input
        link_label = Label(
            text='Facebook Post URL:',
            size_hint_y=None,
            height=35,
            font_size='16sp',
            halign='left',
            valign='middle',
            color=(1, 1, 1, 1)  # White text
        )
        link_label.bind(size=link_label.setter('text_size'))
        layout.add_widget(link_label)

        self.fb_link_input = TextInput(
            hint_text='https://facebook.com/groups/hawaiitracker/posts/...',
            size_hint_y=None,
            height=45,
            font_size='15sp',
            multiline=False,
            background_color=(0.2, 0.2, 0.2, 1),  # Lighter dark input
            foreground_color=(1, 1, 1, 1),  # White text
            cursor_color=(0.9, 0.1, 0.1, 1)  # Red cursor
        )
        if hasattr(self, 'state') and 'fb_link' in self.state:
            self.fb_link_input.text = self.state['fb_link']
        layout.add_widget(self.fb_link_input)

        # Interval setting
        interval_layout = BoxLayout(size_hint_y=None, height=45, spacing=10)
        interval_label = Label(
            text='Check Interval (minutes):',
            size_hint_x=0.6,
            font_size='16sp',
            color=(1, 1, 1, 1)  # White text
        )
        self.interval_input = TextInput(
            text='30',
            size_hint_x=0.4,
            font_size='15sp',
            input_filter='int',
            multiline=False,
            background_color=(0.2, 0.2, 0.2, 1),  # Lighter dark input
            foreground_color=(1, 1, 1, 1),  # White text
            cursor_color=(0.9, 0.1, 0.1, 1)  # Red cursor
        )
        interval_layout.add_widget(interval_label)
        interval_layout.add_widget(self.interval_input)
        layout.add_widget(interval_layout)

        return layout

    def build_control_section(self):
        layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=10)

        self.start_btn = Button(
            text='Start Monitoring',
            font_size='16sp',
            background_color=(0.9, 0.1, 0.1, 1),  # HVERI red
            color=(1, 1, 1, 1),  # White text
            background_normal=''
        )
        self.start_btn.bind(on_press=self.start_monitoring)

        self.stop_btn = Button(
            text='Stop Monitoring',
            font_size='16sp',
            background_color=(0.2, 0.2, 0.2, 1),  # Dark gray (disabled)
            color=(0.5, 0.5, 0.5, 1),  # Gray text
            background_normal='',
            disabled=True
        )
        self.stop_btn.bind(on_press=self.stop_monitoring)

        self.force_run_btn = Button(
            text='Force Run Now',
            font_size='16sp',
            background_color=(0.6, 0.05, 0.05, 1),  # Darker red
            color=(1, 1, 1, 1),  # White text
            background_normal=''
        )
        self.force_run_btn.bind(on_press=self.force_run)

        layout.add_widget(self.start_btn)
        layout.add_widget(self.stop_btn)
        layout.add_widget(self.force_run_btn)

        return layout

    def build_status_section(self):
        layout = BoxLayout(orientation='vertical', size_hint_y=None, height=180, spacing=8)

        status_label = Label(
            text='Status',
            size_hint_y=None,
            height=35,
            bold=True,
            font_size='18sp',
            color=(0.9, 0.1, 0.1, 1)  # HVERI red
        )
        layout.add_widget(status_label)

        # Status grid
        status_grid = GridLayout(cols=2, size_hint_y=None, height=130, spacing=8, row_force_default=True, row_default_height=30)

        label1 = Label(text='Status:', halign='left', font_size='15sp', color=(1, 1, 1, 1))
        label1.bind(size=label1.setter('text_size'))
        status_grid.add_widget(label1)

        self.status_value = Label(text='Idle', halign='left', color=(0.9, 0.1, 0.1, 1), font_size='15sp')
        self.status_value.bind(size=self.status_value.setter('text_size'))
        status_grid.add_widget(self.status_value)

        label2 = Label(text='Last Run:', halign='left', font_size='15sp', color=(1, 1, 1, 1))
        label2.bind(size=label2.setter('text_size'))
        status_grid.add_widget(label2)

        self.last_run_value = Label(text='Never', halign='left', font_size='15sp', color=(1, 1, 1, 1))
        self.last_run_value.bind(size=self.last_run_value.setter('text_size'))
        status_grid.add_widget(self.last_run_value)

        label3 = Label(text='Next Run:', halign='left', font_size='15sp', color=(1, 1, 1, 1))
        label3.bind(size=label3.setter('text_size'))
        status_grid.add_widget(label3)

        self.next_run_value = Label(text='N/A', halign='left', font_size='15sp', color=(1, 1, 1, 1))
        self.next_run_value.bind(size=self.next_run_value.setter('text_size'))
        status_grid.add_widget(self.next_run_value)

        label4 = Label(text='Total Runs:', halign='left', font_size='15sp', color=(1, 1, 1, 1))
        label4.bind(size=label4.setter('text_size'))
        status_grid.add_widget(label4)

        self.total_runs_value = Label(text='0', halign='left', font_size='15sp', color=(1, 1, 1, 1))
        self.total_runs_value.bind(size=self.total_runs_value.setter('text_size'))
        status_grid.add_widget(self.total_runs_value)

        layout.add_widget(status_grid)

        return layout

    def build_output_section(self):
        layout = BoxLayout(orientation='vertical', spacing=8)

        output_label = Label(
            text='Output Log',
            size_hint_y=None,
            height=35,
            bold=True,
            font_size='18sp',
            color=(0.9, 0.1, 0.1, 1)  # HVERI red
        )
        layout.add_widget(output_label)

        # Scrollable output with dark background
        from kivy.graphics import Color, Rectangle
        scroll = ScrollView(do_scroll_x=False)

        # Create container for background
        output_container = BoxLayout()
        with output_container.canvas.before:
            Color(0.15, 0.15, 0.15, 1)  # Darker area for contrast
            output_container.bg_rect = Rectangle(size=output_container.size, pos=output_container.pos)
        output_container.bind(size=lambda obj, val: setattr(obj.bg_rect, 'size', val),
                            pos=lambda obj, val: setattr(obj.bg_rect, 'pos', val))

        self.output_log = Label(
            text='Ready to start monitoring...\n',
            size_hint_y=None,
            halign='left',
            valign='top',
            markup=True,
            font_size='14sp',
            padding=(10, 10),
            color=(1, 1, 1, 1)  # Pure white text for better contrast
        )
        self.output_log.bind(texture_size=self.output_log.setter('size'))
        self.output_log.bind(width=lambda *x: self.output_log.setter('text_size')(self.output_log, (self.output_log.width - 20, None)))

        output_container.add_widget(self.output_log)
        scroll.add_widget(output_container)
        layout.add_widget(scroll)

        # Action buttons
        btn_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)

        view_results_btn = Button(
            text='View Latest Results',
            font_size='15sp',
            background_color=(0.25, 0.25, 0.25, 1),  # Slightly lighter gray
            color=(1, 1, 1, 1),  # White text
            background_normal=''
        )
        view_results_btn.bind(on_press=self.view_latest_results)

        export_btn = Button(
            text='Export Data',
            font_size='15sp',
            background_color=(0.25, 0.25, 0.25, 1),  # Slightly lighter gray
            color=(1, 1, 1, 1),  # White text
            background_normal=''
        )
        export_btn.bind(on_press=self.export_data)

        clear_log_btn = Button(
            text='Clear Log',
            font_size='15sp',
            background_color=(0.25, 0.25, 0.25, 1),  # Slightly lighter gray
            color=(1, 1, 1, 1),  # White text
            background_normal=''
        )
        clear_log_btn.bind(on_press=self.clear_log)

        btn_layout.add_widget(view_results_btn)
        btn_layout.add_widget(export_btn)
        btn_layout.add_widget(clear_log_btn)

        layout.add_widget(btn_layout)

        return layout

    def start_monitoring(self, instance):
        fb_link = self.fb_link_input.text.strip()
        if not fb_link:
            self.show_popup('Error', 'Please enter a Facebook post URL')
            return

        try:
            interval = int(self.interval_input.text)
            if interval < 1:
                raise ValueError
        except ValueError:
            self.show_popup('Error', 'Invalid interval. Must be a positive number.')
            return

        self.is_running = True
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        self.stop_btn.background_color = (0.9, 0.1, 0.1, 1)  # Red when enabled
        self.stop_btn.color = (1, 1, 1, 1)
        self.fb_link_input.disabled = True
        self.interval_input.disabled = True

        self.state['fb_link'] = fb_link
        self.state['interval'] = interval
        self.save_state()

        self.update_status('Monitoring Active', (0.9, 0.1, 0.1, 1))  # Red for active
        self.log_output(f'[b]Started monitoring:[/b] {fb_link}')
        self.log_output(f'Check interval: {interval} minutes')

        # Schedule periodic runs
        Clock.schedule_interval(self.scheduled_run, interval * 60)

        # Run immediately
        self.execute_run()

    def stop_monitoring(self, instance):
        self.is_running = False
        self.start_btn.disabled = False
        self.stop_btn.disabled = True
        self.stop_btn.background_color = (0.2, 0.2, 0.2, 1)  # Dark gray when disabled
        self.stop_btn.color = (0.5, 0.5, 0.5, 1)
        self.fb_link_input.disabled = False
        self.interval_input.disabled = False

        Clock.unschedule(self.scheduled_run)

        self.update_status('Stopped', (0.5, 0.5, 0.5, 1))  # Gray for stopped
        self.log_output('[b]Monitoring stopped[/b]')
        self.next_run_value.text = 'N/A'

    def force_run(self, instance):
        fb_link = self.fb_link_input.text.strip()
        if not fb_link:
            self.show_popup('Error', 'Please enter a Facebook post URL')
            return

        self.log_output('[b]Manual run triggered[/b]')
        self.execute_run()

    def scheduled_run(self, dt):
        if self.is_running:
            self.execute_run()
        return self.is_running

    def execute_run(self):
        """Execute a monitoring run in a separate thread"""
        if self.run_thread and self.run_thread.is_alive():
            self.log_output('[color=#FF8800]Previous run still in progress, skipping...[/color]')
            return

        self.run_thread = threading.Thread(target=self.run_analysis)
        self.run_thread.daemon = True
        self.run_thread.start()

    def run_analysis(self):
        """Main analysis routine - integrate your existing scraper/LangChain code here"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            Clock.schedule_once(lambda dt: self.update_status('Processing...', (0.9, 0.5, 0.1, 1)), 0)  # Orange for processing
            Clock.schedule_once(lambda dt: self.log_output(f'\n[b]Run started:[/b] {timestamp}'), 0)

            # TODO: Replace with actual scraper integration
            # 1. Scrape comments from Facebook post
            Clock.schedule_once(lambda dt: self.log_output('→ Scraping comments...'), 0)
            # comments = scrape_facebook_comments(self.fb_link_input.text)

            # 2. Load previous runs for context
            Clock.schedule_once(lambda dt: self.log_output('→ Loading previous context...'), 0)
            prev_runs = self.load_previous_runs(3)

            # 3. Process with LangChain
            Clock.schedule_once(lambda dt: self.log_output('→ Analyzing with LangChain...'), 0)
            # results = process_with_langchain(comments, prev_runs)

            # Mock results for demonstration
            results = {
                'timestamp': timestamp,
                'by_district': {
                    'Hilo': 'Power outages reported in downtown area. Traffic delays on Highway 19.',
                    'Kona': 'Minor flooding near Ali\'i Drive. Beach closures in effect.',
                    'Puna': 'Road blockages due to fallen trees on Highway 130.'
                },
                'high_priority': [
                    'Medical emergency reported in Hilo - ambulance dispatched',
                    'Major power outage affecting 500+ homes in Kona',
                    'Highway 130 blocked - alternate routes advised'
                ],
                'comment_count': 247,
                'new_comments': 83
            }

            # 4. Save results
            Clock.schedule_once(lambda dt: self.log_output('→ Saving results...'), 0)
            self.save_results(results)

            # 5. Update UI
            Clock.schedule_once(lambda dt: self.finalize_run(results, timestamp), 0)

        except Exception as e:
            error_msg = f'Error during run: {str(e)}'
            Clock.schedule_once(lambda dt: self.log_output(f'[color=#FF0000]{error_msg}[/color]'), 0)
            Clock.schedule_once(lambda dt: self.update_status('Error', (1, 0, 0, 1)), 0)  # Bright red for error

    def finalize_run(self, results, timestamp):
        """Update UI after successful run"""
        self.state['last_run'] = timestamp
        self.state['total_runs'] = self.state.get('total_runs', 0) + 1
        self.save_state()

        self.last_run_value.text = timestamp
        self.total_runs_value.text = str(self.state['total_runs'])

        if self.is_running:
            interval = int(self.interval_input.text)
            next_time = datetime.now().timestamp() + (interval * 60)
            self.next_run_value.text = datetime.fromtimestamp(next_time).strftime('%Y-%m-%d %H:%M:%S')
            self.update_status('Monitoring Active', (0.9, 0.1, 0.1, 1))  # Red for active
        else:
            self.update_status('Idle', (0.5, 0.5, 0.5, 1))  # Gray for idle

        self.log_output(f'[color=#FF3333]✓ Run completed successfully[/color]')
        self.log_output(f'  Comments processed: {results["comment_count"]} ({results["new_comments"]} new)')
        self.log_output(f'  High-priority items: {len(results["high_priority"])}')

    def load_previous_runs(self, count=3):
        """Load the last N runs for context chaining"""
        run_files = sorted(self.output_dir.glob('run_*.json'), reverse=True)[:count]
        previous = []
        for f in run_files:
            with open(f, 'r') as file:
                previous.append(json.load(file))
        return previous

    def save_results(self, results):
        """Save run results to disk"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f'run_{timestamp}.json'

        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        # Also save human-readable format
        text_file = self.output_dir / f'report_{timestamp}.txt'
        with open(text_file, 'w') as f:
            f.write(f"AlohaAI Watchtower Report - {results['timestamp']}\n")
            f.write("=" * 60 + "\n\n")

            f.write("HIGH PRIORITY ITEMS:\n")
            f.write("-" * 60 + "\n")
            for i, item in enumerate(results['high_priority'], 1):
                f.write(f"{i}. {item}\n")
            f.write("\n")

            f.write("BY DISTRICT SUMMARY:\n")
            f.write("-" * 60 + "\n")
            for district, summary in results['by_district'].items():
                f.write(f"\n{district}:\n{summary}\n")

    def view_latest_results(self, instance):
        """Display the most recent results"""
        run_files = sorted(self.output_dir.glob('run_*.json'), reverse=True)
        if not run_files:
            self.show_popup('No Results', 'No analysis results available yet.')
            return

        with open(run_files[0], 'r') as f:
            results = json.load(f)

        content_text = f"[b]Report from {results['timestamp']}[/b]\n\n"
        content_text += "[b]HIGH PRIORITY:[/b]\n"
        for item in results['high_priority']:
            content_text += f"• {item}\n"
        content_text += f"\n[b]BY DISTRICT:[/b]\n"
        for district, summary in results['by_district'].items():
            content_text += f"\n[b]{district}:[/b]\n{summary}\n"

        # Create scrollable container with dark background
        from kivy.graphics import Color, Rectangle
        popup_container = BoxLayout()
        with popup_container.canvas.before:
            Color(0.15, 0.15, 0.15, 1)  # Dark background
            popup_container.bg_rect = Rectangle(size=popup_container.size, pos=popup_container.pos)
        popup_container.bind(size=lambda obj, val: setattr(obj.bg_rect, 'size', val),
                           pos=lambda obj, val: setattr(obj.bg_rect, 'pos', val))

        popup_content = ScrollView(do_scroll_x=False)
        label = Label(
            text=content_text,
            markup=True,
            size_hint_y=None,
            halign='left',
            valign='top',
            font_size='15sp',
            padding=(15, 15),
            color=(1, 1, 1, 1)  # White text on dark background
        )
        label.bind(texture_size=label.setter('size'))
        label.bind(width=lambda *x: label.setter('text_size')(label, (label.width - 30, None)))
        popup_content.add_widget(label)
        popup_container.add_widget(popup_content)

        popup = Popup(
            title='Latest Results',
            content=popup_container,
            size_hint=(0.85, 0.85),
            title_color=(0.9, 0.1, 0.1, 1),  # Red title
            separator_color=(0.9, 0.1, 0.1, 1)  # Red separator
        )
        popup.open()

    def export_data(self, instance):
        """Export all results as a single JSON file"""
        run_files = sorted(self.output_dir.glob('run_*.json'))
        if not run_files:
            self.show_popup('No Data', 'No data available to export.')
            return

        all_runs = []
        for f in run_files:
            with open(f, 'r') as file:
                all_runs.append(json.load(file))

        export_file = self.output_dir / f'export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(export_file, 'w') as f:
            json.dump(all_runs, f, indent=2)

        self.show_popup('Export Complete', f'Data exported to:\n{export_file}')

    def clear_log(self, instance):
        self.output_log.text = 'Log cleared.\n'

    def log_output(self, message):
        """Add a message to the output log"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.output_log.text += f'[{timestamp}] {message}\n'

    def update_status(self, status, color):
        """Update the status indicator"""
        self.status_value.text = status
        self.status_value.color = color

    def load_state(self):
        """Load persistent state from disk"""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                self.state = json.load(f)
        else:
            self.state = {}

    def save_state(self):
        """Save persistent state to disk"""
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)

    def show_popup(self, title, message):
        """Show a simple popup message"""
        # Create container with dark background
        from kivy.graphics import Color, Rectangle
        popup_container = BoxLayout(padding=20)
        with popup_container.canvas.before:
            Color(0.15, 0.15, 0.15, 1)  # Dark background
            popup_container.bg_rect = Rectangle(size=popup_container.size, pos=popup_container.pos)
        popup_container.bind(size=lambda obj, val: setattr(obj.bg_rect, 'size', val),
                           pos=lambda obj, val: setattr(obj.bg_rect, 'pos', val))

        content = Label(
            text=message,
            font_size='15sp',
            color=(1, 1, 1, 1),  # White text on dark background
            halign='center',
            valign='middle'
        )
        content.bind(size=content.setter('text_size'))
        popup_container.add_widget(content)

        popup = Popup(
            title=title,
            content=popup_container,
            size_hint=(0.7, 0.5),
            title_color=(0.9, 0.1, 0.1, 1),  # Red title
            separator_color=(0.9, 0.1, 0.1, 1)  # Red separator
        )
        popup.open()


class WatchtowerApp(App):
    def build(self):
        self.title = 'AlohaAI Watchtower'
        return WatchtowerGUI()


if __name__ == '__main__':
    WatchtowerApp().run()