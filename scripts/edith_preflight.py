"""EDITH local preflight; opt-in tests never save audio or expose credentials."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "api_keys.json"
PRESETS = {"female": "Kore", "male": "Orus"}


def check(name, fn, warnings, warning_only=False):
    try:
        print(f"[PASS] {name}: {fn()}")
        return 0
    except Exception as exc:
        label = "WARN" if warning_only else "FAIL"
        print(f"[{label}] {name}: {type(exc).__name__}: {str(exc)[:180]}")
        warnings[0 if warning_only else 1] += 1
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-sandbox-test", action="store_true")
    parser.add_argument("--live-voice-test", action="store_true")
    parser.add_argument("--record-mic-test", action="store_true")
    parser.add_argument("--speaker-test", action="store_true")
    parser.add_argument("--seconds", type=float, default=2.0)
    args = parser.parse_args()
    warnings = [0, 0]
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            config = {}
    except Exception:
        config = {}

    check("Python", lambda: sys.version.split()[0], warnings)

    def providers():
        from core.provider_registry import load_provider_settings, provider_api_key, provider_spec
        result = []
        for profile in ("main", "powerful"):
            settings = load_provider_settings(CONFIG, profile)
            spec = provider_spec(settings["provider"])
            key = provider_api_key(settings["provider"], CONFIG, profile)
            result.append(f"{profile}={settings['provider']}/{settings['model']}/" +
                          ("key-present" if key else "no-key"))
        return "; ".join(result)
    check("Brain profiles", providers, warnings)

    def voice():
        mode = str(config.get("voice_mode") or "female").lower()
        if mode not in PRESETS:
            raise RuntimeError("voice_mode must be male or female")
        from core.provider_registry import load_voice_settings
        settings = load_voice_settings(CONFIG)
        return f"{mode}={PRESETS[mode]}, provider={settings['provider']}, model={settings['model']}"
    check("Voice presets", voice, warnings)

    def audio_devices():
        import sounddevice as sd
        devices = sd.query_devices()
        inputs = sum(int(d.get("max_input_channels", 0)) > 0 for d in devices)
        outputs = sum(int(d.get("max_output_channels", 0)) > 0 for d in devices)
        if not inputs or not outputs:
            raise RuntimeError(f"input devices={inputs}; output devices={outputs}")
        return f"{inputs} input and {outputs} output device(s); enumeration only"
    check("Microphone/speaker devices", audio_devices, warnings, True)

    def browser():
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        return "Qt WebEngine import OK"
    check("Embedded browser", browser, warnings)

    def rag():
        import langchain_core, langchain_text_splitters, lancedb
        from memory.rag_store import knowledge_stats
        return f"LangChain/LanceDB ready; indexed chunks={knowledge_stats()['chunks']}"
    check("LangChain + RAG", rag, warnings)

    def graph():
        import langgraph
        from core.agent_supervisor import run_agent_supervisor
        return "LangGraph supervisor import OK; no LLM call made"
    check("LangGraph", graph, warnings)

    def agents():
        from core.agent_registry import list_agents
        items = list_agents()
        if not items:
            raise RuntimeError("No agent definitions")
        return f"{sum(bool(x.get('enabled')) for x in items)}/{len(items)} enabled"
    check("Agent registry", agents, warnings)

    def ollama():
        import requests
        base = os.environ.get("EDITH_EMBEDDING_URL", "http://127.0.0.1:11434").rstrip("/")
        r = requests.get(base + "/api/tags", timeout=3)
        r.raise_for_status()
        model = os.environ.get("EDITH_EMBEDDING_MODEL", "nomic-embed-text")
        names = [str(x.get("name") or "") for x in r.json().get("models", [])]
        if not any(x == model or x.startswith(model + ":") for x in names):
            raise RuntimeError(f"model {model} is not installed")
        return f"Ollama and {model} available"
    check("Ollama embeddings", ollama, warnings, True)

    def home_assistant():
        from agents.smart_network import _ha_credentials
        if not _ha_credentials(required=False):
            raise RuntimeError("Home Assistant is not paired")
        return "paired URL/token configured (token hidden)"
    check("Home Assistant", home_assistant, warnings, True)

    def mqtt():
        from agents.mqtt_bridge import _pairing
        data, host, port, tls, _password = _pairing()
        return f"{host}:{port}, TLS={tls}, exact topics={len(data.get('mqtt_topics') or [])}"
    check("MQTT", mqtt, warnings, True)

    def rust():
        from core.sandbox_runner import sandbox_binary
        binary = sandbox_binary()
        if binary.is_file():
            r = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode:
                raise RuntimeError("sandbox binary version check failed")
            return r.stdout.strip()
        if not shutil.which("cargo"):
            raise RuntimeError("Rust helper missing and Cargo unavailable")
        return "Cargo available; helper builds on first use"
    check("Rust sandbox", rust, warnings)

    def briefing():
        from memory.config_manager import get_brief_enabled
        return "ON" if get_brief_enabled() else "OFF (default)"
    check("Startup briefing", briefing, warnings)

    if args.run_sandbox_test:
        def sandbox_test():
            from core.sandbox_runner import run_sandboxed
            with tempfile.TemporaryDirectory(prefix="edith-preflight-") as folder:
                r = run_sandboxed([sys.executable, "-c", "print('EDITH_SANDBOX_OK')"],
                                  workspace=folder, timeout=45, profile="safe", network=False)
                if r.returncode or "EDITH_SANDBOX_OK" not in r.stdout:
                    raise RuntimeError((r.stderr or r.stdout)[-400:])
                return "isolated print succeeded; safe profile; network denied"
        check("Rust sandbox runtime execution", sandbox_test, warnings)

    if args.live_voice_test:
        def voices():
            from core.provider_registry import load_voice_settings, probe_voice_provider
            from core.secrets import get_gemini_api_key
            key = get_gemini_api_key(CONFIG)
            if not key:
                raise RuntimeError("Gemini Live API key missing")
            settings = load_voice_settings(CONFIG)
            for mode, preset in PRESETS.items():
                r = probe_voice_provider(settings["provider"], settings["model"], key, voice_name=preset)
                if not r.get("ok"):
                    raise RuntimeError(f"{mode}/{preset}: {r.get('error')}")
            return "Gemini Live returned audio for Kore (female) and Orus (male)"
        check("Live female/male voice", voices, warnings)

    if args.record_mic_test:
        def microphone():
            import numpy as np
            import sounddevice as sd
            seconds = max(1, min(float(args.seconds), 5))
            data = sd.rec(int(seconds * 16000), samplerate=16000, channels=1,
                          dtype="int16", blocking=True)
            rms = float(np.sqrt(np.mean(data.astype("float32") ** 2)))
            if rms < 1:
                raise RuntimeError("silence captured; check permissions/input level")
            return f"captured {seconds}s, RMS={rms:.1f}; audio not saved"
        check("Opt-in microphone capture", microphone, warnings)

    if args.speaker_test:
        def speaker():
            import numpy as np
            import sounddevice as sd
            rate = 16000
            samples = int(rate * 0.25)
            tone = (0.06 * np.sin(2 * math.pi * 440 * np.arange(samples) / rate)).astype("float32")
            sd.play(tone, samplerate=rate, blocking=True)
            return "played 250ms test tone"
        check("Opt-in speaker playback", speaker, warnings)

    print(f"[SUMMARY] failures={warnings[1]}, warnings={warnings[0]}")
    return 1 if warnings[1] else 0


if __name__ == "__main__":
    raise SystemExit(main())
