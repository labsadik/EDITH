from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProductContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = (ROOT / "ui.py").read_text(encoding="utf-8")
        cls.main = (ROOT / "main.py").read_text(encoding="utf-8")
        cls.llm_client = (ROOT / "core" / "llm_client.py").read_text(encoding="utf-8")
        cls.scheduler = (ROOT / "core" / "task_scheduler.py").read_text(encoding="utf-8")
        cls.prompt = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
        cls.app = (ROOT / "dashboard" / "static" / "app.html").read_text(encoding="utf-8")
        cls.login = (ROOT / "dashboard" / "static" / "login.html").read_text(encoding="utf-8")
        cls.readme = (ROOT / "readme.md").read_text(encoding="utf-8")

    def test_desktop_brand_is_edith_and_not_user_customizable(self):
        self.assertIn('UI_BRAND = "EDITH"', self.ui)
        self.assertIn('self.setWindowTitle("EDITH • PERSONAL ASSISTANT")', self.ui)
        self.assertIn('self._sub_lbl.setText("PERSONAL ASSISTANT SYSTEM  •  VOICE  •  VISION")', self.ui)
        self.assertNotIn("self._name_input", self.ui)
        self.assertNotIn("MARK LI", self.ui)
        self.assertIn("EDITH SYSTEMS", self.ui)
        self.assertNotIn("EVEN DEAD, I'M THE HERO", self.ui)

    def test_hud_uses_a_neutral_generated_visual(self):
        self.assertIn("self._face_px = None", self.ui)
        self.assertIn("def _build_assistant_icon(", self.ui)
        self.assertIn('config" / "edith.ico"', self.ui)
        self.assertIn('svg_icon("edith-app"', self.ui)
        self.assertNotIn('config" / "jarvis.ico', self.ui)

    def test_gemini_model_and_actual_voice_switch_logic(self):
        self.assertIn('LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"', self.main)
        self.assertIn('VOICE_PRESETS       = {"female": "Kore", "male": "Orus"}', self.main)
        self.assertIn('"name": "set_voice_mode"', self.main)
        self.assertIn('voice_name=voice_name', self.main)
        self.assertIn('self._reconfigure_event.set()', self.main)
        self.assertIn('self._voice_confirmation', self.main)
        self.assertIn("Use the configured female voice", self.main)
        self.assertIn("Use the configured male voice", self.main)

    def test_key_editor_validates_against_live_api_before_saving(self):
        self.assertIn("class ApiKeyOverlay(QWidget):", self.ui)
        self.assertIn("client.aio.live.connect(", self.ui)
        self.assertIn("self._save_btn.setEnabled(False)", self.ui)
        self.assertIn("save_gemini_api_key(key, API_FILE)", self.ui)
        self.assertIn("get_gemini_api_key(API_FILE)", self.ui)
        self.assertIn("open_api_key_settings_signal", self.ui)
        self.assertIn("self._request_api_key_reconnect", self.main)

    def test_api_panel_shows_provider_model_local_status_and_real_response_latency(self):
        self.assertIn("LLM & API CONNECTION", self.ui)
        self.assertIn("Google Gemini Live API", self.ui)
        self.assertIn("models/gemini-2.5-flash-native-audio-preview-12-2025", self.ui)
        self.assertIn("LOCAL AGENT PROVIDER", self.ui)
        self.assertIn("LOCAL AGENT MODEL", self.ui)
        self.assertIn("LOCAL AGENT ENDPOINT", self.ui)
        self.assertIn("LOCAL AGENT CONNECTION", self.ui)
        self.assertIn("LOCAL MODEL INFERENCE", self.ui)
        self.assertIn("CLOUD API LAST TEST", self.ui)
        self.assertIn("await session.send_client_content(", self.ui)
        self.assertIn("session.receive()", self.ui)
        self.assertIn("time.perf_counter()", self.ui)
        self.assertIn("TEST LOCAL LLM", self.ui)
        self.assertIn("from core.llm_client import get_llm_provider, get_llm_settings", self.ui)
        self.assertIn("from core.llm_client import call_llm, get_llm_provider, get_llm_settings", self.ui)
        self.assertIn('"llm_provider"', self.llm_client)
        self.assertIn('"llm_url"', self.llm_client)
        self.assertIn('"llm_model"', self.llm_client)
        self.assertIn('def get_llm_provider(profile: str = "powerful")', self.llm_client)
        self.assertIn('def get_llm_settings(profile: str = "powerful")', self.llm_client)
        self.assertIn("def call_llm(", self.llm_client)
        self.assertNotIn("self._local_endpoint", self.ui)

    def test_prompt_includes_brief_progress_without_repeated_confirmation(self):
        self.assertIn("LOW-LATENCY BEHAVIOR", self.prompt)
        self.assertIn("one brief progress sentence", self.prompt)
        self.assertIn("Never sacrifice target verification", self.prompt)

    def test_prompt_is_action_focused_and_voice_aware(self):
        self.assertIn("set_voice_mode", self.prompt)
        self.assertIn("female", self.prompt.lower())
        self.assertIn("male", self.prompt.lower())
        self.assertIn("start the relevant action immediately", self.prompt)
        self.assertIn("Never claim an action succeeded until the tool confirms success", self.prompt)

    def test_remote_pages_use_edith_visible_branding(self):
        self.assertIn("<title>EDITH • Remote</title>", self.app)
        self.assertIn('<div class="logo">EDITH</div>', self.app)
        self.assertIn("<title>EDITH • Remote Access</title>", self.login)
        self.assertIn('<div class="logo">EDITH</div>', self.login)
        for content in (self.app, self.login):
            self.assertNotIn("MARK LI", content)
            self.assertNotIn("Tony Stark", content)

    def test_existing_remote_protocol_contract_is_retained(self):
        # These identifiers are internal compatibility keys, not visible branding.
        self.assertIn("jarvis_token", self.app)
        self.assertIn("jarvis_key", self.app)
        self.assertIn("JARVIS-DASHBOARD-v1", self.app)
        self.assertIn("jarvis_device_token", self.login)
        self.assertIn("speaker === 'jarvis'", self.app)

    def test_cross_app_discovery_and_visible_screen_verification_are_wired(self):
        self.assertIn('"name": "open_app"', self.main)
        self.assertIn('"enum": ["open", "list", "search"]', self.main)
        self.assertIn('"force": {"type": "BOOLEAN"', self.main)
        self.assertIn('self.ui.show_content("INSTALLED DESKTOP APPS", result)', self.main)
        self.assertIn('force=true', self.prompt)
        self.assertIn("computer_control affects the actual foreground desktop", self.prompt)

    def test_ui_uses_bundled_svg_controls_instead_of_emoji(self):
        self.assertIn("from core.icons import svg_icon", self.ui)
        self.assertIn('_set_theme_icon(self._mute_btn, "mic", "GREEN")', self.ui)
        self.assertIn('_set_theme_icon(self._drawer_btn, "settings", "PRI")', self.ui)
        self.assertNotIn("Segoe UI Emoji", self.ui)
        for glyph in ("🎙", "🔇", "🧩", "🐧", "☀"):
            self.assertNotIn(glyph, self.ui)

    def test_generic_close_will_not_target_the_edith_window_itself(self):
        self.assertIn("Do not interpret a generic request as permission to close", self.main)
        self.assertIn('"edith" in foreground_key', self.main)

    def test_phase3_scheduler_wired_to_existing_live_api_and_ui(self):
        self.assertIn("from core.task_scheduler", self.main)
        self.assertIn("async def _execute_tool_batch(", self.main)
        self.assertIn("await self._execute_tool_batch(", self.main)
        self.assertIn("parallel_read_only(fc.name", self.main)
        self.assertIn("TaskReportedFailure", self.main)
        self.assertIn("self._task_scheduler.run_batch(specs)", self.main)
        self.assertIn("task_status_signal", self.ui)
        self.assertIn("CANCEL WAITING", self.ui)
        self.assertIn("on_cancel_queued_tasks", self.ui)
        self.assertIn("def cancel_queued(", self.scheduler)
        self.assertIn("max_concurrency: int = 4", self.scheduler)
        self.assertIn("if spec.exclusive:", self.scheduler)
        self.assertIn("Dependency did not succeed", self.scheduler)
        self.assertIn("MULTITASKING AND TASK DEPENDENCIES", self.prompt)
        # All specialist text inference defaults to the single Powerful Brain profile.
        self.assertIn('def get_llm_provider(profile: str = "powerful")', self.llm_client)
        self.assertIn("def call_llm_text(", self.llm_client)
        self.assertIn("def call_llm_stream(", self.llm_client)
        self.assertIn("models/gemini-2.5-flash-native-audio-preview-12-2025", self.main)

    def test_full_end_to_end_testing_checklist_is_linked(self):
        self.assertIn("TESTING.md", self.readme)

    def test_neuron_intelligence_identity_and_handsfree_policy(self):
        self.assertIn("Neuron Intelligence", self.prompt)
        self.assertIn("Sadik Laskar", self.prompt)
        self.assertIn("PRODUCT_IDENTITY.instruction()", self.main)
        self.assertIn("Do not reveal backend provider names", self.prompt)
        self.assertIn("without asking the user to confirm it again", self.prompt)
        self.assertIn("delete_permanent", self.prompt)
        self.assertIn("PROMPT-INJECTION AND DATA HANDLING", self.prompt)
        self.assertIn("confirmation_requirement(name, args)", self.main)
        self.assertIn("ACTIVITY RUNNING", self.main)

    def test_youtube_channel_search_is_distinct_from_video_playback(self):
        self.assertIn('"channel"', self.main)
        self.assertIn("Use action=channel when the user asks to search/find a channel", self.prompt)
        self.assertIn('"enum": ["play", "channel", "summarize", "get_info", "trending"]', self.main)

    def test_filesystem_tasks_route_to_file_controller_not_code_helper(self):
        self.assertIn("create_folders", self.main)
        self.assertIn('"names":       {"type": "ARRAY"', self.main)
        self.assertIn("always use file_controller rather than code_helper", self.main)
        self.assertIn("Never call code_helper or dev_agent just to create/manage ordinary folders or files", self.prompt)
        self.assertIn('action=create_folders', self.prompt)

    def test_documentation_explains_voice_and_key_management(self):
        self.assertIn("Kore", self.readme)
        self.assertIn("Orus", self.readme)
        self.assertIn("test the key", self.readme.lower())
        self.assertIn("Upgrade_Autonomous.git", self.readme)
        self.assertIn("Cross-app desktop control", self.readme)
        self.assertIn("List installed desktop apps.", self.readme)
        self.assertIn("foreground-window label matches", self.readme)


if __name__ == "__main__":
    unittest.main()


