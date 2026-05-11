# nodes/planner.py
import json
from langchain_ollama import OllamaLLM
from state import AgentState
from utils import parse_json_safe, log_step
from memory.memory_manager import load_template, load_relevant_patterns
from nodes.task_config import TASK_TYPES, COMPLEXITY_HINTS

llm = OllamaLLM(
    model="qwen3.5:9b",
    format="json",
    temperature=0.1,
)


def _assess_complexity(user_request: str, context_summary: str) -> str:
    prompt = f"""
Classify the complexity of this software request.

REQUEST: "{user_request}"
CONTEXT: {context_summary[:300] if context_summary else "None"}

Rules:
- "simple"  = basic CRUD, single feature, no auth needed
- "medium"  = multiple features, needs API layer, no auth
- "complex" = full system, needs auth, tests, or 4+ distinct components

Return ONLY one word: simple, medium, or complex
"""
    result = llm.invoke(prompt).strip().lower()
    # Normalize phòng LLM trả linh tinh — parse_json_safe không dùng ở đây
    # vì format không phải json, chỉ lấy từ đầu tiên
    for level in ("simple", "medium", "complex"):
        if level in result:
            return level
    return "medium"


def planner_node(state: AgentState) -> dict:
    iteration = state["iteration"] + 1

    extra = ""
    if state.get("extra_requirement"):
        extra = f"\nAdditional requirement: {state['extra_requirement']}"
    if state.get("new_plan"):
        extra += f"\nPrevious issues to fix: {state['new_plan']}"

    context_block = ""
    if state.get("context_summary"):
        context_block = f"""
PROJECT CONTEXT:
{state['context_summary']}
EXISTING FILES: {list(state.get('existing_code', {}).keys())}
"""

    db_block = ""
    if state.get("db_schemas"):
        db_block = f"""
EXISTING DATABASE (reuse these tables):
Tables:  {list(state['db_schemas'].keys())}
Schemas: {state['db_schemas']}
"""

    # ── Complexity: đánh giá lần đầu, tái dụng các vòng sau ──
    complexity = state.get("complexity", "")  # ← đọc từ state

    if not complexity:
        # Chỉ gọi LLM ở vòng 1 (hoặc khi chưa có)
        log_step(iteration, "PLANNER", "🔍 Đánh giá độ phức tạp...")
        complexity = _assess_complexity(
            user_request    = state["user_request"],
            context_summary = state.get("context_summary", ""),
        )
        log_step(iteration, "PLANNER", f"📊 Độ phức tạp: {complexity.upper()}")
    else:
        print(f"\n  ♻️  Tái dụng complexity từ vòng trước: {complexity.upper()}")

    complexity_hint = COMPLEXITY_HINTS.get(complexity, COMPLEXITY_HINTS["medium"])

    allowed_types     = list(TASK_TYPES.keys())
    type_descriptions = "\n".join(
        f'  - "{t}": {info["desc"]}' for t, info in TASK_TYPES.items()
    )

    prompt = f"""
You are a software project planner.
User request: "{state['user_request']}"
{context_block}
{db_block}
{extra}

COMPLEXITY ASSESSMENT: {complexity.upper()} → Suggested: {complexity_hint}

AVAILABLE TASK TYPES:
{type_descriptions}

Important rules:
- If existing code is provided, plan tasks to EXTEND it, not rewrite.
- If database schema is provided, reuse existing tables.
- Choose task types based on complexity assessment above.
- Simple requests: use only UI + DB.
- Medium requests: use UI + DB + API.
- Complex requests: use UI + DB + API + AUTH and/or TEST.
- Each task must have a unique type from the list above.
- Maximum 5 tasks total.

Return ONLY this JSON structure, no explanation:
{{
  "complexity": "{complexity}",
  "tasks": [
    {{"id": 1, "name": "Task name", "type": "UI",  "description": "what to build"}},
    {{"id": 2, "name": "Task name", "type": "DB",  "description": "what to build"}},
    {{"id": 3, "name": "Task name", "type": "API", "description": "what to build"}}
  ]
}}
"""

    log_step(iteration, "PLANNER", "Đang tạo plan...")
    response = llm.invoke(prompt)
    plan     = parse_json_safe(response)

    if not plan or "tasks" not in plan:
        plan = {
            "complexity": complexity,
            "tasks": [
                {"id": 1, "name": "Build UI",      "type": "UI", "description": "Basic UI"},
                {"id": 2, "name": "Build Database", "type": "DB", "description": "Basic DB"},
            ]
        }
        log_step(iteration, "PLANNER", "⚠️ JSON lỗi — dùng fallback plan")

    valid_tasks = [t for t in plan["tasks"] if t.get("type") in TASK_TYPES]
    if not valid_tasks:
        valid_tasks = plan["tasks"]
    plan["tasks"] = valid_tasks

    active_types = [t["type"] for t in plan["tasks"]]

    original_plan = state.get("original_plan", {})
    if iteration == 1:
        original_plan = plan

    log_step(iteration, "PLANNER",
             f"✅ Plan ({complexity.upper()}) — {len(plan['tasks'])} tasks: {active_types}\n{plan}")

    is_retry = state.get("tester_retry_count", 0) > 0
    return {
        "iteration":          iteration,
        "current_plan":       plan,
        "original_plan":      original_plan,
        "active_task_types":  active_types,
        "complexity":         complexity,    # ← lưu vào state để vòng sau tái dụng
        "tester_retry_count": 0,             # ← reset mỗi vòng mới, không chỉ khi all_ok
        "test_issues":        [],  # ← reset để CASE B không đọc lỗi cũ
        "test_results":       [],  # ← reset để CASE B không đọc kết quả cũ
        "hard_test_issues": [] if not is_retry else state.get("hard_test_issues", []),
        "timeout_issues":   [] if not is_retry else state.get("timeout_issues", []),
        "history": [{"iteration": iteration, "node": "PLANNER", "content": str(plan)}],
    }