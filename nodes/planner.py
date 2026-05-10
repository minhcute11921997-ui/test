# nodes/planner.py
from langchain_ollama import OllamaLLM
from state import AgentState, log_to_history
from utils import parse_json_safe, log_step

llm = OllamaLLM(
    model="qwen2.5:14b",
    format="json",
    temperature=0.1,
)

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
Tables: {list(state['db_schemas'].keys())}
Schemas: {state['db_schemas']}
"""

    prompt = f"""
You are a software project planner.
User request: "{state['user_request']}"
{context_block}
{db_block}
{extra}

Important:
- If existing code is provided, plan tasks to EXTEND it, not rewrite from scratch.
- If database schema is provided, reuse existing tables, do NOT create new ones.

Return ONLY this JSON structure, no explanation:
{{
  "tasks": [
    {{"id": 1, "name": "Task name", "type": "UI", "description": "what to build"}},
    {{"id": 2, "name": "Task name", "type": "DB", "description": "what to build"}}
  ]
}}
"""

    log_step(iteration, "PLANNER", "Đang tạo plan...")
    response = llm.invoke(prompt)
    plan = parse_json_safe(response)

    if not plan:
        plan = {
            "tasks": [
                {"id": 1, "name": "Build UI",      "type": "UI", "description": "Basic UI"},
                {"id": 2, "name": "Build Database", "type": "DB", "description": "Basic DB"},
            ]
        }
        log_step(iteration, "PLANNER", "⚠️ JSON lỗi — dùng fallback plan")

    original_plan = state.get("original_plan", {})
    if iteration == 1:
        original_plan = plan

    history = state.get("history", [])
    history.append({"iteration": iteration, "node": "PLANNER", "content": str(plan)})

    log_step(iteration, "PLANNER", f"✅ Plan tạo xong:\n{plan}")

    # ← Chỉ trả về field thay đổi
    return {
    "iteration":     iteration,
    "current_plan":  plan,
    "original_plan": original_plan,
    "history": [{"iteration": iteration, "node": "PLANNER", "content": str(plan)}],
    # ← list chỉ có 1 item mới, LangGraph tự nối vào
}