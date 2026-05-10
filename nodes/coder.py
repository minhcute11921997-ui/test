# nodes/coder.py
from langchain_ollama import OllamaLLM
from state import AgentState, log_to_history
from utils import log_step, save_code
from nodes.task_config import TASK_TYPES

llm_coder = OllamaLLM(
    model="qwen2.5-coder:7b",
    temperature=0.1,
)

def _run_coder(state: AgentState, task_type: str) -> str:
    iteration = state["iteration"]
    plan      = state["current_plan"]

    task = next(
        (t for t in plan.get("tasks", []) if t["type"] == task_type),
        {"name": task_type, "description": f"Build {task_type}"}
    )

    # ── Lấy field động từ task_config ───────────────────────
    config       = TASK_TYPES.get(task_type, {})
    code_field   = config.get("state_field",    f"code_{task_type.lower()}")
    fb_field     = config.get("feedback_field", f"feedback_{task_type.lower()}")

    prev_code     = state.get(code_field, "")
    prev_feedback = state.get(fb_field, {})
    # ────────────────────────────────────────────────────────

    fix_instruction = ""
    new_plan = state.get("new_plan", {})
    if new_plan:
        fix_instruction = new_plan.get(f"fix_{task_type.lower()}", "")


    # ── Xây dựng prompt theo tình huống ──
    if prev_code and prev_feedback.get("status") == "error":
        # Vòng 2+: có lỗi cần sửa
        prompt = f"""
You are an expert Python developer fixing buggy code.

PREVIOUS CODE WITH ISSUES:
{prev_code}

ISSUES FOUND:
{prev_feedback.get('issues', [])}

SUGGESTIONS:
{prev_feedback.get('suggestions', [])}

FIX INSTRUCTION:
{fix_instruction}

Fix the code above. Return ONLY the fixed code, no explanation.
"""

    elif prev_code and prev_feedback.get("status") == "ok" and fix_instruction:
        # Vòng 2+: code ok nhưng cần chỉnh để đồng bộ
        prompt = f"""
You are an expert Python developer improving existing code.

CURRENT CODE:
{prev_code}

IMPROVEMENT NEEDED:
{fix_instruction}

Return ONLY the improved code, no explanation.
"""

    else:
        # ── Vòng 1: viết mới ──

        # Code từ module bên kia để đồng bộ
        cross_context = ""
        if task_type == "DB" and state.get("code_ui"):
            cross_context = state["code_ui"][:400]
        elif task_type == "UI" and state.get("code_db"):
            cross_context = state["code_db"][:400]

        # Code hiện có từ dự án gốc
        existing = state.get("existing_code", {})
        relevant_code = ""
        for fname, code in existing.items():
            if task_type == "UI" and any(k in fname.lower() for k in ["ui", "view", "template", "html", "frontend"]):
                relevant_code += f"\n# EXISTING: {fname}\n{code[:600]}\n"
            if task_type == "DB" and any(k in fname.lower() for k in ["db", "model", "database", "schema"]):
                relevant_code += f"\n# EXISTING: {fname}\n{code[:600]}\n"

        context = state.get("context_summary", "")

        prompt = f"""
You are an expert Python developer.
Task: {task['name']}
Description: {task['description']}

{"PROJECT CONTEXT:" if context else ""}
{context[:500] if context else ""}

{"EXISTING CODE TO EXTEND:" if relevant_code else ""}
{relevant_code}

{"RELATED CODE FROM OTHER MODULE:" if cross_context else ""}
{cross_context}

{"Extend the existing code above." if relevant_code else "Write clean, working Python code."}
Return ONLY the code, no explanation.
"""

    log_step(iteration, f"CODER {task_type}",
             f"{'🔧 Sửa lỗi' if prev_code else '✍️ Viết mới'}: {task['name']}...")

    code = llm_coder.invoke(prompt)

    folder = f"output/iteration_{iteration}"
    filename = f"{folder}/{task_type.lower()}_code.py"
    save_code(code, filename)

    log_step(iteration, f"CODER {task_type}", f"✅ Xong — {filename}")
    return code


def coder_a_node(state: AgentState) -> dict:
    """Coder A — viết UI"""
    if state["status"] == "stopped":
        return {}

    code = _run_coder(state, "UI")

    return {
        "code_ui": code,
        "history": [{
            "iteration": state["iteration"],
            "node": "CODER A",
            "content": "UI code generated",
        }],
    }


def coder_b_node(state: AgentState) -> dict:
    """Coder B — viết DB"""
    if state["status"] == "stopped":
        return {}

    code = _run_coder(state, "DB")

    return {
        "code_db": code,
        "history": [{
            "iteration": state["iteration"],
            "node": "CODER B",
            "content": "DB code generated",
        }],
    }

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
            "history": [{"iteration": state["iteration"],
                         "node": f"CODER {task_type}",
                         "content": f"{task_type} code generated"}],
        }
    coder_node.__name__ = f"coder_{task_type.lower()}_node"
    return coder_node


# Tạo sẵn các node chuẩn
coder_a_node    = make_coder_node("UI")
coder_b_node    = make_coder_node("DB")
coder_api_node  = make_coder_node("API")
coder_auth_node = make_coder_node("AUTH")
coder_test_node = make_coder_node("TEST")