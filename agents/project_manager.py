"""Local, persistent project planning and lightweight task tracking."""
from __future__ import annotations
import json, os, re, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "config" / "projects.json"
AGENT_ID = "project_manager"
AGENT_VERSION = "1.0.0"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{1,47}$")

def _read() -> dict[str, Any]:
    try:
        payload = json.loads(STORE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"projects": {}}
    except (OSError, ValueError, TypeError):
        return {"projects": {}}

def _write(payload: dict[str, Any]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=STORE.parent,
                prefix=".edith-projects-", suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(STORE)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)

def _project_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", str(value or "").strip().lower()).strip("-_")[:48]
    if len(slug) < 2 or not _SLUG.fullmatch(slug):
        raise ValueError("Project id must contain 2-48 letters, numbers, hyphens or underscores.")
    return slug

def plan_project(goal: str, project_id: str = "") -> dict[str, Any]:
    objective = str(goal or "").strip()
    if not objective:
        raise ValueError("A project goal is required.")
    if len(objective) > 3000:
        raise ValueError("Project goal must be 3000 characters or fewer.")
    from core.brain_router import call_brain_text
    prompt = (
        "Create a practical project plan. Return ONLY valid JSON with this shape: "
        '{"project_name":"short name","summary":"one paragraph","milestones":['
        '{"title":"milestone","tasks":[{"title":"actionable task","description":"one sentence"}]}]}. '
        "Use 2-8 milestones and 1-6 tasks per milestone. Do not claim to execute anything.\n"
        f"Goal: {objective}"
    )
    raw = call_brain_text(prompt, workload="project_management", timeout=90).strip()
    raw = re.sub(r"^\x60{3}(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*\x60{3}$", "", raw)
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Powerful Brain returned an invalid project plan; nothing was saved.") from exc
    milestones = data.get("milestones") if isinstance(data, dict) else None
    if not isinstance(milestones, list) or not 1 <= len(milestones) <= 8:
        raise RuntimeError("Project plan must contain between 1 and 8 milestones.")
    tasks = []
    for milestone_index, milestone in enumerate(milestones, start=1):
        if not isinstance(milestone, dict):
            continue
        title = str(milestone.get("title") or f"Milestone {milestone_index}")[:120]
        items = milestone.get("tasks")
        if not isinstance(items, list):
            continue
        for task in items[:6]:
            if not isinstance(task, dict):
                continue
            tasks.append({
                "task_id": f"T{len(tasks) + 1:03d}", "milestone": title,
                "title": str(task.get("title") or "Untitled task")[:180],
                "description": str(task.get("description") or "")[:500],
                "status": "pending", "notes": "",
            })
    if not 1 <= len(tasks) <= 48:
        raise RuntimeError("Project plan must contain between 1 and 48 valid tasks.")
    identifier = _project_id(project_id or str(data.get("project_name") or objective[:48]))
    project = {
        "id": identifier, "name": str(data.get("project_name") or identifier)[:120],
        "goal": objective, "summary": str(data.get("summary") or "")[:1200],
        "status": "active", "version": AGENT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(), "tasks": tasks,
    }
    payload = _read()
    projects = payload.setdefault("projects", {})
    if identifier in projects:
        raise ValueError(f"Project '{identifier}' already exists. Choose another project_id.")
    projects[identifier] = project
    _write(payload)
    return project

def update_task(project_id: str, task_id: str, status: str, notes: str = "") -> dict[str, Any]:
    identifier, task_key = _project_id(project_id), str(task_id or "").strip().upper()
    new_status = str(status or "").strip().lower()
    if new_status not in {"pending", "in_progress", "blocked", "completed"}:
        raise ValueError("Task status must be pending, in_progress, blocked or completed.")
    payload = _read()
    project = payload.get("projects", {}).get(identifier)
    if not isinstance(project, dict):
        raise KeyError(f"Project '{identifier}' was not found.")
    task = next((item for item in project.get("tasks", []) if item.get("task_id") == task_key), None)
    if task is None:
        raise KeyError(f"Task '{task_key}' was not found in project '{identifier}'.")
    task["status"] = new_status
    if notes:
        task["notes"] = str(notes)[:1000]
    statuses = [item.get("status") for item in project.get("tasks", [])]
    project["status"] = "completed" if statuses and all(item == "completed" for item in statuses) else "active"
    project["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write(payload)
    return {"project": identifier, "task": task, "project_status": project["status"]}

def get_project(project_id: str = "") -> list[dict[str, Any]] | dict[str, Any]:
    projects = _read().get("projects", {})
    if project_id:
        identifier = _project_id(project_id)
        project = projects.get(identifier)
        if not isinstance(project, dict):
            raise KeyError(f"Project '{identifier}' was not found.")
        return project
    return list(projects.values())

def format_project_status(value: list[dict[str, Any]] | dict[str, Any]) -> str:
    projects = value if isinstance(value, list) else [value]
    if not projects:
        return "No locally tracked projects yet."
    lines = ["Local project tracker:"]
    for project in projects:
        lines.append(f"- {project.get('name')} ({project.get('id')}) · {project.get('status')}")
        lines.append(f"  Goal: {project.get('goal', '')[:240]}")
        for task in project.get("tasks", []):
            lines.append(f"  {task.get('task_id')} [{task.get('status')}] {task.get('milestone')}: {task.get('title')}")
    return "\n".join(lines)

def run_project_manager(action: str, project_id: str = "", goal: str = "",
                        task_id: str = "", status: str = "", notes: str = "") -> str:
    action = str(action or "status").strip().lower()
    if action == "plan":
        project = plan_project(goal, project_id)
        return "Saved a new local project plan.\n" + format_project_status(project)
    if action in {"status", "list"}:
        return format_project_status(get_project(project_id))
    if action in {"update", "complete", "start", "block"}:
        selected_status = {"complete": "completed", "start": "in_progress", "block": "blocked"}.get(action, status)
        result = update_task(project_id, task_id, selected_status, notes)
        return f"Updated {result['project']} {task_id} to {selected_status}. Project status: {result['project_status']}."
    return "Use action=plan, status, list, update, complete, start or block."
