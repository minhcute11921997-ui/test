# nodes/integrator.py
import os
from state import AgentState
from utils import log_step, save_code
from nodes.task_config import TASK_TYPES


def integrator_node(state: AgentState) -> dict:
    if state["status"] == "stopped":
        return {}

    iteration    = state["iteration"]
    active_types = state.get("active_task_types", ["UI", "DB"])
    folder       = f"output/iteration_{iteration}"
    os.makedirs(folder, exist_ok=True)

    log_step(iteration, "INTEGRATOR", f"Đang tích hợp {len(active_types)} modules: {active_types}...")

    # ── Gom code từng module đang active ─────────────────────
    sections = [
        f"# {'='*60}",
        f"# INTEGRATED CODE — Iteration {iteration}",
        f"# Modules: {', '.join(active_types)}",
        f"# {'='*60}",
        "",
    ]

    found_any = False
    for task_type in active_types:
        config     = TASK_TYPES.get(task_type, {})
        code_field = config.get("state_field", f"code_{task_type.lower()}")
        code       = state.get(code_field, "")

        sections.append(f"# {'─'*60}")
        sections.append(f"# MODULE: {task_type} — {config.get('desc', '')}")
        sections.append(f"# {'─'*60}")

        if code and code.strip():
            sections.append(code)
            found_any = True
            print(f"  ✅ [{task_type}] {len(code)} chars")
        else:
            sections.append(f"# ⚠️  [{task_type}] — Không có code")
            print(f"  ⚠️  [{task_type}] rỗng — bỏ qua")

        sections.append("")

    if not found_any:
        log_step(iteration, "INTEGRATOR", "⚠️ Không có module nào có code — bỏ qua lưu file")
        return {
            "history": [{"iteration": iteration, "node": "INTEGRATOR",
                         "content": "no code to integrate"}]
        }

    combined = "\n".join(sections)
    save_code(combined, f"{folder}/integrated.py")

    # ── Report tổng hợp feedback động ────────────────────────
    report_lines = [
        f"ITERATION {iteration} REPORT",
        "=" * 40,
        f"Active modules: {active_types}",
        "",
    ]
    for task_type in active_types:
        config   = TASK_TYPES.get(task_type, {})
        fb_field = config.get("feedback_field", f"feedback_{task_type.lower()}")
        fb       = state.get(fb_field, {})
        status   = fb.get("status", "unknown")
        score    = fb.get("quality_score", "?")
        report_lines.append(f"[{task_type}] status={status} score={score}/10")
        if fb.get("issues"):
            for issue in fb["issues"]:
                report_lines.append(f"  ❌ {issue}")

    save_code("\n".join(report_lines), f"{folder}/report.txt")

    log_step(iteration, "INTEGRATOR", f"✅ Lưu tại {folder}/")

    return {
        "history": [{"iteration": iteration, "node": "INTEGRATOR",
                     "content": f"integrated {len(active_types)} modules to {folder}"}]
    }