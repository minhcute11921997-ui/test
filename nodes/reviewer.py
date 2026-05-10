# nodes/reviewer.py
import ast
import subprocess
import sys
import os
from langchain_ollama import OllamaLLM
from state import AgentState
from utils import parse_json_safe, log_step
from memory.memory_manager import load_relevant_patterns
from nodes.task_config import TASK_TYPES

llm = OllamaLLM(
    model="qwen2.5:14b",
    format="json",
    temperature=0.1,
)


# ── Static Analysis ───────────────────────────────────────────

def _check_syntax(code: str) -> dict:
    """Kiểm tra syntax bằng ast"""
    try:
        ast.parse(code)
        return {"ok": True, "error": None}
    except SyntaxError as e:
        return {"ok": False, "error": f"SyntaxError dòng {e.lineno}: {e.msg}"}
    except Exception as e:
        return {"ok": False, "error": f"ParseError: {str(e)}"}


def _check_pylint(code: str, task_type: str) -> list:
    """Chạy pylint — chỉ lấy lỗi E (error), bỏ warning"""
    issues = []
    os.makedirs("logs", exist_ok=True)
    tmp_file = f"logs/tmp_{task_type.lower()}.py"

    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(code)

        result = subprocess.run(
            [
                sys.executable, "-m", "pylint", tmp_file,
                "--errors-only",
                "--output-format=text",
                "--score=no",
                "--disable=C,R,W",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )

        if result.stdout.strip():
            ERROR_CODES = ["E0", "E1", "F0", "error"]
            for line in result.stdout.strip().split("\n"):
                if any(err_code in line for err_code in ERROR_CODES):
                    clean = line.strip()
                    if clean:
                        issues.append(clean)

    except subprocess.TimeoutExpired:
        issues.append("Pylint timeout — bỏ qua static check")
    except FileNotFoundError:
        issues.append("Pylint chưa cài — chạy: pip install pylint")
    except Exception as e:
        issues.append(f"Pylint lỗi: {str(e)}")
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)

    return issues


def _static_check(code: str, task_type: str) -> dict:
    """Gộp syntax check + pylint"""
    syntax = _check_syntax(code)
    if not syntax["ok"]:
        return {
            "static_status": "error",
            "static_issues": [syntax["error"]],
            "passed_syntax": False,
            "passed_pylint": False,
        }

    pylint_issues = _check_pylint(code, task_type)
    return {
        "static_status": "error" if pylint_issues else "ok",
        "static_issues": pylint_issues,
        "passed_syntax": True,
        "passed_pylint": len(pylint_issues) == 0,
    }


# ── LLM Review ────────────────────────────────────────────────

def _llm_review(code: str, task_type: str) -> dict:
    """LLM đọc code và nhận xét — chạy sau khi syntax đã ok"""

    # Đọc pattern hay gặp từ memory
    known_patterns = load_relevant_patterns(task_type)
    pattern_hint   = ""

    if known_patterns:
        lines = ["KNOWN ISSUES TO WATCH FOR (từ các lần chạy trước):"]
        for p in known_patterns:
            fix_text = f" → Fix: {p['fix']}" if p.get("fix") else ""
            lines.append(f"  - [{p['seen_count']}x] {p['issue']}{fix_text}")
        pattern_hint = "\n".join(lines)
        print(f"  📚 Loaded {len(known_patterns)} known patterns cho {task_type}")

    prompt = f"""
You are a senior Python code reviewer.
Review this {task_type} code carefully.

CODE TO REVIEW:
{code[:1500]}

{pattern_hint}

Return ONLY this JSON, no explanation:
{{
  "status": "ok" or "error",
  "issues": [
    "describe issue 1 clearly",
    "describe issue 2 clearly"
  ],
  "suggestions": [
    "how to fix issue 1",
    "how to fix issue 2"
  ],
  "quality_score": 1 to 10
}}

Rules:
- "status" is "error" only if there are real bugs or missing logic
- Empty issues list means status must be "ok"
- Be specific, not generic
- Pay special attention to the KNOWN ISSUES listed above
"""
    response = llm.invoke(prompt)
    result   = parse_json_safe(response)

    if not result:
        return {
            "status":        "ok",
            "issues":        [],
            "suggestions":   [],
            "quality_score": 5,
        }

    return result


# ── Main Review Function ──────────────────────────────────────

def _review_code(code: str, task_type: str) -> dict:
    """Review đầy đủ: Static check + LLM review"""
    if not code or not code.strip():
        return {
            "status":        "error",
            "static_check":  "error",
            "llm_review":    "skipped",
            "issues":        ["Không có code để review"],
            "suggestions":   ["Coder cần sinh code trước"],
            "quality_score": 0,
            "passed_syntax": False,
            "passed_pylint": False,
        }

    # 1. Static check
    static = _static_check(code, task_type)

    # 2. LLM review (chỉ khi syntax ok)
    if static["passed_syntax"]:
        llm_result = _llm_review(code, task_type)
    else:
        llm_result = {
            "status":      "error",
            "issues":      [],
            "suggestions": ["Fix syntax errors before LLM review"],
            "quality_score": 0,
        }

    # 3. Gộp tất cả issues
    all_issues   = static["static_issues"] + llm_result.get("issues", [])
    final_status = "error" if all_issues else "ok"

    return {
        "status":        final_status,
        "static_check":  static["static_status"],
        "llm_review":    llm_result.get("status"),
        "issues":        all_issues,
        "suggestions":   llm_result.get("suggestions", []),
        "quality_score": llm_result.get("quality_score", 0),
        "passed_syntax": static["passed_syntax"],
        "passed_pylint": static["passed_pylint"],
    }


# ── Node Function ─────────────────────────────────────────────

def reviewer_node(state: AgentState) -> dict:
    if state["status"] == "stopped":
        return {}

    iteration = state["iteration"]
    log_step(iteration, "REVIEWER", "Bắt đầu review...")

    # Review động theo active_task_types
    active_types     = state.get("active_task_types", ["UI", "DB"])
    feedback_results = {}

    for t in active_types:
        config     = TASK_TYPES.get(t, {})
        code_field = config.get("state_field", f"code_{t.lower()}")
        code       = state.get(code_field, "")

        print(f"\n  🔍 Review {t}...")
        fb = _review_code(code, t)
        _print_review_result(t, fb)
        feedback_results[t] = fb

    # Log tổng kết
    summary = " | ".join(
        f"{'✅' if fb['status'] == 'ok' else '❌'} {t}: {fb.get('quality_score','?')}/10"
        for t, fb in feedback_results.items()
    )
    log_step(iteration, "REVIEWER", summary)

    # Build return dict động
    return_dict = {
        "history": [{
            "iteration": iteration,
            "node":      "REVIEWER",
            "content":   {f"feedback_{t.lower()}": fb for t, fb in feedback_results.items()},
        }]
    }
    for t, fb in feedback_results.items():
        config   = TASK_TYPES.get(t, {})
        fb_field = config.get("feedback_field", f"feedback_{t.lower()}")
        return_dict[fb_field] = fb

    return return_dict


def _print_review_result(task_type: str, feedback: dict):
    """In kết quả review dễ đọc"""
    status_icon = "✅" if feedback["status"] == "ok" else "❌"
    print(f"\n  {status_icon} [{task_type}] Syntax: {'✅' if feedback['passed_syntax'] else '❌'} | "
          f"Pylint: {'✅' if feedback['passed_pylint'] else '❌'} | "
          f"LLM: {feedback.get('llm_review', '?')} | "
          f"Score: {feedback.get('quality_score', '?')}/10")

    if feedback["issues"]:
        print(f"  ⚠️  Issues ({len(feedback['issues'])}):")
        for issue in feedback["issues"]:
            print(f"     • {issue}")

    if feedback["suggestions"]:
        print(f"  💡 Suggestions:")
        for s in feedback["suggestions"]:
            print(f"     → {s}")