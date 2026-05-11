# nodes/reviewer.py
import ast
import subprocess
import sys
import os
import tempfile
from langchain_ollama import OllamaLLM
from state import AgentState
from utils import parse_json_safe, log_step
from memory.memory_manager import load_relevant_patterns
from nodes.task_config import TASK_TYPES

llm = OllamaLLM(
    model="deepseek-r1:14b",
    format="json",
    temperature=0.1,
)

# Nếu static issues >= ngưỡng này → bỏ qua LLM review (tiết kiệm thời gian)
SKIP_LLM_IF_STATIC_ISSUES_GTE = 5


# ── Static Analysis ───────────────────────────────────────────

def _check_syntax(code: str) -> dict:
    try:
        ast.parse(code)
        return {"ok": True, "error": None}
    except SyntaxError as e:
        return {"ok": False, "error": f"SyntaxError dòng {e.lineno}: {e.msg}"}
    except Exception as e:
        return {"ok": False, "error": f"ParseError: {str(e)}"}


def _check_pylint(code: str, task_type: str) -> list:
    """Chạy pylint dùng tempfile thực sự — tránh conflict giữa các lần chạy"""
    issues = []

    try:
        # Dùng NamedTemporaryFile thay vì fixed filename
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        result = subprocess.run(
            [
                sys.executable, "-m", "pylint", tmp_path,
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
                    # Thay absolute path bằng label dễ đọc
                    clean = line.replace(tmp_path, f"{task_type.lower()}_code.py").strip()
                    if clean:
                        issues.append(clean)

    except subprocess.TimeoutExpired:
        issues.append("Pylint timeout — bỏ qua static check")
    except FileNotFoundError:
        issues.append("Pylint chưa cài — chạy: pip install pylint")
    except Exception as e:
        issues.append(f"Pylint lỗi: {str(e)}")
    finally:
        # Luôn dọn file tạm dù có lỗi hay không
        try:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass

    return issues


def _static_check(code: str, task_type: str) -> dict:
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
    known_patterns = load_relevant_patterns(task_type)
    pattern_hint   = ""

    if known_patterns:
        lines = ["KNOWN ISSUES TO WATCH FOR (từ các lần chạy trước):"]
        for p in known_patterns:
            fix_text = f" → Fix: {p['fix']}" if p.get("fix") else ""
            lines.append(f"  - [{p['seen_count']}x] {p['issue']}{fix_text}")
        pattern_hint = "\n".join(lines)
        print(f"  📚 Loaded {len(known_patterns)} known patterns cho {task_type}")


    code_preview = code[:3000]
    code_note    = f"\n... (truncated, {len(code) - 3000} more chars)" if len(code) > 3000 else ""

    prompt = f"""
You are a senior Python code reviewer.
Review this {task_type} code carefully.
    
CODE TO REVIEW:
{code_preview}{code_note}

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

    # 2. Quyết định có chạy LLM không
    static_issue_count = len(static["static_issues"])

    if not static["passed_syntax"]:
        # Syntax lỗi → LLM không thể đọc được code
        llm_result = {
            "status":        "error",
            "issues":        [],
            "suggestions":   ["Fix syntax errors before LLM review"],
            "quality_score": 0,
        }
        print(f"  ⏭️  [{task_type}] Bỏ qua LLM review — syntax error")

    elif static_issue_count >= SKIP_LLM_IF_STATIC_ISSUES_GTE:
        # Quá nhiều lỗi static → không cần LLM, sửa static trước
        llm_result = {
            "status":        "error",
            "issues":        [],
            "suggestions":   [f"Fix {static_issue_count} static/pylint issues first"],
            "quality_score": max(0, 5 - static_issue_count),
        }
        print(f"  ⏭️  [{task_type}] Bỏ qua LLM review — {static_issue_count} static issues (>= {SKIP_LLM_IF_STATIC_ISSUES_GTE})")

    else:
        llm_result = _llm_review(code, task_type)

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

    iteration    = state["iteration"]
    log_step(iteration, "REVIEWER", "Bắt đầu review...")

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