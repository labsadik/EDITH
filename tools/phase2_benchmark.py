"""Measure the configured local model's actual response latency.

Usage (from project root):
    python tools/phase2_benchmark.py --iterations 3

This tool uses existing config/api_keys.json provider/model settings only.
It neither displays nor modifies API keys, local configuration, or messages.
Cloud Gemini Live latency is measured via Settings > TEST KEY and the Live
session's PERF entries in EDITH's Activity Log.
"""
import argparse
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.llm_client import call_llm_stream, get_llm_provider, get_llm_settings


def run_benchmark(iterations: int, timeout: int) -> list[dict]:
    records = []
    messages = [
        {"role": "user", "content": "In one short sentence, describe what a computer does."}
    ]
    for number in range(1, iterations + 1):
        start = time.perf_counter()
        first_sentence_ms = None
        completed = False
        for event in call_llm_stream(messages, timeout=timeout):
            if event.get("type") == "sentence" and first_sentence_ms is None:
                first_sentence_ms = round((time.perf_counter() - start) * 1000)
            if event.get("type") == "done":
                completed = True
        total_ms = round((time.perf_counter() - start) * 1000)
        if not completed:
            raise RuntimeError("Model stream ended without a final 'done' event.")
        result = {"first_sentence_ms": first_sentence_ms, "total_ms": total_ms}
        records.append(result)
        first = str(first_sentence_ms) if first_sentence_ms is not None else "none"
        print(f"Run {number}: first sentence {first} ms; complete {total_ms} ms")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="EDITH Phase 2 local LLM benchmark")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 10 or args.timeout < 1:
        parser.error("iterations must be 1-10 and timeout must be positive")

    url, model = get_llm_settings()
    print(f"Configured local agent: {get_llm_provider()} | {model} | {url}")
    print("First sentence is NOT the same as first token.")
    try:
        results = run_benchmark(args.iterations, args.timeout)
    except (RuntimeError, OSError) as exc:
        parser.exit(1, f"Benchmark failed: {type(exc).__name__}: {exc}\n")
    print(
        "Median total: "
        f"{statistics.median(item['total_ms'] for item in results):g} ms"
    )
    firsts = [item["first_sentence_ms"] for item in results
              if item["first_sentence_ms"] is not None]
    if firsts:
        print(f"Median first sentence: {statistics.median(firsts):g} ms")


if __name__ == "__main__":
    main()
