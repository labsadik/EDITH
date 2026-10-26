import unittest

from core.icons import icon_names, svg_markup


class BundledIconTests(unittest.TestCase):
    def test_icon_collection_contains_core_controls_and_file_types(self):
        names = set(icon_names())
        for required in ("mic", "mic-off", "settings", "stop-circle", "puzzle", "file-image", "file-code", "sun", "maximize", "alert-triangle"):
            with self.subTest(icon=required):
                self.assertIn(required, names)

    def test_svg_icons_are_local_vector_markup(self):
        svg = svg_markup("settings")
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("<path", svg)
        self.assertNotIn("http://", svg.replace('xmlns="http://www.w3.org/2000/svg"', ""))

    def test_unknown_color_falls_back_to_brand_accent(self):
        svg = svg_markup("mic", "url(javascript:alert(1))")
        self.assertIn('stroke="#A5B4FC"', svg)


if __name__ == "__main__":
    unittest.main()
