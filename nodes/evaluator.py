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

MIN_QUALITY_SCORE = 20   # score tối thiểu để coi là "ok"


def _build_cross_context(state: AgentState, active_types: list,
                         feedback_results: dict) -> str:
    hard_test_issues = state.get("hard_test_issues", [])
    timeout_issues   = state.get("timeout_issues", [])
    lines = []

    for t in active_types:
        config     = TASK_TYPES.get(t, {})
        code_field = config.get("state_field", f"code_{t.lower()}")
        code       = state.get(code_field, "")
        fb         = feedback_results.get(t, {})

        # Tester issues theo module
        my_test_issues    = [i for i in hard_test_issues if f"[{t}]" in i]
        my_timeout_issues = [i for i in timeout_issues   if f"[{t}]" in i]

        lines.append(f"\n{'='*50}")
        lines.append(f"MODULE: {t}")
        lines.append(f"STATUS: {fb.get('status', 'unknown')}")
        lines.append(f"SCORE:  {fb.get('quality_score', '?')}/10")

        issues = fb.get("issues", [])
        if issues:
            lines.append(f"REVIEWER ISSUES ({len(issues)}):")
            for issue in issues:
                lines.append(f"  ❌ {issue}")

        if my_test_issues:
            lines.append(f"TESTER ISSUES ({len(my_test_issues)}):")
            for ti in my_test_issues:
                lines.append(f"  🧪 {ti}")

        if my_timeout_issues:
            lines.append(f"TIMEOUT ISSUES ({len(my_timeout_issues)}):")
            for ti in my_timeout_issues:
                lines.append(f"  ⏱️ {ti}")

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


def _generate_smart_fix_plan(state, active_types, feedback_results, iteration):
    hard_test_issues = state.get("hard_test_issues", [])
    cross_context    = _build_cross_context(state, active_types, feedback_results)

    fix_fields = "\n".join(
        f'  "fix_{t.lower()}": "specific fix instruction for {t} or empty string if ok"'
        for t in active_types
    )

    # Module bị lỗi: xét cả reviewer lẫn tester
    error_modules = [
        t for t in active_types
        if feedback_results.get(t, {}).get("status") != "ok"
        or any(f"[{t}]" in i for i in hard_test_issues)
        or feedback_results.get(t, {}).get("quality_score", 0) < MIN_QUALITY_SCORE
        or bool(feedback_results.get(t, {}).get("suggestions", []))
    ]
    ok_modules = [t for t in active_types if t not in error_modules]

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
1. Read the exact issues from Reviewer AND Tester above.
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

    if not result:
        log_step(iteration, "EVALUATOR", "⚠️ JSON lỗi — dùng fallback fix plan")
        result = {"summary": "Errors found — fix required"}
        for t in active_types:
            fb  = feedback_results.get(t, {})
            key = f"fix_{t.lower()}"
            if t in error_modules:
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

    active_types     = state.get("active_task_types", ["UI", "DB"])
    hard_test_issues = state.get("hard_test_issues", [])
    auto_mode        = state.get("auto_mode", False)

    # Thu thập feedback reviewer
    feedback_results = {}
    for t in active_types:
        fb_field = TASK_TYPES.get(t, {}).get("feedback_field", f"feedback_{t.lower()}")
        feedback_results[t] = state.get(fb_field, {})

    # all_ok: xét cả reviewer score + tester hard issues
    all_ok = (
        all(fb.get("status") == "ok" for fb in feedback_results.values())
        and all(fb.get("quality_score", 0) >= MIN_QUALITY_SCORE
                for fb in feedback_results.values())
        and not hard_test_issues
    )

    # In bảng kết quả
    print(f"\n  {'─'*50}")
    print(f"  {'MODULE':<8} {'SYNTAX':<8} {'PYLINT':<8} {'LLM':<6} {'SCORE':<8} {'TEST'}")
    print(f"  {'─'*50}")
    for t, fb in feedback_results.items():
        syntax     = "✅" if fb.get("passed_syntax") else "❌"
        pylint     = "✅" if fb.get("passed_pylint") else "❌"
        llm_r      = "✅" if fb.get("llm_review") == "ok" else "❌"
        score      = fb.get("quality_score", "?")
        test_ok    = "✅" if not any(f"[{t}]" in i for i in hard_test_issues) else "❌"
        score_icon = "✅" if str(score).isdigit() and int(score) >= MIN_QUALITY_SCORE else "⚠️"
        print(f"  {t:<8} {syntax:<8} {pylint:<8} {llm_r:<6} {score_icon}{score}/10  {test_ok}")
    print(f"  {'─'*50}")

    if all_ok:
        print(f"\n{'🟢'*25}")
        print("  ✅ PIPELINE HOÀN THÀNH!")
        print(f"  Code tại: output/iteration_{iteration}/")
        print(f"{'🟢'*25}")

        if auto_mode:
            confirm = ""   # tự động chốt, không block
        else:
            confirm = input("\n  Chốt? [Enter] hoặc [s] chạy thêm: ").strip()

        status   = "done" if confirm.lower() != "s" else "running"
        all_good = status == "done"
        save_log(state.get("history", []))
        return {
            "all_good":           all_good,
            "new_plan":           {},
            "status":             status,
            "tester_retry_count": 0,
            "history": [{"iteration": iteration, "node": "EVALUATOR",
                         "content": status}],
        }

    # Sinh fix plan
    log_step(iteration, "EVALUATOR", "🧠 Đang phân tích cross-module dependencies...")
    new_plan = _generate_smart_fix_plan(
        state=state, active_types=active_types,
        feedback_results=feedback_results, iteration=iteration,
    )

    print(f"\n  📋 Fix Plan:")
    print(f"  Summary: {new_plan.get('summary', '')}")
    for t in active_types:
        fix = new_plan.get(f"fix_{t.lower()}", "")
        print(f"\n  {'🔧' if fix else '✅'} [{t}]: {fix if fix else 'no fix needed'}")

    log_step(iteration, "EVALUATOR", f"⚠️ Fix plan:\n{new_plan}")
    save_log(state.get("history", []))

    return {
        "all_good": False,
        "new_plan": new_plan,
        "status":   "running",
        "history":  [{"iteration": iteration, "node": "EVALUATOR",
                      "content": "running"}],
    }