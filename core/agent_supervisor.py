"""LangGraph-powered multi-role supervisor for Powerful Brain tasks."""
from __future__ import annotations

import json
from typing import Any, TypedDict

from core.brain_router import call_brain_text

_SPECIALISTS = {
    "planner": "Break a complex request into a practical plan with risks and acceptance checks.",
    "researcher": "Analyze facts carefully and distinguish verified facts from assumptions.",
    "developer": "Design implementation steps, APIs, code structure, edge cases and tests.",
    "security": "Review permissions, trust boundaries, privacy and failure modes using least privilege.",
}


class SupervisorState(TypedDict, total=False):
    request: str
    context: str
    tasks: list[dict[str, str]]
    results: list[dict[str, str]]
    answer: str


def _retrieve(state: SupervisorState) -> dict[str, Any]:
    try:
        from memory.rag_store import search_knowledge
        matches = search_knowledge(state["request"], limit=5)
        context = "\n\n".join(f"[{item['source']}] {item['text']}" for item in matches)
    except Exception as exc:
        context = f"(Local knowledge retrieval unavailable: {type(exc).__name__})"
    return {"context": context}


def _plan(state: SupervisorState) -> dict[str, Any]:
    prompt = (
        "Create a compact delegation plan. Return only JSON as "
        "{\"tasks\":[{\"role\":\"planner|researcher|developer|security\",\"task\":\"bounded task\"}]}. "
        "Use 1-4 tasks; do not invent tools or claim external actions happened.\n\nREQUEST:\n"
        + state["request"]
        + ("\n\nLOCAL CONTEXT:\n" + state.get("context", "") if state.get("context") else "")
    )
    raw = call_brain_text(prompt, system="You are EDITH's supervisor. Output valid JSON only.")
    try:
        start, end = raw.find("{"), raw.rfind("}") + 1
        parsed = json.loads(raw[start:end]) if start >= 0 and end > start else {}
        tasks = parsed.get("tasks", [])
    except Exception:
        tasks = []
    normalized = []
    for item in tasks if isinstance(tasks, list) else []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "planner").lower()
        task = str(item.get("task") or "").strip()
        if role in _SPECIALISTS and task:
            normalized.append({"role": role, "task": task[:2000]})
        if len(normalized) >= 4:
            break
    if not normalized:
        normalized = [{"role": "planner", "task": state["request"]}]
    return {"tasks": normalized}


def _delegate(state: SupervisorState) -> dict[str, Any]:
    results: list[dict[str, str]] = []
    for task in state.get("tasks", [])[:4]:
        role = task["role"]
        prompt = (
            f"USER REQUEST: {state['request']}\n\nASSIGNED TASK: {task['task']}\n\n"
            f"AVAILABLE LOCAL CONTEXT:\n{state.get('context', '(none)')}\n\n"
            "Return a focused specialist result. Do not claim a tool, device or file was changed."
        )
        answer = call_brain_text(prompt, system=_SPECIALISTS[role])
        results.append({"role": role, "task": task["task"], "result": answer[:6000]})
    return {"results": results}


def _synthesize(state: SupervisorState) -> dict[str, Any]:
    prompt = (
        f"USER REQUEST:\n{state['request']}\n\n"
        f"LOCAL RETRIEVAL CONTEXT:\n{state.get('context', '(none)')}\n\n"
        f"SPECIALIST RESULTS:\n{json.dumps(state.get('results', []), ensure_ascii=False)}\n\n"
        "Combine the specialist results into one actionable answer. Separate verified facts, assumptions and next steps."
    )
    answer = call_brain_text(
        prompt, system="You are EDITH's supervisor. Reconcile specialist results and be precise."
    )
    return {"answer": answer}


def _build_graph():
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("Install langgraph from requirements.txt to enable the agent supervisor") from exc
    graph = StateGraph(SupervisorState)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("plan", _plan)
    graph.add_node("delegate", _delegate)
    graph.add_node("synthesize", _synthesize)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "plan")
    graph.add_edge("plan", "delegate")
    graph.add_edge("delegate", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


def run_agent_supervisor(request: str) -> str:
    """Run retrieval-augmented planning, specialist delegation and synthesis."""
    clean = str(request or "").strip()
    if not clean:
        raise ValueError("A task description is required")
    result = _build_graph().invoke({"request": clean[:8000]})
    answer = str(result.get("answer") or "").strip()
    if not answer:
        raise RuntimeError("Supervisor graph completed without a final answer")
    return answer
