# nodes/human_gate.py
import json
from state import AgentState
from utils import log_step
from nodes.task_config import TASK_TYPES


def human_gate_node(state: AgentState) -> dict:
    iteration    = state["iteration"]
    plan         = state["current_plan"]
    active_types = state.get("active_task_types", [])

    print(f"\n{'🔵'*25}")
    print(f"  HUMAN CHECKPOINT — Vòng {iteration}")
    print(f"{'🔵'*25}")
    print(f"\n📋 Plan hiện tại:")
    print(json.dumps(plan, indent=2, ensure_ascii=False))

    # ── Hiển thị feedback động theo active_task_types ────────
    has_feedback = False
    for task_type in active_types:
        config   = TASK_TYPES.get(task_type, {})
        fb_field = config.get("feedback_field", f"feedback_{task_type.lower()}")
        fb       = state.get(fb_field, {})
        if fb:
            if not has_feedback:
                print(f"\n📝 Feedback vòng trước:")
                has_feedback = True
            status = fb.get("status", "unknown")
            score  = fb.get("quality_score", "?")
            icon   = "✅" if status == "ok" else "❌"
            print(f"  {icon} [{task_type}] status={status} score={score}/10")
            for issue in fb.get("issues", [])[:3]:   # chỉ in 3 issue đầu
                print(f"     • {issue}")

    print(f"\n{'─'*50}")
    print("  [Enter] → Tiếp tục | [s] → Dừng | [text] → Thêm yêu cầu")
    print(f"{'─'*50}")

    decision = input("  Quyết định: ").strip()

    status            = state.get("status", "running")
    human_decision    = "continue"
    extra_requirement = state.get("extra_requirement", "")

    if decision.lower() == "s":
        status         = "stopped"
        human_decision = "stop"
        log_step(iteration, "HUMAN GATE", "🛑 Dừng pipeline")
    elif decision == "":
        log_step(iteration, "HUMAN GATE", "✅ Tiếp tục")
    else:
        human_decision    = "modify"
        extra_requirement = decision
        log_step(iteration, "HUMAN GATE", f"📝 Yêu cầu thêm: {decision}")

    return {
        "status":            status,
        "human_decision":    human_decision,
        "extra_requirement": extra_requirement,
        # ← Chỉ entry MỚI, không get history cũ
        "history": [{"iteration": iteration, "node": "HUMAN GATE", "content": human_decision}],
    }