"""Direct voice switch intent regression cases."""
import unittest

from core.voice_intent import requested_voice_mode


class VoiceIntentRegressionTests(unittest.TestCase):
    def test_english_and_bengali_gender_voice_switch_phrases(self):
        self.assertEqual(requested_voice_mode("Switch to a male voice"), "male")
        self.assertEqual(requested_voice_mode("Use a female voice"), "female")
        self.assertEqual(requested_voice_mode("মেয়েদের ভয়েসে কথা বলো"), "female")
        self.assertEqual(requested_voice_mode("মেল ভয়েসে কথা বলো"), "male")
        self.assertEqual(requested_voice_mode("আমার কণ্ঠ পুরুষের মতো করো"), "male")

    def test_voice_mode_requires_an_instruction_not_a_question_about_options(self):
        self.assertIsNone(requested_voice_mode("What are the male voice options?"))
        self.assertIsNone(requested_voice_mode("Why did the female voice change?"))


if __name__ == "__main__":
    unittest.main()
