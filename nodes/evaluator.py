# nodes/evaluator.py
from langchain_ollama import OllamaLLM
from state import AgentState
from utils import parse_json_safe, log_step, save_log
from nodes.task_config import TASK_TYPES

llm = OllamaLLM(
    model="deepseek-r1:14b",
    format="json",
    temperature=0.1,
)


def _build_cross_context(state: AgentState, active_types: list, feedback_results: dict) -> str:
    lines = []
    for t in active_types:
        config     = TASK_TYPES.get(t, {})
        code_field = config.get("state_field", f"code_{t.lower()}")
        code       = state.get(code_field, "")
        fb         = feedback_results.get(t, {})

        lines.append(f"\n{'='*50}")
        lines.append(f"MODULE: {t}")
        lines.append(f"STATUS: {fb.get('status', 'unknown')}")
        lines.append(f"SCORE:  {fb.get('quality_score', '?')}/10")

        issues = fb.get("issues", [])
        if issues:
            lines.append(f"ISSUES ({len(issues)}):")
            for issue in issues:
                lines.append(f"  ❌ {issue}")

        suggestions = fb.get("suggestions", [])
        if suggestions:
            lines.append("SUGGESTIONS:")
            for s in suggestions:
                lines.append(f"  💡 {s}")

        if code and code.strip():
            lines.append("CODE SNIPPET (first 600 chars):")
            lines.append(f"```python\n{code[:600]}\n```")
        else:
            lines.append("CODE: (empty)")

    return "\n".join(lines)


def _generate_smart_fix_plan(
    state:            AgentState,
    active_types:     list,
    feedback_results: dict,
    iteration:        int,
) -> dict:
    cross_context = _build_cross_context(state, active_types, feedback_results)

    fix_fields = "\n".join(
        f'  "fix_{t.lower()}": "specific fix instruction for {t} or empty string if ok"'
        for t in active_types
    )

    error_modules = [t for t, fb in feedback_results.items() if fb.get("status") != "ok"]
    ok_modules    = [t for t, fb in feedback_results.items() if fb.get("status") == "ok"]

    prompt = f"""
You are a senior software architect analyzing code review results.

USER REQUEST: "{state['user_request']}"

MODULES STATUS:
- Need fixing : {error_modules}
- Already OK  : {ok_modules}

DETAILED CODE AND FEEDBACK:
{cross_context}

TASK:
Create a SPECIFIC fix plan. For each module that needs fixing:
1. Read the exact issues from Reviewer above.
2. Look at the code snippets to understand what's actually wrong.
3. Check cross-module dependencies:
   - Does UI call a function that DB hasn't defined?
   - Does API reference a model that DB schema is missing?
4. Write a fix instruction that is:
   - SPECIFIC: mention exact function names, class names, variable names
   - ACTIONABLE: say exactly what to add/change/remove
   - CROSS-AWARE: mention if another module needs to match this change

BAD example:  "Fix the database code"
GOOD example: "Add get_by_id(user_id: int) -> dict to UserDB class,
               returning {{'id', 'name', 'email'}} — UI's user_detail() calls it on line 45"

Return ONLY this JSON, no explanation:
{{
  "summary": "1-2 sentences: what are the main issues overall",
{fix_fields}
}}

Rules:
- For modules in {ok_modules}: set their fix field to "" (empty string)
- For modules in {error_modules}: write specific, detailed fix instruction
- If module A's fix requires module B to change, mention it explicitly
"""

    response = llm.invoke(prompt)
    result   = parse_json_safe(response)

    # ── Fallback nếu LLM fail ────────────────────────────────
    if not result:
        log_step(iteration, "EVALUATOR", "⚠️ JSON lỗi — dùng fallback fix plan")
        result = {"summary": "Errors found — fix required"}
        for t in active_types:
            fb  = feedback_results.get(t, {})   # ← .get() tránh KeyError
            key = f"fix_{t.lower()}"
            if fb.get("status") != "ok":
                suggestions = fb.get("suggestions", [])
                result[key] = suggestions[0] if suggestions else f"Fix issues in {t} module"
            else:
                result[key] = ""

    return result


def evaluator_node(state: AgentState) -> dict:
    if state["status"] == "stopped":
        return {}

    iteration    = state["iteration"]
    log_step(iteration, "EVALUATOR", "Đang đánh giá...")

    active_types = state.get("active_task_types", ["UI", "DB"])

    # ── Thu thập feedback của tất cả module ─────────────────
    feedback_results = {}
    for t in active_types:
        fb_field = TASK_TYPES.get(t, {}).get("feedback_field", f"feedback_{t.lower()}")
        feedback_results[t] = state.get(fb_field, {})

    all_ok = all(fb.get("status") == "ok" for fb in feedback_results.values())

    # ── In bảng kết quả ──────────────────────────────────────
    print(f"\n  {'─'*45}")
    print(f"  {'MODULE':<8} {'SYNTAX':<8} {'PYLINT':<8} {'LLM':<6} {'SCORE'}")
    print(f"  {'─'*45}")
    for t, fb in feedback_results.items():
        syntax = "✅" if fb.get("passed_syntax") else "❌"
        pylint = "✅" if fb.get("passed_pylint") else "❌"
        llm_r  = "✅" if fb.get("llm_review") == "ok" else "❌"
        score  = fb.get("quality_score", "?")
        print(f"  {t:<8} {syntax:<8} {pylint:<8} {llm_r:<6} {score}/10")
    print(f"  {'─'*45}")

    if all_ok:
        print(f"\n{'🟢'*25}")
        print("  ✅ PIPELINE HOÀN THÀNH!")
        print(f"  Code tại: output/iteration_{iteration}/")
        print(f"{'🟢'*25}")
        confirm = input("\n  Chốt? [Enter] hoặc [s] chạy thêm: ").strip()

        status   = "done" if confirm.lower() != "s" else "running"
        all_good = status == "done"
        new_plan = {}

        save_log(state.get("history", []))
        return {
            "all_good":           all_good,
            "new_plan":           new_plan,
            "status":             status,
            "tester_retry_count": 0,   # ← reset khi thành công
            "history": [{"iteration": iteration, "node": "EVALUATOR", "content": status}],
        }

    # ── Sinh smart fix plan ──────────────────────────────────
    log_step(iteration, "EVALUATOR", "🧠 Đang phân tích cross-module dependencies...")

    new_plan = _generate_smart_fix_plan(
        state            = state,
        active_types     = active_types,
        feedback_results = feedback_results,
        iteration        = iteration,
    )

    print(f"\n  📋 Fix Plan:")
    print(f"  Summary: {new_plan.get('summary', '')}")
    for t in active_types:
        fix = new_plan.get(f"fix_{t.lower()}", "")
        if fix:
            print(f"\n  🔧 [{t}]: {fix}")
        else:
            print(f"  ✅ [{t}]: no fix needed")

    log_step(iteration, "EVALUATOR", f"⚠️ Fix plan:\n{new_plan}")
    save_log(state.get("history", []))

    return {
        "all_good": False,
        "new_plan": new_plan,
        "status":   "running",
        "history":  [{"iteration": iteration, "node": "EVALUATOR", "content": "running"}],
    }