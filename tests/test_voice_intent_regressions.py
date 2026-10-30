"""Direct voice switch intent regression cases."""
from core.voice_intent import requested_voice_mode


def test_english_and_bengali_gender_voice_switch_phrases():
    assert requested_voice_mode("Switch to a male voice") == "male"
    assert requested_voice_mode("Use a female voice") == "female"
    assert requested_voice_mode("মেয়েদের ভয়েসে কথা বলো") == "female"
    assert requested_voice_mode("মেল ভয়েসে কথা বলো") == "male"
    assert requested_voice_mode("আমার কণ্ঠ পুরুষের মতো করো") == "male"


def test_voice_mode_requires_an_instruction_not_a_question_about_options():
    assert requested_voice_mode("What are the male voice options?") is None
    assert requested_voice_mode("Why did the female voice change?") is None
