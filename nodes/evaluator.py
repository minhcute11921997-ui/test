# nodes/evaluator.py
from langchain_ollama import OllamaLLM
from state import AgentState, log_to_history
from utils import parse_json_safe, log_step, save_log
from nodes.task_config import TASK_TYPES


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

    # ── Check feedback động theo active_task_types ───────────
    active_types = state.get("active_task_types", ["UI", "DB"])

    feedback_results = {}
    for t in active_types:
        fb_field = TASK_TYPES.get(t, {}).get("feedback_field", f"feedback_{t.lower()}")
        fb       = state.get(fb_field, {})
        feedback_results[t] = fb

    all_ok = all(
        fb.get("status") == "ok"
        for fb in feedback_results.values()
    )

    # In trạng thái từng task
    for t, fb in feedback_results.items():
        icon  = "✅" if fb.get("status") == "ok" else "❌"
        score = fb.get("quality_score", "?")
        print(f"  {icon} [{t}] score: {score}/10")
    # ────────────────────────────────────────────────────────

    if all_ok:
        print(f"\n{'🟢'*25}")
        print("  ✅ PIPELINE HOÀN THÀNH!")
        print(f"  Code tại: output/iteration_{iteration}/")
        print(f"{'🟢'*25}")
        confirm = input("\n  Chốt? [Enter] hoặc [s] chạy thêm: ").strip()

        status   = "done" if confirm.lower() != "s" else "running"
        all_good = status == "done"
        new_plan = {}

    else:
        # ── Prompt động ──────────────────────────────────────
        feedback_text = "\n".join(
            f"{t} feedback: {fb}"
            for t, fb in feedback_results.items()
        )
        fix_fields_example = "\n".join(
            f'  "fix_{t.lower()}": "instruction for {t}"'
            for t in active_types
        )

        prompt = f"""
Based on these feedbacks, create a fix plan.
{feedback_text}
Original request: {state['user_request']}

Return ONLY JSON:
{{
  "summary": "what needs fixing",
{fix_fields_example}
}}
"""
        response = llm.invoke(prompt)
        new_plan = parse_json_safe(response) or {
            "summary": "Fix errors",
            **{
                f"fix_{t.lower()}": str(
                    feedback_results[t].get("suggestions", [f"Fix {t}"])[0]
                )
                for t in active_types
            }
        }
        status   = "running"
        all_good = False
        log_step(iteration, "EVALUATOR", f"⚠️ Cần sửa:\n{new_plan}")

    save_log(state.get("history", []))
    return {
        "all_good": all_good,
        "new_plan": new_plan,
        "status":   status,
        "history":  [{"iteration": iteration, "node": "EVALUATOR", "content": status}],
    }