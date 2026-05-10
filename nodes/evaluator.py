# nodes/evaluator.py
from langchain_ollama import OllamaLLM
from state import AgentState, log_to_history
from utils import parse_json_safe, log_step, save_log

llm = OllamaLLM(
    model="qwen2.5:14b",
    format="json",
    temperature=0.1,
)

def evaluator_node(state: AgentState) -> dict:
    if state["status"] == "stopped":
        return {}

    iteration = state["iteration"]
    log_step(iteration, "EVALUATOR", "Đang đánh giá...")

    ui_ok = state["feedback_ui"].get("status") == "ok"
    db_ok = state["feedback_db"].get("status") == "ok"

    history = state.get("history", [])

    if ui_ok and db_ok:
        print(f"\n{'🟢'*25}")
        print("  ✅ PIPELINE HOÀN THÀNH!")
        print(f"  Code tại: output/iteration_{iteration}/")
        print(f"{'🟢'*25}")
        confirm = input("\n  Chốt? [Enter] hoặc [s] chạy thêm: ").strip()

        status   = "done" if confirm.lower() != "s" else "running"
        all_good = status == "done"
        new_plan = {}
    else:
        prompt = f"""
Based on these feedbacks, create a fix plan.
UI feedback: {state['feedback_ui']}
DB feedback: {state['feedback_db']}
Original request: {state['user_request']}

Return ONLY JSON:
{{
  "summary":  "what needs fixing",
  "fix_ui":   "instruction for UI",
  "fix_db":   "instruction for DB"
}}
"""
        response = llm.invoke(prompt)
        new_plan = parse_json_safe(response) or {
            "summary": "Fix errors",
            "fix_ui":  str(state["feedback_ui"].get("suggestions", ["Fix UI"])[0]),
            "fix_db":  str(state["feedback_db"].get("suggestions", ["Fix DB"])[0]),
        }
        status   = "running"
        all_good = False
        log_step(iteration, "EVALUATOR", f"⚠️ Cần sửa:\n{new_plan}")

    save_log(history)
    history.append({"iteration": iteration, "node": "EVALUATOR", "content": status})

    # ← Chỉ trả về field thay đổi
    return {
        "all_good": all_good,
        "new_plan": new_plan,
        "status":   status,
        "history":  history,
    }