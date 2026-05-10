# nodes/human_gate.py
from state import AgentState, log_to_history
from utils import log_step
import json

def human_gate_node(state: AgentState) -> dict:
    iteration = state["iteration"]
    plan = state["current_plan"]

    print(f"\n{'🔵'*25}")
    print(f"  HUMAN CHECKPOINT — Vòng {iteration}")
    print(f"{'🔵'*25}")
    print(f"\n📋 Plan hiện tại:")
    print(json.dumps(plan, indent=2, ensure_ascii=False))

    if state.get("feedback_ui") or state.get("feedback_db"):
        print(f"\n📝 Feedback vòng trước:")
        print(f"  UI: {state.get('feedback_ui', {})}")
        print(f"  DB: {state.get('feedback_db', {})}")

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

    history = state.get("history", [])
    history.append({"iteration": iteration, "node": "HUMAN GATE", "content": human_decision})

    # ← Chỉ trả về field thay đổi
    return {
        "status":            status,
        "human_decision":    human_decision,
        "extra_requirement": extra_requirement,
        "history":           history,
    }