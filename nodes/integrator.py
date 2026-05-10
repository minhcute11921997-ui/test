# nodes/integrator.py
from state import AgentState, log_to_history
from utils import log_step, save_code
import os

def integrator_node(state: AgentState) -> dict:
    if state["status"] == "stopped":
        return {}

    iteration = state["iteration"]
    folder    = f"output/iteration_{iteration}"
    os.makedirs(folder, exist_ok=True)

    log_step(iteration, "INTEGRATOR", "Đang tích hợp code...")

    combined = f"""
# ============================================================
# INTEGRATED CODE — Iteration {iteration}
# ============================================================

# ── UI CODE ──────────────────────────────────────────────────
{state['code_ui']}

# ── DB CODE ──────────────────────────────────────────────────
{state['code_db']}
"""
    save_code(combined, f"{folder}/integrated.py")

    report = f"""
ITERATION {iteration} REPORT
{'='*40}
UI Feedback: {state['feedback_ui']}
DB Feedback: {state['feedback_db']}
"""
    save_code(report, f"{folder}/report.txt")

    log_step(iteration, "INTEGRATOR", f"✅ Lưu tại {folder}/")

    history = state.get("history", [])
    history.append({"iteration": iteration, "node": "INTEGRATOR", "content": f"saved to {folder}"})

    # ← Chỉ trả về field thay đổi
    return {"history": history}