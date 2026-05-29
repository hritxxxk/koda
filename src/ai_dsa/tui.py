from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Select, Label, Button, ListItem, ListView, TextArea, Markdown, Input
from textual.screen import ModalScreen, Screen
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.binding import Binding
from textual.events import Key
from typing import List, Dict, Any
import asyncio
import os
import time
import json
import tempfile
import subprocess
from .providers import GeminiProvider, OllamaProvider, AnthropicProvider, OpenAIProvider
from .codec import IndentEngine, LanguageRules, BracketEngine
from .models import Problem, SQLProblem
from . import telemetry
from .profiler import UserProfiler
from . import recommender
from . import notes
from .linter import Linter

class FixModeEntryScreen(ModalScreen):
    """Entry screen for Fix AI Slop mode."""
    def compose(self) -> ComposeResult:
        with Vertical(id="startup-container"):
            yield Label("Fix AI Slop Mode", id="startup-subtitle")
            with ListView(id="entry-list"):
                yield ListItem(Label("[1] Give a problem statement - AI generates sloppy code"), id="entry-generate")
                yield ListItem(Label("[2] Paste your own AI-generated code"), id="entry-paste")
            yield Label("Use Arrows + Enter or 1/2 keys", id="startup-footer")

    def on_mount(self) -> None:
        self.query_one("#entry-list").focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        entry_id = event.item.id
        if entry_id == "entry-generate":
            self.dismiss("generate")
        elif entry_id == "entry-paste":
            self.dismiss("paste")

    def on_key(self, event: Key) -> None:
        if event.character == "1":
            self.dismiss("generate")
        elif event.character == "2":
            self.dismiss("paste")

class StartupScreen(ModalScreen):
    """Initial screen for mode selection."""
    def compose(self) -> ComposeResult:
        with Vertical(id="startup-container"):
            yield Label(r"""
            ██   ██  ██████  ██████   █████
            ██  ██  ██    ██ ██   ██ ██   ██
            █████   ██    ██ ██   ██ ███████
            ██  ██  ██    ██ ██   ██ ██   ██
            ██   ██  ██████  ██████  ██   ██
            """, id="ascii-logo")
            yield Label("Select your training path:", id="startup-subtitle")
            
            with ListView(id="mode-list"):
                yield ListItem(Label("[1] DSA Practice"), id="mode-dsa")
                yield ListItem(Label("[2] SQL Practice"), id="mode-sql")
                yield ListItem(Label("[3] Fix AI Slop"), id="mode-fix")
            
            yield Label("Use Arrows + Enter or 1/2/3 keys", id="startup-footer")

    def on_mount(self) -> None:
        self.query_one("#mode-list").focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        mode_id = event.item.id
        if mode_id == "mode-dsa":
            self.dismiss("DSA")
        elif mode_id == "mode-sql":
            self.dismiss("SQL")
        elif mode_id == "mode-fix":
            self.dismiss("FixSlop")

    def on_key(self, event: Key) -> None:
        if event.character == "1":
            self.dismiss("DSA")
        elif event.character == "2":
            self.dismiss("SQL")
        elif event.character == "3":
            self.dismiss("FixSlop")

class ProblemStatementModal(ModalScreen):
    """A modal for entering a problem statement to generate slop."""
    def compose(self) -> ComposeResult:
        with Vertical(id="options-dialog"):
            yield Label("Enter Problem Statement:")
            yield Label("AI will generate a sloppy solution for you to fix.")
            yield TextArea(id="statement-input", classes="large-input")
            with Horizontal(id="options-buttons"):
                yield Button("Generate", variant="primary", id="gen-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "gen-btn":
            text = self.query_one("#statement-input", TextArea).text
            self.dismiss(text)
        else:
            self.dismiss(None)

class PasteModal(ModalScreen):
    """A modal for pasting code."""
    def compose(self) -> ComposeResult:
        with Vertical(id="options-dialog"):
            yield Label("Paste Slop Code Below:")
            yield TextArea(id="paste-input", classes="large-input")
            with Horizontal(id="options-buttons"):
                yield Button("Load", variant="primary", id="load-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "load-btn":
            text = self.query_one("#paste-input", TextArea).text
            self.dismiss(text)
        else:
            self.dismiss(None)

class HelpOverlay(ModalScreen):
    """A floating modal showing keybindings."""
    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Label("Keyboard Shortcuts", id="help-title")
            yield Markdown("""
| Key | Action |
|---|---|
| `Ctrl+P` | Select Problem |
| `Ctrl+N` | New AI Problem |
| `Ctrl+H` | Get Socratic Hint |
| `Ctrl+G` | Submit Solution |
| `Ctrl+R` | Get Code Review |
| `Ctrl+S` | Run Tests |
| `Ctrl+O` | Options / Provider |
| `/` | Focus Command Bar |
| `F2` | View Statistics |
| `Esc` | Focus Editor |
| `?` | Show this Help |
""")
            yield Label("Press any key to dismiss", id="help-footer")

    def on_key(self, event: Key) -> None:
        self.dismiss()

class SlopGutter(Static):
    """A gutter for showing severity markers next to code."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.markers = {} # line_no -> char
        self.gutter_scroll_offset = 0

    def update_markers(self, issues: List[Dict]):
        self.markers = {}
        for issue in issues:
            line = int(issue["line"])
            severity = issue["severity"]
            char = "🔴" if severity == "red" else "🟡" if severity == "yellow" else "🟢"
            self.markers[line] = char
        self.refresh()

    def sync_scroll(self, offset: int):
        self.gutter_scroll_offset = offset
        self.refresh()

    def render(self):
        from rich.text import Text
        lines = []
        # Adjust for scroll offset
        # The gutter itself is a Static, we just render lines.
        # We need to render from gutter_scroll_offset+1 to gutter_scroll_offset+height
        start_line = int(self.gutter_scroll_offset) + 1
        height = self.size.height or 50
        if height == 0: height = 50
        
        for i in range(start_line, start_line + height):
            char = self.markers.get(i, "  ")
            lines.append(f"{char}")
        return Text("\n".join(lines))

class PythonEditor(TextArea):
    """A professional-grade editor with background linting and smart behavior."""
    
    def on_mount(self) -> None:
        self.border_title = "Editor"
        self._refresh_indent_settings()
        self._lint_task = None
        self._lint_errors = {} # line -> message

    def _refresh_indent_settings(self) -> None:
        """Scan content to detect indentation style."""
        char, width = IndentEngine.detect_indent(self.text)
        self.indent_width = width
        self.indent_unit = char * width

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Trigger background linting on change (debounced)."""
        if self.language == "python":
            if self._lint_task:
                self._lint_task.cancel()
            
            async def run_lint():
                await asyncio.sleep(1.0) # Debounce
                issues = await asyncio.to_thread(Linter.lint_code, self.text)
                self._lint_errors = {i["line"]: i["message"] for i in issues}
                # Update app status or gutter if available
                if hasattr(self.app, "update_editor_lint"):
                    self.app.update_editor_lint(issues)
            
            self._lint_task = asyncio.create_task(run_lint())

    def action_submit(self) -> None:
        asyncio.create_task(self.app.action_submit())

    def action_run_tests(self) -> None:
        asyncio.create_task(self.app.action_run_tests())

    def action_get_hint(self) -> None:
        asyncio.create_task(self.app.action_get_hint())

    def action_get_review(self) -> None:
        asyncio.create_task(self.app.action_get_review())

    def action_open_vim(self) -> None:
        asyncio.create_task(self.app.action_open_vim())

    def on_key(self, event: Key) -> None:
        # Notify app of first keystroke for telemetry
        if hasattr(self.app, "on_editor_keystroke"):
            self.app.on_editor_keystroke()
            
        # 1. Bracket Auto-Pairing
        if event.character and event.character in BracketEngine.PAIRS:
            closing = BracketEngine.get_closing(event.character)
            if self.selection.is_empty:
                # Auto-pair
                self.insert(event.character + closing)
                self.move_cursor_relative(columns=-1)
                event.stop()
                event.prevent_default()
                return
            else:
                # Wrap selection
                start, end = self.selection.start, self.selection.end
                text = self.selected_text
                self.replace(event.character + text + closing, start, end)
                event.stop()
                event.prevent_default()
                return

        # 2. Smart Indentation on Enter
        if event.key == "enter":
            cursor_row, _ = self.cursor_location
            current_line = self.document[cursor_row]
            current_indent = current_line[:len(current_line) - len(current_line.lstrip())]
            
            next_indent = LanguageRules.get_next_indent(
                self.language or "python", 
                current_line, 
                current_indent, 
                self.indent_unit
            )
            
            # Only override if we're actually changing the indentation level
            # OR if we are preserving a non-zero indentation.
            # If current line is empty and next_indent is empty, let default handle it.
            if next_indent:
                self.insert("\n" + next_indent)
                event.stop()
                event.prevent_default()
                return
            # Else: let Textual handle the default Enter behavior

class ProblemPickerScreen(ModalScreen):
    """Unified screen for selecting or generating problems."""
    def compose(self) -> ComposeResult:
        with Vertical(id="picker-dialog"):
            yield Label("Select or Generate Problem", id="picker-title")
            with Horizontal(id="picker-body"):
                with Vertical(id="list-section"):
                    yield Label("Existing Problems", classes="section-label")
                    yield ListView(id="problem-list")
                
                with Vertical(id="gen-section"):
                    yield Label("AI Generation", classes="section-label")
                    label_text = "Topic (e.g. Graphs)" if self.app.mode == "DSA" else "Schema/Topic (e.g. JOINs)"
                    yield Label(label_text)
                    yield TextArea(id="topic-input", classes="picker-input")
                    yield Button("Generate [Ctrl+G]", variant="primary", id="gen-btn")
            
            with Horizontal(id="picker-footer"):
                yield Label("", id="recommendation-label")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        list_view = self.query_one("#problem-list", ListView)
        if self.app.mode == "SQL":
            for problem in self.app.sql_bank.problems:
                list_view.append(ListItem(Label(f"{problem.title} [{problem.difficulty}]"), id=problem.id))
        else:
            for problem in self.app.bank.problems:
                list_view.append(ListItem(Label(f"{problem.title} [{problem.difficulty}]"), id=problem.id))
        
        # C.3 Recommendations
        self._update_recommendation()

    def _update_recommendation(self) -> None:
        if self.app.mode not in ["DSA", "SQL"]:
            return
            
        review_prob = recommender.get_review_problem(self.app.db, self.app.bank, self.app.sql_bank, self.app.mode)
        label = self.query_one("#recommendation-label", Label)
        
        if review_prob:
            label.update(f"[R] Review: {review_prob.title} — you struggled with this recently")
            label.add_class("review-suggestion")
        else:
            next_prob = recommender.get_next_problem(
                self.app.db, self.app.bank, self.app.sql_bank, self.app.mode, 
                self.app.problem.id if hasattr(self.app, 'problem') and self.app.problem else ""
            )
            if next_prob:
                label.update(f"[N] Suggested: {next_prob.title}")
                label.add_class("next-suggestion")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        problem_id = event.item.id
        if self.app.mode == "SQL":
            problem = self.app.sql_bank.get_problem(problem_id)
            self.app.load_sql_problem(problem)
        else:
            problem = self.app.bank.get_problem(problem_id)
            self.app.load_problem(problem)
        self.dismiss(True)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "gen-btn":
            await self.action_generate()
        elif event.button.id == "cancel-btn":
            if not hasattr(self.app, "problem") or self.app.problem is None:
                self.app.exit()
            else:
                self.dismiss(False)

    async def action_generate(self) -> None:
        topic = self.query_one("#topic-input", TextArea).text.strip()
        if not topic:
            self.app.notify("Enter a topic first", severity="warning")
            return
        
        self.app.notify(f"AI: Generating {self.app.mode} problem...")
        try:
            if self.app.mode == "SQL":
                problem_dict = await self.app.ai.generate_sql_problem(topic)
                new_problem = SQLProblem.from_dict(problem_dict)
                self.app.sql_bank.save_problem(new_problem)
                self.app.load_sql_problem(new_problem)
            else:
                problem_dict = await self.app.ai.generate_problem(topic=topic)
                new_problem = Problem.from_dict(problem_dict)
                self.app.bank.save_problem(new_problem)
                self.app.load_problem(new_problem)
            self.dismiss(True)
        except Exception as e:
            self.app.notify(f"Generation Error: {str(e)}", severity="error")

    BINDINGS = [
        Binding("ctrl+g", "generate", "Generate")
    ]

class NotesScreen(Screen):
    """Full-screen overlay for viewing and managing notes."""
    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(id="notes-container"):
            yield Label("AI-Generated Insights", classes="section-label")
            yield Markdown("", id="ai-notes-content")
            
            yield Label("Manual Notes", classes="section-label")
            yield ListView(id="manual-notes-list")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_notes()
        self._editing_note_id = None

    def _refresh_notes(self) -> None:
        all_notes = notes.get_notes(self.app.db)
        
        # AI Insights
        ai_notes = [n for n in all_notes if n["source"] == "ai_generated"]
        ai_text = ""
        for n in ai_notes:
            ai_text += f"- **[{n['mode']}]** {n['content']} *({n['timestamp']})*\n"
        self.query_one("#ai-notes-content", Markdown).update(ai_text or "No AI insights yet.")
        
        # Manual Notes
        manual_list = self.query_one("#manual-notes-list", ListView)
        manual_list.clear()
        manual_notes = [n for n in all_notes if n["source"] == "manual"]
        for n in manual_notes:
            item = ListItem(Label(f"[{n['mode']}] {n['content']} ({n['timestamp']})"))
            item.note_id = n["id"]
            item.note_content = n["content"]
            item.note_source = n["source"]
            manual_list.append(item)

    def on_key(self, event: Key) -> None:
        if self._editing_note_id is not None:
            return # Let Input handle keys

        if event.character == "d":
            # Delete selected manual note
            list_view = self.query_one("#manual-notes-list", ListView)
            if list_view.highlighted_child:
                note_id = list_view.highlighted_child.note_id
                with self.app.db._get_connection() as conn:
                    conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
                    conn.commit()
                self._refresh_notes()
                self.app.notify("Note deleted.")
        elif event.character == "e":
            list_view = self.query_one("#manual-notes-list", ListView)
            if list_view.highlight_index is not None:
                # Check if it's AI or manual (though it's in manual list, let's be safe)
                item = list_view.highlighted_child
                if item.note_source == "ai_generated":
                    self.app.notify("AI notes are read-only", severity="warning")
                else:
                    self._start_editing(item)

    def _start_editing(self, item: ListItem) -> None:
        self._editing_note_id = item.note_id
        # Replace label with Input
        old_label = item.query_one(Label)
        new_input = Input(value=item.note_content, id="note-edit-input")
        item.mount(new_input)
        old_label.display = False
        new_input.focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "note-edit-input":
            new_content = event.value.strip()
            if new_content:
                notes.update_note(self.app.db, self._editing_note_id, new_content)
                self.app.notify("Note updated.")
            self._editing_note_id = None
            self._refresh_notes()

    def on_input_changed(self, event: Input.Changed) -> None:
        # Prevent app-level input handling if any
        pass

    def action_cancel_edit(self) -> None:
        if self._editing_note_id is not None:
            self._editing_note_id = None
            self._refresh_notes()

    BINDINGS = [
        ("escape", "cancel_edit_or_back", "Back"),
        ("ctrl+n", "app.pop_screen", "Back")
    ]
    
    def action_cancel_edit_or_back(self) -> None:
        if self._editing_note_id is not None:
            self._editing_note_id = None
            self._refresh_notes()
        else:
            self.app.pop_screen()

class StatsScreen(Screen):
    """Full-screen overlay for statistics."""
    def compose(self) -> ComposeResult:
        yield Header()
        yield Markdown("Loading Stats...", id="stats-content")
        yield Footer()

    def on_mount(self) -> None:
        stats_data = self.app.db.get_stats()
        if not stats_data:
            content = "# No stats found yet. Start practicing!"
        else:
            content = "# Your Progress\n\n| Topic | Solved | Total |\n|---|---|---|\n"
            for row in stats_data:
                content += f"| {row['topic']} | {row['solved_count']} | - |\n"
        
        self.query_one("#stats-content", Markdown).update(content)

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("F2", "app.pop_screen", "Back")
    ]

class OptionsScreen(ModalScreen):
    """Screen for configuring app settings."""
    def compose(self) -> ComposeResult:
        providers = [
            ("Ollama", "ollama"),
            ("Gemini", "gemini"),
            ("Anthropic", "anthropic"),
            ("OpenAI", "openai")
        ]
        
        with Vertical(id="options-dialog"):
            yield Label("Settings", id="options-title")
            
            yield Label("AI Provider:")
            yield Select(providers, id="provider-select", value=getattr(self.app, "provider_name", "ollama"))
            
            yield Label("Model Name:")
            yield Select([], id="model-select")
            
            with Horizontal(id="options-buttons"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        self.update_models(self.query_one("#provider-select", Select).value)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "provider-select":
            self.update_models(str(event.value))

    def update_models(self, provider: str) -> None:
        select = self.query_one("#model-select", Select)
        if provider == "gemini":
            models = [("Gemini 2.0 Flash", "gemini-2.0-flash"), ("Gemini 1.5 Pro", "gemini-1.5-pro")]
        elif provider == "anthropic":
            models = [("Claude 3.5 Sonnet", "claude-3-5-sonnet-20241022"), ("Claude 3 Opus", "claude-3-opus-20240229")]
        elif provider == "openai":
            models = [("GPT-4o", "gpt-4o"), ("GPT-4 Turbo", "gpt-4-turbo")]
        else:
            models = [
                ("Qwen 2.5 (7B)", "qwen2.5:7b"),
                ("Llama 3 (8B)", "llama3:8b"),
                ("Gemma 3 (4B)", "gemma3:4b"),
                ("Phi-3 (Mini)", "phi3")
            ]
        
        select.set_options(models)
        saved_model = self.app.db.get_setting("ai_model")
        if saved_model and any(m[1] == saved_model for m in models):
            select.value = saved_model
        else:
            select.value = models[0][1]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            provider = str(self.query_one("#provider-select", Select).value)
            model = str(self.query_one("#model-select", Select).value)
            
            self.app.db.set_setting("ai_provider", provider)
            self.app.db.set_setting("ai_model", model)
            self.app.update_ai_provider(provider, model)
            self.dismiss(True)
        else:
            self.dismiss(False)

class CommandMenu(Static):
    """A floating menu showing available commands."""
    def update_menu(self, filter_text: str) -> None:
        commands = [
            ("/hint", "Get a Socratic hint"),
            ("/review", "Deep code critique"),
            ("/generate random", "Random problem"),
            ("/generate specific", "Targeted problem"),
            ("/generate something", "AI picks for you"),
            ("/explain", "Breakdown requirements"),
            ("/test", "Run all test cases"),
            ("/clear", "Wipe AI history")
        ]
        
        filtered = [c for c in commands if c[0].startswith(filter_text)]
        if not filtered:
            self.display = False
            return
            
        self.display = True
        content = "[bold underline]Commands[/]\n"
        for cmd, desc in filtered:
            content += f"[bold]{cmd}[/] - {desc}\n"
        self.update(content)

class CommandBar(Input):
    """A terminal-style command bar for AI interactions and app commands."""
    def __init__(self, **kwargs):
        super().__init__(placeholder="Press / for commands (e.g. /hint, /review, or ask a question...)", **kwargs)

    def on_mount(self) -> None:
        self.border_title = "Command"

    def on_input_changed(self, event: Input.Changed) -> None:
        menu = self.app.query_one("#command-menu", CommandMenu)
        if event.value.startswith("/"):
            menu.update_menu(event.value)
        else:
            menu.display = False

    def on_focus(self) -> None:
        if self.value.startswith("/"):
            self.app.query_one("#command-menu", CommandMenu).display = True

    def on_blur(self) -> None:
        self.app.query_one("#command-menu", CommandMenu).display = False

class DSATUI(App):
    """Main TUI for Koda."""
    TITLE = "Koda"
    CSS = """
    #app-container {
        height: 1fr;
        layout: grid;
        grid-size: 3;
        grid-columns: 30fr 40fr 30fr;
    }

    #startup-container {
        align: center middle;
        background: $background;
    }

    #ascii-logo {
        color: $accent;
        text-style: bold;
        margin-bottom: 2;
        width: auto;
    }

    #startup-subtitle {
        text-style: bold;
        margin-bottom: 1;
    }

    #mode-list {
        width: 40;
        height: auto;
        border: thick $primary;
        margin-bottom: 1;
    }

    #mode-list ListItem {
        padding: 1;
    }

    #startup-footer {
        color: $text-muted;
    }

    #problem-pane {
        border: tall $primary-lighten-3;
        padding: 0 1;
        height: 100%;
        overflow-y: scroll;
        scrollbar-gutter: stable;
    }
    
    #problem-pane:focus-within {
        border: tall $accent;
    }

    #problem-markdown {
        height: auto;
        width: 100%;
    }

    #editor-pane {
        height: 100%;
        layout: vertical;
    }

    #main-editor-container {
        height: 1fr;
        layout: horizontal;
        border: thick $primary-lighten-3;
    }
    
    #main-editor-container:focus-within {
        border: thick $accent;
    }

    #main-gutter {
        width: 4;
        height: 100%;
        background: $surface;
        color: $text;
        content-align: center top;
        padding-top: 1;
    }

    #code-editor {
        border: none;
        height: 100%;
    }

    #slop-container {
        display: none;
        height: 1fr;
    }

    #slop-left-container {
        width: 1fr;
        height: 100%;
        layout: horizontal;
        border: thick $primary-lighten-3;
    }
    
    #slop-left-container:focus-within {
        border: thick $accent;
    }

    #slop-gutter {
        width: 4;
        height: 100%;
        background: $surface;
        color: $text;
        content-align: center top;
        padding-top: 1;
    }

    #slop-left {
        width: 1fr;
        height: 100%;
        border: none;
    }
    
    #slop-right {
        width: 1fr;
        height: 100%;
        border: thick $primary-lighten-3;
    }
    
    #slop-right:focus {
        border: thick $accent;
    }

    #ai-pane {
        border: tall $primary-lighten-3;
        padding: 0;
        background: $panel;
        height: 100%;
        layout: vertical;
        scrollbar-gutter: stable;
    }
    
    #ai-pane:focus-within {
        border: tall $accent;
    }

    #ai-content {
        height: 1fr;
        padding: 1;
    }

    #command-bar-container {
        height: auto;
        border-top: tall $primary-lighten-3;
        padding: 0 1;
    }

    #command-menu {
        display: none;
        background: $surface;
        border: tall $accent;
        padding: 1;
        width: 100%;
        height: auto;
        dock: bottom;
        margin-bottom: 0;
    }

    #command-bar {
        height: 3;
        border: none;
        background: $surface;
        color: $text;
    }
    
    #command-bar:focus {
        border: none;
    }

    #ai-header-row {
        height: auto;
        align: center middle;
    }
    
    .ai-coach-header {
        color: $accent;
        text-style: bold;
        width: 1fr;
    }
    
    #struggle-timer {
        color: $text-muted;
        text-style: italic;
        width: auto;
    }

    .ai-coach-buttons {
        height: auto;
        margin: 1 0;
        layout: vertical;
    }

    .ai-coach-buttons Button {
        margin-bottom: 1;
        width: 100%;
    }

    #ai-recent-header {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
        border: inner $primary;
        padding-top: 1;
    }

    #ai-markdown {
        color: $text-muted;
        height: auto;
        width: 100%;
    }

    #picker-dialog {
        background: $panel;
        border: thick $primary;
        padding: 1 2;
        width: 80%;
        height: 80%;
        align: center middle;
    }

    #picker-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
        width: 100%;
        content-align: center middle;
    }

    #picker-body {
        height: 1fr;
        border-top: tall $primary-lighten-2;
        border-bottom: tall $primary-lighten-2;
        padding: 1 0;
    }

    #list-section {
        width: 1fr;
        border-right: tall $primary-lighten-2;
        padding-right: 2;
    }

    #gen-section {
        width: 1fr;
        padding-left: 2;
    }

    .section-label {
        text-style: bold underline;
        margin-bottom: 1;
    }

    .picker-input {
        height: 5;
        border: inner $accent;
        margin: 1 0;
    }

    #picker-footer {
        height: 3;
        align: right middle;
        margin-top: 1;
    }
    
    #recommendation-label {
        width: 1fr;
        padding-left: 1;
        content-align: left middle;
    }
    
    .review-suggestion {
        color: $warning;
        text-style: bold italic;
    }
    
    .next-suggestion {
        color: $success;
        text-style: italic;
    }

    #select-dialog, #options-dialog, #help-dialog {
        background: $panel;
        border: thick $primary;
        padding: 1 2;
        width: 60;
        height: auto;
        align: center middle;
    }
    
    #help-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
        width: 100%;
        content-align: center middle;
    }
    
    #help-footer {
        color: $text-muted;
        margin-top: 1;
        width: 100%;
        content-align: center middle;
    }

    .small-input {
        height: 3;
        border: inner $accent;
        margin: 1 0;
    }
    
    .large-input {
        height: 15;
        border: inner $accent;
        margin: 1 0;
    }

    #problem-list {
        height: 10;
        border: inner $accent;
        margin: 1 0;
    }

    #status-bar {
        background: $primary;
        color: white;
        padding: 0 1;
        height: 1;
        dock: top;
        text-style: bold;
    }

    #status-bar.pass {
        background: $success;
        color: white;
    }

    #status-bar.fail {
        background: $error;
        color: white;
    }

    #notes-container {
        padding: 2;
    }

    #manual-notes-list {
        height: auto;
        border: inner $accent;
        margin-top: 1;
    }

    #command-ribbon {
        background: $primary-darken-2;
        color: $text;
        height: 1;
        dock: bottom;
    }
    
    #command-ribbon Label {
        padding: 0 1;
        background: $primary;
        color: white;
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+p", "push_screen('problem_picker')", "Problems"),
        Binding("ctrl+n", "push_screen('notes')", "Notes"),
        Binding("ctrl+h", "get_hint", "Hint"),
        Binding("ctrl+g", "run_tests", "Submit"),
        Binding("ctrl+r", "get_review", "Review"),
        Binding("ctrl+o", "push_screen('options')", "Options"),
        Binding("/", "focus_command", "Command"),
        Binding("f2", "push_screen('stats')", "Stats"),
        Binding("escape", "focus_editor", "Focus Editor"),
        Binding("ctrl+s", "run_tests", "Run Tests"),
        Binding("ctrl+m", "toggle_mode", "Toggle Mode"),
        Binding("?", "push_screen('help')", "Help"),
    ]

    SCREENS = {
        "startup": StartupScreen,
        "problem_picker": ProblemPickerScreen,
        "fix_entry": FixModeEntryScreen,
        "notes": NotesScreen,
        "options": OptionsScreen,
        "stats": StatsScreen,
        "help": HelpOverlay
    }

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Status: Ready", id="status-bar")
        with Container(id="app-container"):
            with ScrollableContainer(id="problem-pane"):
                yield Markdown("", id="problem-markdown")
            
            with Vertical(id="editor-pane"):
                with Horizontal(id="main-editor-container"):
                    yield SlopGutter(id="main-gutter")
                    yield PythonEditor(language="python", id="code-editor", show_line_numbers=True, tab_behavior="indent")
                
                with Horizontal(id="slop-container"):
                    with Horizontal(id="slop-left-container"):
                        yield SlopGutter(id="slop-gutter")
                        yield TextArea(id="slop-left", read_only=True)
                    yield PythonEditor(language="python", id="slop-right", show_line_numbers=True, tab_behavior="indent")
            
            with Vertical(id="ai-pane"):
                with ScrollableContainer(id="ai-content"):
                    with Horizontal(id="ai-header-row"):
                        yield Label("AI Coach", classes="ai-coach-header")
                        yield Label("Timer: 00:00", id="struggle-timer")
                    
                    yield Label("Try solving first. Stuck?")
                    with Vertical(classes="ai-coach-buttons"):
                        yield Button("Hint", id="coach-hint-btn")
                        yield Button("Explain Problem", id="coach-explain-btn")
                        yield Button("Discuss Approach", id="coach-approach-btn")
                    
                    yield Label("Recent Interactions:", id="ai-recent-header")
                    yield Markdown("", id="ai-markdown")
                
                with Vertical(id="command-bar-container"):
                    yield CommandMenu(id="command-menu")
                    yield CommandBar(id="command-bar")
        
        with Horizontal(id="command-ribbon"):
            yield Label("^P Problems")
            yield Label("^N New")
            yield Label("^H Hint")
            yield Label("^G Submit")
            yield Label("^S Run Tests")
            yield Label("^R Review")
            yield Label("^O Options")
            yield Label("F2 Stats")
            
        yield Footer()

    def on_mount(self) -> None:
        # Set border titles
        self.query_one("#problem-pane").border_title = "Problem"
        self.query_one("#ai-pane").border_title = "AI Panel"
        
        # Watch cursor for slop issues
        self.watch(self.query_one("#slop-left"), "cursor_location", self._on_slop_cursor_move)
        self.watch(self.query_one("#code-editor"), "cursor_location", self._on_main_cursor_move)
        
        # Watch scroll for gutter sync
        self.watch(self.query_one("#code-editor"), "scroll_y", self._sync_main_gutter)
        self.watch(self.query_one("#slop-left"), "scroll_y", self._sync_slop_gutter)

        self.hint_count = 0
        self.last_hint_time = 0.0
        self._timer_task = None
        self._auto_save_task = None
        self._last_saved_code = ""
        self._first_keystroke_logged = False
        self._load_timestamp = None
        self._last_failure_type = None
        self._time_to_first_keystroke = 0.0
        self._slop_issues = {}
        self._main_lint_issues = {}
        # self.mode is already set in cli.py if flags were used

        self.provider_name = self.db.get_setting("ai_provider", "ollama")
        
        # Immediate editor focus
        self.query_one("#code-editor").focus()
        
        def on_startup_done(mode: str) -> None:
            if mode:
                self.mode = mode
                self.update_status(f"Mode: {self.mode}")
                self.update_layout_for_mode()
                # If dsa or sql, push problem select
                if mode in ["DSA", "SQL"]:
                    self.push_screen("problem_picker")
                elif mode == "FixSlop":
                    def on_fix_entry(entry_mode: str) -> None:
                        if entry_mode:
                            self.entry_mode = entry_mode
                            if entry_mode == "paste":
                                asyncio.create_task(self.action_paste_slop())
                            else:
                                asyncio.create_task(self.action_generate_slop_prompt())
                    self.push_screen("fix_entry", on_fix_entry)

        if hasattr(self, 'problem') and self.problem is not None:
            self.update_layout_for_mode()
            if isinstance(self.problem, SQLProblem):
                self.load_sql_problem(self.problem)
            else:
                self.load_problem(self.problem)
        else:
            # Check if mode was set explicitly
            if hasattr(self, 'mode_explicit') and self.mode_explicit:
                self.update_layout_for_mode()
                if self.mode in ["DSA", "SQL"]:
                    self.push_screen("problem_picker")
            else:
                self.push_screen("startup", on_startup_done)

    def _sync_main_gutter(self, scroll_y: float) -> None:
        self.query_one("#main-gutter", SlopGutter).sync_scroll(int(scroll_y))

    def _sync_slop_gutter(self, scroll_y: float) -> None:
        self.query_one("#slop-gutter", SlopGutter).sync_scroll(int(scroll_y))

    def update_editor_lint(self, issues: List[Dict]) -> None:
        """Update the main editor gutter with linting results."""
        self._main_lint_issues = {int(i["line"]): i["message"] for i in issues}
        self.query_one("#main-gutter", SlopGutter).update_markers(issues)

    def _on_main_cursor_move(self, location) -> None:
        """Show linting messages in the status bar when the cursor moves."""
        if self.mode == "DSA" and hasattr(self, "_main_lint_issues"):
            line = location[0] + 1
            if line in self._main_lint_issues:
                self.update_status(f"Lint: {self._main_lint_issues[line]}")
            else:
                self.update_status(f"Problem: {self.problem.title if self.problem else 'Ready'}")

    def _on_slop_cursor_move(self, location) -> None:
        if self.mode == "FixSlop" and self._slop_issues:
            line = location[0] + 1 # 1-indexed
            if line in self._slop_issues:
                self.update_status(f"Issue: {self._slop_issues[line]}")
            else:
                self.update_status("Fix AI Slop Mode")

    def load_problem(self, problem) -> None:
        self.problem = problem
        self.hint_count = 0
        self.last_hint_time = 0.0
        self._first_keystroke_logged = False
        self._load_timestamp = time.time()
        
        # Start DB session for timer
        self.db.start_session(problem.id)
        self._restart_timer()
        self._restart_auto_save()
        
        telemetry.log_event(self.db, "problem_loaded", problem.id, self.mode)

        # Enhanced spacing for better scanability
        content = f"# {problem.title}\n\n"
        content += f"**Difficulty:** {problem.difficulty}\n"
        content += f"**Topic:** {problem.topic}\n\n"
        content += "---\n\n"  # Visual separator
        content += f"{problem.description}\n\n"
        content += "### Constraints\n\n"
        for c in problem.constraints:
            content += f"- {c}\n"
        
        self.query_one("#problem-markdown", Markdown).update(content)
        
        draft = self.db.get_draft(self.problem.id)
        self._last_saved_code = draft if draft else ""
        editor = self.query_one("#code-editor", PythonEditor)
        editor.text = draft if draft else "# Write your solution here\n"
        editor._refresh_indent_settings()
        
        # Educational empty state
        self.query_one("#ai-markdown", Markdown).update(
            "*No interactions yet.*\n\n**Try asking:**\n- 'Give a small hint'\n- 'Explain the brute force approach'\n- 'Why use a hash map here?'"
        )
        self.update_status(f"Problem: {problem.title}")

    def _restart_timer(self) -> None:
        if self._timer_task:
            self._timer_task.cancel()
        
        async def update_timer():
            while True:
                start_time = self.db.get_start_time(self.problem.id)
                if start_time:
                    from datetime import datetime
                    elapsed = datetime.now() - start_time
                    minutes, seconds = divmod(int(elapsed.total_seconds()), 60)
                    self.query_one("#struggle-timer", Label).update(f"Timer: {minutes:02d}:{seconds:02d}")
                await asyncio.sleep(1)
        
        self._timer_task = asyncio.create_task(update_timer())

    def _restart_auto_save(self) -> None:
        if self._auto_save_task:
            self._auto_save_task.cancel()
            
        async def auto_save_loop():
            while True:
                await asyncio.sleep(30)
                if hasattr(self, "problem") and self.problem:
                    editor = self.query_one("#code-editor", PythonEditor)
                    current_code = editor.text
                    if current_code != self._last_saved_code:
                        self.db.save_draft(self.problem.id, current_code)
                        self._last_saved_code = current_code
                        self.notify("Draft auto-saved", timeout=1.5)
        
        self._auto_save_task = asyncio.create_task(auto_save_loop())

    def action_focus_command(self) -> None:
        self.query_one("#command-bar").focus()
    
    def on_editor_keystroke(self) -> None:
        if not self._first_keystroke_logged and self._load_timestamp and hasattr(self, 'problem') and self.problem:
            self._first_keystroke_logged = True
            self._time_to_first_keystroke = (time.time() - self._load_timestamp)
            telemetry.log_event(self.db, "keystroke_first", self.problem.id, self.mode, {"time_elapsed_seconds": self._time_to_first_keystroke})

    def action_focus_editor(self) -> None:
        self.query_one("#code-editor").focus()

    def action_toggle_mode(self) -> None:
        modes = ["DSA", "SQL", "FixSlop"]
        current_idx = modes.index(self.mode)
        self.mode = modes[(current_idx + 1) % len(modes)]
        self.notify(f"Mode switched to: {self.mode}")
        self.update_status(f"Mode: {self.mode}")
        self.update_layout_for_mode()

    async def action_paste_slop(self) -> None:
        if self.mode != "FixSlop":
            self.notify("Switch to FixSlop mode first", severity="warning")
            return
            
        async def on_pasted(text: str) -> None:
            if text:
                self.query_one("#slop-left").text = text
                await self.analyze_slop(text)
        
        self.push_screen(PasteModal(), on_pasted)

    async def action_generate_slop_prompt(self) -> None:
        if self.mode != "FixSlop":
            self.notify("Switch to FixSlop mode first", severity="warning")
            return
            
        async def on_statement(text: str) -> None:
            if text:
                await self.generate_slop(text)
        
        self.push_screen(ProblemStatementModal(), on_statement)

    async def generate_slop(self, statement: str) -> None:
        self.notify("AI: Generating sloppy code...")
        md_widget = self.query_one("#ai-markdown", Markdown)
        md_widget.update("### Generating Slop\n\n*Thinking...* ▌")
        
        full_text = ""
        try:
            async for chunk in self.app.ai.generate_slop(statement):
                full_text += chunk
                # For slop generation, we might want to just update the left pane after it's done
                # or stream it into the left pane. Let's stream it into the left pane.
                self.query_one("#slop-left").text = full_text
            
            await self.analyze_slop(full_text)
        except Exception as e:
            self.report_error(e, "Slop Generation")

    async def action_submit_slop(self) -> None:
        original = self.query_one("#slop-left").text
        rewrite = self.query_one("#slop-right").text

        if not original.strip():
            self.notify("No original code to validate", severity="warning")
            return

        md_widget = self.query_one("#ai-markdown", Markdown)
        md_widget.update("### Validation Verdict\n\n*Comparing solutions...* ▌")

        full_text = "### Validation Verdict\n\n"
        try:
            async for chunk in self.ai.validate_fix(original, rewrite):
                full_text += chunk
                md_widget.update(full_text + " ▌")
            md_widget.update(full_text)
        except Exception as e:
            self.report_error(e, "Fix Validation")

    async def analyze_slop(self, code: str) -> None:
        self.notify("AI: Analyzing slop...")
        md_widget = self.query_one("#ai-markdown", Markdown)
        md_widget.update("### Slop Analysis\n\n*Analyzing issues...* ▌")
        
        full_json = ""
        try:
            async for chunk in self.app.ai.analyze_slop(code):
                full_json += chunk
            
            issues = json.loads(full_json)
            # Store issues for reference when cursor moves
            self._slop_issues = {int(i["line"]): i["message"] for i in issues}
            
            # Update Gutter
            self.query_one("#slop-gutter", SlopGutter).update_markers(issues)
            
            # Summary for AI Pane
            red = sum(1 for i in issues if i["severity"] == "red")
            yellow = sum(1 for i in issues if i["severity"] == "yellow")
            green = sum(1 for i in issues if i["severity"] == "green")
            
            summary = f"**{red} critical** · **{yellow} warnings** · **{green} style**"
            md_widget.update(f"### Slop Analysis\n\n{summary}\n\n*Hover/Select line in left pane to see details.*")
            
        except Exception as e:
            self.report_error(e, "Slop Analysis")
    def update_layout_for_mode(self) -> None:
        editor = self.query_one("#code-editor")
        slop_container = self.query_one("#slop-container")
        
        if self.mode == "FixSlop":
            editor.display = False
            slop_container.display = True
            self.query_one("#problem-pane").border_title = "Fix AI Slop"
            self.query_one("#problem-markdown", Markdown).update(
                "# Fix AI Slop Mode\n\n1. Paste AI-generated code (`Ctrl+V` or `/paste`)\n2. AI will annotate correctness, slop, and style\n3. Rewrite it on the right\n4. `/submit` to validate your fix"
            )
        elif self.mode == "SQL":
            editor.display = True
            slop_container.display = False
            editor.language = "sql"
            self.query_one("#problem-pane").border_title = "SQL Schema"
            if not isinstance(self.problem, SQLProblem):
                if self.sql_bank.problems:
                    self.load_sql_problem(self.sql_bank.problems[0])
                else:
                    self.notify("No SQL problems found in data/sql/", severity="warning")
        else: # DSA
            editor.display = True
            slop_container.display = False
            editor.language = "python"
            self.query_one("#problem-pane").border_title = "Problem"
            if isinstance(self.problem, SQLProblem) or self.problem is None:
                if self.bank.problems:
                    self.load_problem(self.bank.problems[0])

    def load_sql_problem(self, problem: SQLProblem) -> None:
        self.problem = problem
        self.hint_count = 0
        self.last_hint_time = 0.0
        self.db.start_session(problem.id)
        self._restart_timer()
        self._restart_auto_save()

        content = f"# {problem.title}\n\n"
        content += f"**Difficulty:** {problem.difficulty} | **Category:** {problem.category}\n\n"
        content += f"{problem.description}\n\n"
        content += "### Schema Definition\n\n"
        content += "```sql\n" + problem.schema_definition + "\n```\n\n"
        
        self.query_one("#problem-markdown", Markdown).update(content)
        
        draft = self.db.get_draft(problem.id)
        self._last_saved_code = draft if draft else ""
        editor = self.query_one("#code-editor", PythonEditor)
        editor.text = draft if draft else "-- Write your SQL query here\n"
        editor.language = "sql"
        editor._refresh_indent_settings()
        
        self.query_one("#ai-markdown", Markdown).update(
            "*SQL mode active.*\n\nAsk about JOINs, window functions, or query plans."
        )
        self.update_status(f"SQL: {problem.title}")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "command-bar":
            cmd = event.value.strip()
            event.input.value = "" # Clear input
            
            if not cmd:
                return
            
            if cmd.startswith("/"):
                # Handle slash commands
                parts = cmd[1:].split()
                base = parts[0].lower()
                
                if base == "hint":
                    await self.action_get_hint()
                elif base == "review":
                    await self.action_get_review()
                elif base == "submit":
                    if self.mode == "FixSlop":
                        await self.action_submit_slop()
                    else:
                        await self.action_submit()
                elif base == "paste":
                    await self.action_paste_slop()
                elif base in ["test", "run"]:
                    await self.action_run_tests()
                elif base == "clear":
                    self.query_one("#ai-markdown", Markdown).update("*Cleared*")
                elif base == "explain":
                    await self.stream_ai_response("explain")
                elif base == "note":
                    content = " ".join(parts[1:])
                    if content:
                        notes.add_note(self.db, self.problem.id, self.mode, content, source="manual")
                        self.notify("Note saved.", severity="information")
                    else:
                        self.notify("Note content cannot be empty", severity="warning")
                else:
                    self.notify(f"Unknown command: /{base}", severity="warning")
            else:
                # Direct question
                await self.action_ask_ai(cmd)

    async def action_generate_cmd(self, args: List[str]) -> None:
        if not self.check_ready(): return
        
        mode = "random"
        topic = "Any"
        if args:
            sub = args[0].lower()
            if sub == "specific":
                mode = "specific"
                topic = " ".join(args[1:]) if len(args) > 1 else "Two Sum"
            elif sub == "something":
                mode = "suggested"
            else:
                mode = "random"
                topic = " ".join(args)

        self.notify(f"AI: Generating {mode} problem...")
        try:
            problem_dict = await self.ai.generate_problem(mode=mode, topic=topic)
            from .models import Problem
            new_problem = Problem.from_dict(problem_dict)
            self.bank.save_problem(new_problem)
            self.notify(f"Success! '{new_problem.title}' added.", severity="information")
            self.load_problem(new_problem)
        except Exception as e:
            self.notify(f"Generation Error: {str(e)}", severity="error")

    async def action_ask_ai(self, question: str) -> None:
        if not self.check_ready(): return
        
        md_widget = self.query_one("#ai-markdown", Markdown)
        md_widget.update(f"**Q:** {question}\n\n*Thinking...* ▌")
        
        full_text = f"**Q:** {question}\n\n"
        try:
            code = self.query_one("#code-editor", PythonEditor).text
            async for chunk in self.ai.ask_question(self.problem.description, code, question, mode=self.mode):
                full_text += chunk
                md_widget.update(full_text + " ▌")
            md_widget.update(full_text)
        except Exception as e:
            self.report_error(e, "AI Interaction")

    def update_status(self, message: str) -> None:
        self.query_one("#status-bar", Static).update(f"Status: {message}")

    def report_error(self, error: Exception, context: str = "") -> None:
        """Surface error details in the AI pane for visibility."""
        message = f"### ⚠️ Error: {context}\n\n{str(error)}"
        if hasattr(error, "__notes__"): # Python 3.11+
            message += "\n".join(error.__notes__)
        
        self.query_one("#ai-markdown", Markdown).update(message)
        self.notify(f"Error: {context}", severity="error")

    def update_ai_provider(self, provider: str, model: str) -> None:
        self.provider_name = provider
        api_key = ""
        if provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY", "")
            self.ai = GeminiProvider(api_key, model_name=model)
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            self.ai = AnthropicProvider(api_key, model_name=model)
        elif provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "")
            self.ai = OpenAIProvider(api_key, model_name=model)
        else:
            self.ai = OllamaProvider(model_name=model)
        
        self.notify(f"AI: {provider} ({model})")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "coach-hint-btn":
            await self.action_get_hint()
        elif event.button.id == "coach-explain-btn":
            await self.stream_ai_response("explain")
        elif event.button.id == "coach-approach-btn":
            await self.stream_ai_response("approach")

    async def stream_ai_response(self, action_type: str) -> None:
        if not self.check_ready(): return
        
        md_widget = self.query_one("#ai-markdown", Markdown)
        md_widget.update("Thinking... ▌")
        full_text = ""
        
        try:
            code = self.query_one("#code-editor", PythonEditor).text
            if action_type == "explain":
                prompt = f"Explain the following DSA problem clearly: {self.problem.description}"
            else: # approach
                prompt = f"Discuss a good algorithmic approach for this problem: {self.problem.description}"
            
            # Using stream_hint for general discussion
            async for chunk in self.ai.stream_hint(self.problem.description, code, [{"role": "user", "content": prompt}], mode=self.mode):
                full_text += chunk
                md_widget.update(full_text + " ▌")
            md_widget.update(full_text)
        except Exception as e:
            self.report_error(e, "AI Interaction")

    async def action_get_hint(self) -> None:
        if not self.check_ready(): return
        
        now = time.time()
        start_time = self.db.get_start_time(self.problem.id)
        from datetime import datetime
        elapsed_min = (datetime.now() - start_time).total_seconds() / 60 if start_time else 0
        
        hint_level = 1
        if elapsed_min > 8:
            hint_level = 2
        elif elapsed_min < 5:
            # We allow it, but it's just a nudge
            pass

        if self.hint_count >= 3:
            self.notify("Hint limit reached (max 3 per problem)", severity="warning")
            return
            
        elapsed_since_last = now - self.last_hint_time
        if elapsed_since_last < 30:
            remaining = int(30 - elapsed_since_last)
            self.notify(f"Please wait {remaining}s before next hint", severity="warning")
            return

        md_widget = self.query_one("#ai-markdown", Markdown)
        md_widget.update("Thinking... ▌") # Pulsing cursor start
        full_text = ""
        
        try:
            self.hint_count += 1
            self.last_hint_time = now
            telemetry.log_event(self.db, "hint_used", self.problem.id, self.mode, {"hint_level": hint_level})
            code = self.query_one("#code-editor", PythonEditor).text
            async for chunk in self.ai.stream_hint(self.problem.description, code, [], level=hint_level, mode=self.mode):
                full_text += chunk
                md_widget.update(full_text + " ▌") # Keep cursor
            md_widget.update(full_text) # Remove cursor at end
            self.update_status(f"Hint {self.hint_count}/3 used")
        except Exception as e:
            self.hint_count -= 1  # Revert if failed
            self.report_error(e, "AI Interaction")

    async def action_get_review(self) -> None:
        if not self.check_ready(): return
        
        start_time = self.db.get_start_time(self.problem.id)
        from datetime import datetime
        elapsed_min = (datetime.now() - start_time).total_seconds() / 60 if start_time else 0
        
        if elapsed_min < 15:
            remaining = int(15 - elapsed_min)
            self.notify(f"Review unlocks in {remaining} minutes. Keep struggling!", severity="warning")
            return

        md_widget = self.query_one("#ai-markdown", Markdown)
        md_widget.update("Reviewing code... ▌")
        full_text = "### AI Code Review\n\n"
        
        try:
            async for chunk in self.ai.review_code(self.problem.description, self.query_one("#code-editor", PythonEditor).text, mode=self.mode):
                full_text += chunk
                md_widget.update(full_text + " ▌")
            md_widget.update(full_text)
        except Exception as e:
            self.report_error(e, "AI Interaction")

    async def action_run_tests(self) -> None:
        if not self.check_ready(): return
        
        # Explicitly get the most fresh text from the widget
        editor = self.query_one("#code-editor", PythonEditor)
        code = editor.text
        
        # Explicit save before running tests
        self.db.save_draft(self.problem.id, code)
        
        if self.mode == "SQL":
            self.update_status("Running SQL query...")
            results = self.sql_sandbox.run_test_cases(code, self.problem)
        else:
            self.update_status(f"Running tests on {len(code)} chars...")
            results = self.sandbox.run_test_cases(code, self.problem)
        
        passed_count = sum(1 for r in results if r['passed'])
        total = len(results)
        
        # Color-coded status signal
        status_bar = self.query_one("#status-bar", Static)
        status_bar.remove_class("pass", "fail")
        if passed_count == total:
            status_bar.add_class("pass")
            self.update_status(f"PASSED ({passed_count}/{total})")
            telemetry.log_event(self.db, "test_passed", self.problem.id, self.mode, {"passed_count": passed_count, "total": total})
            
            # Phase B.3: Record submission in profile
            profiler = UserProfiler(self.db)
            profiler.record_submission(
                topic=self.problem.topic if hasattr(self.problem, 'topic') else self.problem.category,
                passed=True,
                hints_used=self.hint_count,
                time_to_first_keystroke=self._time_to_first_keystroke,
                failure_type=self._last_failure_type
            )
            
            # Phase D.2: Background AI insight
            async def generate_insight_and_save():
                try:
                    insight = await self.ai.generate_insight(code, self.problem.description)
                    if insight:
                        notes.add_note(self.db, self.problem.id, self.mode, insight, source="ai_generated")
                except:
                    pass
            
            asyncio.create_task(generate_insight_and_save())
        else:
            status_bar.add_class("fail")
            self.update_status(f"FAILED ({passed_count}/{total})")
            event_id = telemetry.log_event(self.db, "test_failed", self.problem.id, self.mode, {"passed_count": passed_count, "total": total})
            
            # Phase B.2: Background AI classification
            async def classify_and_update():
                try:
                    res_str = "\n".join([f"Test {i}: {'Pass' if r['passed'] else 'Fail'} - {r.get('error','')}" for i, r in enumerate(results)])
                    failure_type = await self.ai.classify_failure(code, self.problem.description, res_str)
                    self._last_failure_type = failure_type
                    telemetry.update_event_metadata(self.db, event_id, {"failure_type": failure_type})
                except:
                    pass # Silent failure for background telemetry
            
            asyncio.create_task(classify_and_update())
        
        res_text = "### Test Results\n\n"
        for i, res in enumerate(results):
            status = "[PASS]" if res['passed'] else "[FAIL]"
            res_text += f"{status} {res['runtime_ms']:.1f}ms\n"
            if not res['passed']:
                if res.get('error'):
                    res_text += f"   Error: {res['error']}\n"
                else:
                    res_text += f"   Expected: {res['expected']}\n   Actual: {res['actual']}\n"
        
        ai_content = self.query_one("#ai-content", ScrollableContainer)
        ai_markdown = self.query_one("#ai-markdown", Markdown)
        ai_markdown.update(res_text)
        
        # Auto-scroll to results
        ai_content.scroll_end(animate=False)

    async def action_submit(self) -> None:
        if not self.check_ready(): return
        
        code = self.query_one("#code-editor", PythonEditor).text
        results = self.sandbox.run_test_cases(code, self.problem)
        all_passed = all(r['passed'] for r in results)
        
        self.db.add_submission(self.problem.id, self.problem.topic, code, all_passed, sum(r['runtime_ms'] for r in results))
        
        if all_passed:
            self.notify("Submission SUCCESS!", severity="information")
        else:
            self.notify("Submission FAILED.", severity="error")
            
        await self.action_get_review()

    async def action_open_vim(self) -> None:
        """Launch external Vim to edit the current code."""
        if not hasattr(self, "problem"):
            self.notify("Select a problem first", severity="error")
            return

        editor_cmd = os.environ.get("EDITOR", "vim")
        current_code = self.query_one("#code-editor", PythonEditor).text
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as tf:
            tf.write(current_code)
            temp_path = tf.name

        try:
            with self.suspend():
                subprocess.run([editor_cmd, temp_path], check=True)
            with open(temp_path, "r") as f:
                new_code = f.read()
                if new_code != current_code:
                    self.query_one("#code-editor", PythonEditor).text = new_code
                    self.db.save_draft(self.problem.id, new_code)
            self.notify("Sync'd from Vim!")
        except Exception as e:
            self.notify(f"Editor error: {str(e)}", severity="error")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        pass

    def check_ready(self) -> bool:
        if not hasattr(self, "problem") or not self.problem:
            self.notify("Select a problem first", severity="error")
            return False
        if not self.ai:
            self.notify("AI not configured", severity="error")
            return False
        return True
