# nodes/coder.py
import ast
from langchain_ollama import OllamaLLM
from state import AgentState
from utils import log_step, save_code, clean_code
from nodes.task_config import TASK_TYPES

llm_coder = OllamaLLM(
    model="qwen2.5-coder:7b",
    temperature=0.1,
    stop=["```", "Hope", "Sure", "Note:", "Explanation:"],
)

MAX_RETRIES = 2

STRICT_CODE_INSTRUCTION = """
CRITICAL RULES — MUST FOLLOW:
- Return ONLY raw Python code
- NO markdown (no ```python, no ```)
- NO explanation text before or after the code
- NO "Here is...", "Hope this...", "Sure!" etc.
- Start directly with: import / from / class / def / #
"""


def _run_coder(state: AgentState, task_type: str) -> str:
    iteration = state["iteration"]
    plan      = state["current_plan"]

    task = next(
        (t for t in plan.get("tasks", []) if t["type"] == task_type),
        {"name": task_type, "description": f"Build {task_type}"}
    )

    # ── Lấy field động từ task_config ───────────────────────
    config        = TASK_TYPES.get(task_type, {})
    code_field    = config.get("state_field",    f"code_{task_type.lower()}")
    fb_field      = config.get("feedback_field", f"feedback_{task_type.lower()}")

    prev_code     = state.get(code_field, "")
    prev_feedback = state.get(fb_field, {})

    # ── Lấy fix instruction từ Evaluator ────────────────────
    fix_instruction = ""
    new_plan = state.get("new_plan", {})
    if new_plan:
        fix_instruction = new_plan.get(f"fix_{task_type.lower()}", "")

    # ── Xây dựng prompt theo tình huống ─────────────────────
    if prev_code and prev_feedback.get("status") == "error":
        # Vòng 2+: có lỗi cần sửa
        prompt = f"""
{STRICT_CODE_INSTRUCTION}

You are an expert Python developer fixing buggy code.

PREVIOUS CODE WITH ISSUES:
{prev_code}

ISSUES FOUND:
{prev_feedback.get('issues', [])}

SUGGESTIONS:
{prev_feedback.get('suggestions', [])}

FIX INSTRUCTION:
{fix_instruction}

Fix the code above. Return ONLY the fixed Python code.
"""

    elif prev_code and prev_feedback.get("status") == "ok" and fix_instruction:
        # Vòng 2+: code ok nhưng cần chỉnh để đồng bộ
        prompt = f"""
{STRICT_CODE_INSTRUCTION}

You are an expert Python developer improving existing code.

CURRENT CODE:
{prev_code}

IMPROVEMENT NEEDED:
{fix_instruction}

Return ONLY the improved Python code.
"""

    else:
        # ── Vòng 1: viết mới ──────────────────────────────
        cross_context = ""
        if task_type == "DB" and state.get("code_ui"):
            cross_context = state["code_ui"][:400]
        elif task_type == "UI" and state.get("code_db"):
            cross_context = state["code_db"][:400]
        else:
            # Dynamic cross-context cho task type khác
            for other_type, other_config in TASK_TYPES.items():
                if other_type == task_type:
                    continue
                other_code = state.get(other_config.get("state_field", ""), "")
                if other_code:
                    cross_context += f"\n# --- {other_type} MODULE ---\n{other_code[:300]}\n"

        existing  = state.get("existing_code", {})
        keywords  = {
            "UI":   ["ui", "view", "template", "html", "frontend"],
            "DB":   ["db", "model", "database", "schema"],
            "API":  ["api", "route", "endpoint", "handler"],
            "AUTH": ["auth", "login", "token", "jwt", "session"],
            "TEST": ["test", "spec", "fixture"],
        }
        relevant_code = ""
        kws = keywords.get(task_type, [task_type.lower()])
        for fname, code in existing.items():
            if any(k in fname.lower() for k in kws):
                relevant_code += f"\n# EXISTING: {fname}\n{code[:600]}\n"

        context = state.get("context_summary", "")

        prompt = f"""
{STRICT_CODE_INSTRUCTION}

You are an expert Python developer.
Task: {task['name']}
Description: {task['description']}

{"PROJECT CONTEXT:" if context else ""}
{context[:500] if context else ""}

{"EXISTING CODE TO EXTEND:" if relevant_code else ""}
{relevant_code}

{"RELATED CODE FROM OTHER MODULES:" if cross_context else ""}
{cross_context}

{"Extend the existing code above." if relevant_code else "Write clean, working Python code."}
Return ONLY the Python code.
"""

    log_step(iteration, f"CODER {task_type}",
             f"{'🔧 Sửa lỗi' if prev_code else '✍️ Viết mới'}: {task['name']}...")

    # ── Gọi LLM với retry nếu syntax lỗi ────────────────────
    code = ""
    for attempt in range(1, MAX_RETRIES + 1):
        raw  = llm_coder.invoke(prompt)
        code = clean_code(raw)

        try:
            ast.parse(code)
            if attempt > 1:
                print(f"  ✅ Syntax OK sau {attempt} lần thử")
            break

        except SyntaxError as e:
            print(f"  ⚠️ Attempt {attempt}/{MAX_RETRIES} — SyntaxError: {e.msg} dòng {e.lineno}")

            if attempt < MAX_RETRIES:
                prompt = f"""
{STRICT_CODE_INSTRUCTION}

You are an expert Python developer.
Your previous attempt had a syntax error:
  Error: {e.msg} at line {e.lineno}

PREVIOUS ATTEMPT (with error):
{code}

Fix the syntax error and return ONLY the corrected Python code.
"""
            else:
                print(f"  ❌ Vẫn lỗi sau {MAX_RETRIES} lần — giữ code gần nhất")
    # ────────────────────────────────────────────────────────

    folder   = f"output/iteration_{iteration}"
    filename = f"{folder}/{task_type.lower()}_code.py"
    save_code(code, filename)

    log_step(iteration, f"CODER {task_type}", f"✅ Xong — {filename}")
    return code


def make_coder_node(task_type: str):
    """Factory tạo coder node cho bất kỳ task type nào"""
    def coder_node(state: AgentState) -> dict:
        if state["status"] == "stopped":
            return {}

        code = _run_coder(state, task_type)

        config     = TASK_TYPES.get(task_type, {})
        code_field = config.get("state_field", f"code_{task_type.lower()}")

        return {
            code_field: code,
            "history": [{
                "iteration": state["iteration"],
                "node":      f"CODER {task_type}",
                "content":   f"{task_type} code generated",
            }],
        }

    coder_node.__name__ = f"coder_{task_type.lower()}_node"
    return coder_node


# Các node chuẩn
coder_a_node    = make_coder_node("UI")
coder_b_node    = make_coder_node("DB")
coder_api_node  = make_coder_node("API")
coder_auth_node = make_coder_node("AUTH")
coder_test_node = make_coder_node("TEST")