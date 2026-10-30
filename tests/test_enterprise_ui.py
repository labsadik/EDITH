"""Behavioral gates for the desktop workspace; no API or hardware requests."""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import ui
            from PyQt6.QtWidgets import QApplication
        except ImportError as exc:
            if os.environ.get('CI') == 'true':
                raise
            raise unittest.SkipTest(str(exc))
        cls.ui = ui
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = tempfile.TemporaryDirectory()
        cls.original = ui.API_FILE
        ui.API_FILE = Path(cls.tmp.name) / 'api_keys.json'
        ui.API_FILE.write_text(json.dumps({'gemini_api_key': 'test', 'os_system': 'Linux'}))

    @classmethod
    def tearDownClass(cls):
        cls.ui.API_FILE = cls.original
        cls.tmp.cleanup()

    def setUp(self):
        self.window = self.ui.MainWindow('')
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()


    def test_modern_workspace_surfaces_and_provider_panels(self):
        from PyQt6.QtWidgets import QFrame, QScrollArea, QTabWidget, QPushButton
        from ui import PluginManagerOverlay, ProviderSettingsOverlay

        self.assertIn("border-radius: 18px", self.window._left_panel.styleSheet())
        self.assertIn("border-radius: 18px", self.window._right_panel.styleSheet())
        self.assertIn("PERSONAL AI WORKSPACE", self.window._sub_lbl.text())

        provider = ProviderSettingsOverlay(parent=self.window.centralWidget())
        self.assertIsNotNone(provider._provider)
        self.assertIsNotNone(provider._url)
        self.assertIsNotNone(provider._model)
        self.assertIsNotNone(provider._key)
        provider.deleteLater()

        catalog = PluginManagerOverlay([
            {"name": "sample_mcp", "kind": "mcp", "icon": "MCP",
             "description": "Trusted connector", "valid": True, "enabled": False},
            {"name": "sample_tool", "kind": "python",
             "description": "Local tool", "valid": True, "enabled": True},
        ], parent=self.window.centralWidget())
        self.assertIsInstance(catalog._tabs, QTabWidget)
        self.assertEqual([catalog._tabs.tabText(i) for i in range(catalog._tabs.count())],
                         ["MCP SERVERS", "AGENTS"])
        self.assertEqual(len(catalog.findChildren(QScrollArea)), 2)
        self.assertEqual(len(catalog.findChildren(QFrame, "PluginCard")), 2)
        self.assertEqual(len(catalog._mcp_tab.findChildren(QFrame, "PluginCard")), 1)
        self.assertEqual(len(catalog._agents_tab.findChildren(QFrame, "PluginCard")), 1)
        self.assertTrue(any(button.accessibleName() == "Close Plugins manager"
                                for button in catalog.findChildren(QPushButton)))
        catalog.deleteLater()
        self.app.processEvents()

    def test_api_provider_workspace_has_four_test_gated_tabs(self):
        from PyQt6.QtWidgets import QTabWidget, QPushButton
        from ui import ApiProviderWorkspace

        overlay = ApiProviderWorkspace(parent=self.window.centralWidget())
        self.assertIsInstance(overlay._tabs, QTabWidget)
        self.assertEqual([overlay._tabs.tabText(i) for i in range(overlay._tabs.count())],
                         ["VOICE", "MAIN BRAIN", "POWERFUL BRAIN", "REAL-TIME SEARCH"])
        self.assertEqual(overlay._voice._provider.currentData(), "gemini_live")
        self.assertEqual(overlay._main_brain._provider.count(), 6)
        self.assertEqual(overlay._powerful_brain._provider.count(), 6)
        self.assertEqual(overlay._search._provider.count(), 4)
        for panel in (overlay._voice, overlay._main_brain, overlay._powerful_brain, overlay._search):
            self.assertFalse(panel._save_btn.isEnabled())
        self.assertTrue(any(button.accessibleName() == "Close API Providers"
                            for button in overlay.findChildren(QPushButton)))
        overlay.deleteLater()
        self.app.processEvents()

    def test_preferences_no_longer_exposes_manual_colour_adjustments(self):
        self.window._open_customize()
        panel = self.window._customize_overlay
        self.assertFalse(hasattr(panel, "_wheel"))
        self.assertFalse(hasattr(panel, "_hex_input"))
        self.assertTrue(hasattr(panel, "_theme_picker"))
        panel._cancel()
        self.assertFalse(panel.isVisible())

    def test_remove_attachment_clears_all_selection_state(self):
        window = self.window
        window._drop_zone._set_file(str(self.ui.API_FILE))
        self.assertEqual(window._current_file, str(self.ui.API_FILE))
        window._drop_zone.clear_file()
        self.assertIsNone(window._current_file)
        self.assertIsNone(window._drop_zone.current_file())
        self.assertIn('No file selected', window._file_hint.text())


    def test_confirmation_timeout_rejects_and_releases_waiter(self):
        import threading
        state = {'event': threading.Event(), 'confirmed': False, 'timeout': .02}
        self.window._show_action_confirmation('Test', 'No action will run.', state)
        self.assertTrue(state['event'].is_set())
        self.assertFalse(state['confirmed'])

    def test_reduced_motion_keeps_real_input_meter(self):
        hud = self.window.hud
        hud.reduced_motion = True
        hud.state = 'LISTENING'
        tick = hud._tick
        hud.set_input_level(.8, 'PC')
        hud._step()
        self.assertEqual(hud._tick, tick)
        self.assertGreater(hud._mic_level, .5)

    def test_compact_window_keeps_composer_and_context_visible(self):
        window = self.window
        window.resize(840, 560)
        self.app.processEvents()
        for widget in [window._input, window._mute_btn, window._right_panel]:
            self.assertTrue(widget.isVisible())
            point = widget.mapTo(window, widget.rect().bottomRight())
            self.assertLessEqual(point.x(), window.width())
            self.assertLessEqual(point.y(), window.height())







    def test_initial_geometry_preserves_title_bar_and_screen_origin(self):
        from PyQt6.QtCore import QRect
        from core.window_controls import initial_geometry
        for screen in [QRect(0, 0, 1366, 720), QRect(-1920, 40, 1920, 1040),
                       QRect(1920, 30, 1280, 690)]:
            geometry = initial_geometry(screen, 1180, 780)
            self.assertTrue(screen.contains(geometry))
            self.assertGreaterEqual(geometry.top(), screen.top()+32)
            self.assertLessEqual(geometry.bottom(), screen.bottom()-16)

    def test_original_layout_and_center_ring_are_present(self):
        window = self.window
        self.assertEqual(window._center_split.widget(0), window._hud_cam_stack)
        self.assertTrue(window._left_panel.isVisible())
        self.assertTrue(window._right_panel.isVisible())
        self.assertFalse(hasattr(window, '_context_tabs'))
        self.assertFalse(hasattr(window, '_conversation'))
        window._on_cam_stream(True)
        self.assertEqual(window._hud_cam_stack.currentIndex(), 1)
        window._on_cam_stream(False)
        self.assertEqual(window._hud_cam_stack.currentIndex(), 0)

    def test_theme_preview_cancels_without_persistence(self):
        original = self.ui.current_palette()
        self.window._open_customize()
        panel = self.window._customize_overlay
        panel._theme_picker.setCurrentIndex(2)
        self.app.processEvents()
        self.assertEqual(self.ui.C.BG, self.ui._THEME_DEFAULTS["light"]["BG"])
        self.window._escape_action()
        self.assertFalse(panel.isVisible())
        self.assertEqual({k:v.lower() for k,v in original.items()},
                         {k:v.lower() for k,v in self.ui.current_palette().items()})

    def test_theme_picker_previews_light_and_cancel_restores_system_choice(self):
        original = self.ui.current_palette()
        self.window._open_customize()
        panel = self.window._customize_overlay
        panel._theme_picker.setCurrentIndex(2)  # Light
        self.app.processEvents()
        self.assertEqual(self.ui.C.BG, self.ui._THEME_DEFAULTS["light"]["BG"])
        self.window._on_system_theme_changed("dark")
        self.assertEqual(self.ui.C.BG, self.ui._THEME_DEFAULTS["light"]["BG"])
        panel._cancel()
        self.assertEqual(self.window._theme_preference, "system")
        self.assertIsNone(self.window._theme_preview_preference)
        self.assertEqual({k:v.lower() for k,v in original.items()},
                         {k:v.lower() for k,v in self.ui.current_palette().items()})

    def test_thinking_working_speaking_priority_tracks_real_tasks(self):
        w = self.window
        w._apply_state('THINKING')
        self.assertEqual(w.hud.state, 'THINKING')
        self.assertEqual(w._activity_lbl.text(), 'THINKING')
        w._update_task_status(2, 1, 0)
        self.assertEqual(w.hud.state, 'WORKING')
        w._apply_state('LISTENING')
        self.assertEqual(w.hud.state, 'WORKING', 'another callback must not hide running work')
        w._apply_state('SPEAKING')
        self.assertTrue(w.hud.speaking)
        self.assertEqual(w._activity_lbl.text(), 'SPEAKING')
        w._apply_state('LISTENING')
        self.assertEqual(w.hud.state, 'WORKING')
        w._update_task_status(0, 0, 3)
        self.assertEqual(w.hud.state, 'LISTENING')

    def test_microphone_animation_updates_while_waiting_for_model(self):
        w = self.window
        w._apply_state('THINKING')
        w._on_mic_level(.8, 'PHONE')
        w.hud._step()
        self.assertGreater(w.hud._mic_level, 0)
        self.assertEqual(w.hud._mic_source, 'PHONE')
        self.assertEqual(w.hud.state, 'THINKING')
        w._apply_state('SPEAKING')
        w._output_level_sig.emit(.7)
        self.app.processEvents()
        self.assertAlmostEqual(w.hud._out_level, .7)
        self.assertEqual(w.hud._mic_level, 0)
        w._apply_state('LISTENING')
        w._toggle_mute()
        w._on_mic_level(.9, 'PC')
        self.assertEqual(w.hud._mic_level, 0)

    def test_standard_right_click_menu_uses_theme_surface_and_text(self):
        from PyQt6.QtGui import QPalette, QColor
        w = self.window
        w._input.setText('Select and copy')
        w._input.selectAll()
        menu = w._input.createStandardContextMenu()
        menu.popup(w._input.mapToGlobal(w._input.rect().topLeft()))
        self.app.processEvents()
        try:
            palette = menu.palette()
            self.assertEqual(palette.color(QPalette.ColorRole.Text), QColor(self.ui.C.TEXT))
            self.assertEqual(palette.color(QPalette.ColorRole.Window), QColor(self.ui.C.SHEET))
            self.assertGreater(palette.color(QPalette.ColorRole.Text).lightness(), 200)
            self.assertLess(palette.color(QPalette.ColorRole.Window).lightness(), 70)
            self.assertIn('QMenu::item:selected', menu.styleSheet())
            self.assertIn(self.ui.C.TEXT, menu.styleSheet())
        finally:
            menu.close()
            menu.deleteLater()

    def test_live_light_switch_repaints_panels_icons_log_and_context_menu(self):
        from PyQt6.QtGui import QColor, QPalette
        w = self.window
        w._log.set_reduced_motion(True)
        w._log.append_log('SYS: Ready')
        self.app.processEvents()
        w._log._step()
        w._preview_theme_preference('light')
        self.app.processEvents()
        self.assertIn(self.ui.C.SIDEBAR.lower(), w._right_panel.styleSheet().lower())
        self.assertIn(self.ui.C.HEADER.lower(), w._title_lbl.parentWidget().styleSheet().lower())
        self.assertIn(self.ui.C.INPUT.lower(), w._input.styleSheet().lower())
        fragment = w._log.document().begin().begin().fragment()
        self.assertEqual(fragment.charFormat().foreground().color(), QColor(self.ui.C.ACC2))
        self.assertFalse(w._drawer_btn.icon().isNull())
        menu = w._input.createStandardContextMenu()
        menu.popup(w._input.mapToGlobal(w._input.rect().topLeft()))
        self.app.processEvents()
        try:
            self.assertEqual(menu.palette().color(QPalette.ColorRole.Window), QColor(self.ui.C.SHEET))
            self.assertEqual(menu.palette().color(QPalette.ColorRole.Text), QColor(self.ui.C.TEXT))
        finally:
            menu.close()
            menu.deleteLater()

    def test_actual_playback_cannot_be_hidden_by_tool_listening_callback(self):
        w = self.window
        w._on_playback_state(True)
        w._apply_state('LISTENING')
        self.assertEqual(w.hud.state, 'SPEAKING')
        w._update_task_status(1, 0, 0)
        self.assertEqual(w.hud.state, 'SPEAKING')
        w._on_playback_state(False)
        self.assertEqual(w.hud.state, 'WORKING')

    def test_only_native_window_controls_are_present(self):
        from PyQt6.QtCore import Qt
        w = self.window
        self.assertFalse(hasattr(w, '_window_controls'))
        for flag in [Qt.WindowType.WindowCloseButtonHint, Qt.WindowType.WindowMinimizeButtonHint,
                     Qt.WindowType.WindowMaximizeButtonHint]:
            self.assertTrue(w.windowFlags() & flag)
        w.showMinimized()
        self.app.processEvents()
        self.assertTrue(w.isMinimized())
        w.showNormal()
        w.showMaximized()
        self.app.processEvents()
        self.assertTrue(w.isMaximized())
        w.showNormal()
        self.assertFalse(w.isMaximized())
