# nodes/coder.py
import ast
import re
import os
from langchain_ollama import OllamaLLM
from state import AgentState
from utils import log_step, save_code, clean_code
from nodes.task_config import TASK_TYPES
from nodes.prompt_builder import build_coder_prompt

llm_coder = OllamaLLM(
    model="deepseek-coder-v2",
    temperature=0.1,
    num_predict=8192,
    num_ctx=16384,
)

MAX_RETRIES = 3


def _build_cross_context(state: AgentState, current_type: str) -> str:
    cross_context = ""
    active_types  = state.get("active_task_types", [])

    for other_type in active_types:
        if other_type == current_type:
            continue
        config     = TASK_TYPES.get(other_type, {})
        code_field = config.get("state_field", f"code_{other_type.lower()}")
        other_code = state.get(code_field, "")
        if other_code and other_code.strip():
            cross_context += f"\n# --- {other_type} MODULE ({config.get('desc','')}) ---\n"
            cross_context += other_code[:1200]
            cross_context += "\n"

    return cross_context


def extract_multiple_files(raw_output: str) -> dict | None:
    results = {}

    pattern1 = r"###?\s*([\w./\-]+\.\w+)\s*\n```(?:python|text|bash|sql|html|css|js|)?\s*\n(.*?)```"
    pattern2 = r"\*\*([\w./\-]+\.\w+)\*\*\s*\n```(?:python|text|bash|sql|html|css|js|)?\s*\n(.*?)```"
    pattern3 = r"#\s*[Ff]ile:\s*([\w./\-]+\.\w+)\s*\n```(?:python|text|bash|sql|html|css|js|)?\s*\n(.*?)```"

    for pattern in [pattern1, pattern2, pattern3]:
        matches = re.findall(pattern, raw_output, re.DOTALL)
        for fname, content in matches:
            fname = fname.strip()
            if fname not in results:
                results[fname] = content.strip()

    return results if len(results) >= 2 else None


def _validate_multi_output(files: dict, task_type: str) -> list:
    warnings = []
    has_py  = any(k.endswith(".py") for k in files)
    has_req = any("requirement" in k.lower() for k in files)

    if not has_py:
        warnings.append(f"[{task_type}] Không tìm thấy file .py trong output multi-file")
    if not has_req:
        warnings.append(f"[{task_type}] Không có requirements.txt — dependencies không được track")
    return warnings


def _run_coder(state: AgentState, task_type: str) -> str:
    iteration = state["iteration"]
    plan      = state.get("current_plan", {})

    task = next(
        (t for t in plan.get("tasks", []) if t["type"] == task_type),
        {"name": task_type, "description": f"Build {task_type}"}
    )

    config     = TASK_TYPES.get(task_type, {})
    code_field = config.get("state_field",    f"code_{task_type.lower()}")
    fb_field   = config.get("feedback_field", f"feedback_{task_type.lower()}")

    prev_code     = state.get(code_field, "")
    prev_feedback = state.get(fb_field, {})

    fix_instruction = ""
    new_plan = state.get("new_plan", {})
    if new_plan:
        fix_instruction = new_plan.get(f"fix_{task_type.lower()}", "")

    # ── Thu thập lỗi từ tester ──────────────────────────────────────
    test_issues       = state.get("test_issues", [])
    my_test_issues    = [i for i in test_issues    if f"[{task_type}]" in i]
    timeout_issues    = state.get("timeout_issues", [])
    my_timeout_issues = [i for i in timeout_issues if f"[{task_type}]" in i]
    hard_issues       = state.get("hard_test_issues", [])
    my_hard_issues    = [i for i in hard_issues    if f"[{task_type}]" in i]

    folder = f"output/iteration_{iteration}"
    os.makedirs(folder, exist_ok=True)

    # ── Xác định mode ───────────────────────────────────────────────
    is_first_run = not prev_code
    has_error    = (
        (prev_feedback.get("status") == "error")
        or bool(my_hard_issues)
        or bool(fix_instruction)
    )
    has_fix_hint = bool(my_timeout_issues)

    # ── Build relevant_code (chỉ dùng ở mode new) ──────────────────
    relevant_code = ""
    if is_first_run:
        existing = state.get("existing_code", {})
        keywords = {
            "UI":   ["ui", "view", "template", "html", "frontend"],
            "DB":   ["db", "model", "database", "schema"],
            "API":  ["api", "route", "endpoint", "handler"],
            "AUTH": ["auth", "login", "token", "jwt", "session"],
            "TEST": ["test", "spec", "fixture"],
        }
        kws = keywords.get(task_type, [task_type.lower()])
        for fname, code in existing.items():
            if any(k in fname.lower() for k in kws):
                relevant_code += f"\n# EXISTING: {fname}\n{code[:600]}\n"

    # ── Xác định error_detail (chỉ dùng ở mode fix) ─────────────────
    error_detail = ""
    if has_error and not is_first_run:
        if prev_feedback.get("status") == "error":
            error_detail += f"Reviewer issues: {prev_feedback.get('issues', [])}\n"
            error_detail += f"Reviewer suggestions: {prev_feedback.get('suggestions', [])}\n"
        if my_test_issues:
            error_detail += "Tester issues:\n" + "\n".join(my_test_issues)
        if my_hard_issues:
            error_detail += "Hard test issues:\n" + "\n".join(my_hard_issues)

    # ── Chọn mode và log ─────────────────────────────────────────────
    if is_first_run:
        log_step(iteration, f"CODER {task_type}", f"✍️ Viết mới: {task['name']}")
        mode = "new"
    elif has_error:
        log_step(iteration, f"CODER {task_type}",
                 f"🔧 Sửa lỗi — reviewer={prev_feedback.get('status')}, "
                 f"tester={len(my_test_issues)}, fix_hint={bool(fix_instruction)}")
        mode = "fix"
    elif has_fix_hint:
        log_step(iteration, f"CODER {task_type}",
                 f"⚡ Cải thiện — timeout={len(my_timeout_issues)}")
        mode = "improve"
    else:
        log_step(iteration, f"CODER {task_type}",
                 "♻️  Giữ nguyên — không có lỗi và không có yêu cầu mới")
        save_code(prev_code, f"{folder}/{task_type.lower()}_code.py")
        return prev_code

    # ── Build prompt động ────────────────────────────────────────────
    prompt = build_coder_prompt(
        task             = task,
        task_type        = task_type,
        mode             = mode,
        prev_code        = prev_code,
        error_detail     = error_detail,
        fix_instruction  = fix_instruction,
        cross_context    = _build_cross_context(state, task_type) if is_first_run else "",
        relevant_code    = relevant_code,
        context_summary  = state.get("context_summary", ""),
        timeout_issues   = my_timeout_issues,
    )

    # ── Gọi LLM với retry nếu syntax lỗi ────────────────────────────
    raw  = ""
    code = ""
    for attempt in range(1, MAX_RETRIES + 1):
        raw = llm_coder.invoke(prompt)

        # Kiểm tra multi-file trước
        multi = extract_multiple_files(raw)
        if multi:
            warns = _validate_multi_output(multi, task_type)
            for w in warns:
                print(f"  ⚠️  {w}")
            print(f"  📁 LLM trả về {len(multi)} files: {list(multi.keys())}")
            for fname, content in multi.items():
                save_code(content, f"{folder}/{fname}")
            main_file = next(
                (v for k, v in multi.items() if k.endswith(".py") and "requirement" not in k),
                list(multi.values())[0]
            )
            log_step(iteration, f"CODER {task_type}", f"✅ Xong (multi-file) — {folder}/")
            return main_file

        code = clean_code(raw)

        try:
            ast.parse(code)
            if attempt > 1:
                print(f"  ✅ Syntax OK sau {attempt} lần thử")
            break

        except SyntaxError as e:
            print(f"  ⚠️ Attempt {attempt}/{MAX_RETRIES} — SyntaxError: {e.msg} dòng {e.lineno}")
            if attempt < MAX_RETRIES:
                # Prompt retry tự động — chỉ truyền lỗi cụ thể
                prompt = build_coder_prompt(
                    task        = task,
                    task_type   = task_type,
                    mode        = "fix",
                    prev_code   = code,
                    error_detail= f"SyntaxError tại dòng {e.lineno}: {e.msg}",
                )
            else:
                print(f"  ❌ Vẫn lỗi sau {MAX_RETRIES} lần — giữ code gần nhất")

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