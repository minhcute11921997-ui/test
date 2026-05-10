# nodes/reviewer.py
import ast
import subprocess
import sys
import os
from langchain_ollama import OllamaLLM
from state import AgentState
from utils import parse_json_safe, log_step
from memory.memory_manager import load_relevant_patterns
from nodes.task_config import TASK_TYPES   # ← thêm

llm = OllamaLLM(
    model="qwen2.5:14b",
    format="json",
    temperature=0.1,
)

# ── Static Analysis ───────────────────────────────────────────
# (giữ nguyên _check_syntax, _check_pylint, _static_check, _llm_review, _review_code)
# ...

# ── Node Function ─────────────────────────────────────────────

def reviewer_node(state: AgentState) -> dict:
    if state["status"] == "stopped":
        return {}

    iteration    = state["iteration"]
    log_step(iteration, "REVIEWER", "Bắt đầu review...")

    # ── Review động theo active_task_types ───────────────────
    active_types     = state.get("active_task_types", ["UI", "DB"])
    feedback_results = {}

    for t in active_types:
        config     = TASK_TYPES.get(t, {})
        code_field = config.get("state_field", f"code_{t.lower()}")
        code       = state.get(code_field, "")

        print(f"\n  🔍 Review {t}...")
        fb = _review_code(code, t)
        _print_review_result(t, fb)

        fb_field               = config.get("feedback_field", f"feedback_{t.lower()}")
        feedback_results[t]    = fb

    # Log tổng kết
    summary = " | ".join(
        f"{'✅' if fb['status'] == 'ok' else '❌'} {t}: {fb.get('quality_score','?')}/10"
        for t, fb in feedback_results.items()
    )
    log_step(iteration, "REVIEWER", summary)
    # ─────────────────────────────────────────────────────────

    # Build return dict động
    return_dict = {
        "history": [{
            "iteration": iteration,
            "node":      "REVIEWER",
            "content":   {f"feedback_{t.lower()}": fb for t, fb in feedback_results.items()},
        }]
    }

    # Thêm từng feedback field vào return
    for t, fb in feedback_results.items():
        config   = TASK_TYPES.get(t, {})
        fb_field = config.get("feedback_field", f"feedback_{t.lower()}")
        return_dict[fb_field] = fb

    return return_dict