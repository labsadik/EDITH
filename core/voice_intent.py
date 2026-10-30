"""Require a direct user request before changing the active Live voice preset."""
import re


def requested_voice_mode(text: str) -> str | None:
    statement = str(text or "").strip().casefold()
    if not statement or len(statement) > 220:
        return None

    female = bool(re.search(
        r"\b(female|woman|girl)\b|মেয়েদের|মেয়েদের|মেয়েলি|মেয়েলি|নারী|মেয়ের কণ্ঠ",
        statement,
    ))
    male = bool(re.search(
        r"\bmale\b|\bman's\b|\bman\b|\bboy\b|পুরুষ|ছেলেদের|মেল ভয়েস|মেল ভয়েস",
        statement,
    ))
    if female == male:
        return None

    shorthand = bool(re.fullmatch(
        r"(?:(?:a|the) )?(?:female|male|woman's|man's) voice(?: please)?|"
        r"(?:মেয়েদের|মেয়েদের|মেয়েলি|মেয়েলি|পুরুষ|ছেলেদের|মেল)\s*(?:ভয়েস|ভয়েস|কণ্ঠ)",
        statement,
    ))
    # Include common ASR variants such as "turn into female voice" and
    # "change my voice to male". A gender word alone is never sufficient.
    english = bool(re.search(
        r"\b(change|switch|set|use|speak|talk|make|turn)\b.{0,75}"
        r"\b(voice|female|male|woman|man)\b",
        statement,
    ))
    bengali = bool(re.search(
        r"(?:ভয়েস|ভয়েস|কণ্ঠ|গলা).{0,55}(?:করো|করে দাও|বলো|বলবে|চাই|চালাও|দাও)|"
        r"(?:মেয়েদের|মেয়েদের|মেয়েলি|মেয়েলি|পুরুষ|ছেলেদের).{0,55}"
        r"(?:কথা বলো|ভয়েস করো|ভয়েস করো|কণ্ঠে বলো|মতো করো|মতো করে দাও)",
        statement,
    ))
    return ("female" if female else "male") if shorthand or english or bengali else None
