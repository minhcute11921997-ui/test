# nodes/tester.py
import os
import re
import subprocess
import tempfile
import threading
from langchain_ollama import OllamaLLM
from state import AgentState
from utils import log_step
from nodes.task_config import TASK_TYPES

llm = OllamaLLM(
    model="qwen2.5:14b",
    temperature=0.1,
    num_predict=1024,
)


# ══════════════════════════════════════════════
# LỚP 1 — SYNTAX CHECK
# ══════════════════════════════════════════════

def check_syntax(code: str, label: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                     delete=False, encoding="utf-8") as f:
        f.write(code)
        fname = f.name
    result = subprocess.run(
        ["python", "-m", "py_compile", fname],
        capture_output=True, text=True
    )
    os.unlink(fname)
    return {
        "passed": result.returncode == 0,
        "error":  result.stderr.strip().replace(fname, f"{label}.py")
    }


# ══════════════════════════════════════════════
# LỚP 2 — STATIC ANALYSIS
# ══════════════════════════════════════════════

# Mỗi rule: (pattern_phải_có, message_nếu_thiếu)
# Logic đúng: nếu pattern KHÔNG tìm thấy → báo lỗi
STATIC_RULES_BY_TYPE = {
    "DB": [
        (r"def \w+",                "Không có hàm nào được định nghĩa trong DB module"),
        (r"sqlite3|sqlalchemy|psycopg2|pymongo",
                                    "Không tìm thấy import thư viện database"),
        (r"try\s*:|except\s+",      "Thiếu error handling (try/except) trong DB operations"),
    ],
    "UI": [
        (r"def \w+",                "Không có hàm nào được định nghĩa trong UI module"),
        (r"input\(|flask|fastapi|streamlit|tkinter|PyQt",
                                    "Không tìm thấy UI framework hoặc input handler"),
    ],
    "API": [
        (r"@app\.|@router\.|def \w+_route|def \w+_handler|def \w+_endpoint",
                                    "Không tìm thấy route/endpoint definitions"),
        (r"flask|fastapi|aiohttp|django",
                                    "Không tìm thấy web framework import"),
    ],
    "AUTH": [
        (r"def \w*(login|logout|register|verify|authenticate|token)\w*",
                                    "Không tìm thấy hàm authentication"),
        (r"password|token|jwt|session|hash",
                                    "Không tìm thấy xử lý credentials/token"),
    ],
    "TEST": [
        (r"def test_\w+",           "Không tìm thấy test functions (def test_...)"),
        (r"assert ",                "Không có assert statements trong tests"),
    ],
}

# Rules áp dụng cho mọi module
STATIC_RULES_COMMON = [
    (r"^(import |from )",           "Không có import statement nào"),
]


def check_static(code: str, task_type: str) -> list:
    issues = []
    type_rules   = STATIC_RULES_BY_TYPE.get(task_type, [])
    common_rules = STATIC_RULES_COMMON

    for pattern, message in (common_rules + type_rules):
        if not re.search(pattern, code, re.MULTILINE):
            issues.append(f"⚠️  {message}")
    return issues


def check_pylint(code: str, label: str) -> list:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                     delete=False, encoding="utf-8") as f:
        f.write(code)
        fname = f.name
    result = subprocess.run(
        ["python", "-m", "pylint", fname,
         "--disable=C,R", "--score=no", "--output-format=text"],
        capture_output=True, text=True
    )
    os.unlink(fname)
    lines = [
        l.replace(fname, f"{label}.py").strip()
        for l in result.stdout.splitlines()
        if re.search(r"\s[WE]\d{4}:", l)
    ]
    return lines[:5]


# ══════════════════════════════════════════════
# LỚP 3 — PYTEST
# ══════════════════════════════════════════════

def generate_fallback_test(source_code: str) -> str:
    """Sinh test tối thiểu không cần LLM — dựa trên def có trong code"""
    funcs = re.findall(r"^def (\w+)\(", source_code, re.MULTILINE)
    lines = [
        "import sys, os",
        "sys.path.insert(0, os.path.dirname(__file__))",
        "import module",
        "",
    ]
    if not funcs:
        lines.append("def test_module_imports(): pass")
    else:
        for func in funcs[:5]:
            lines.append(f"def test_{func}_exists():")
            lines.append(f"    assert hasattr(module, '{func}'), '{func} not found'")
            lines.append("")
    return "\n".join(lines)


def generate_test_code_llm(source_code: str, label: str) -> str:
    prompt = f"""You are a Python test engineer. Write pytest test cases for the code below.

STRICT RULES:
1. Use sqlite3.connect(":memory:") for ALL database connections
2. Always run CREATE TABLE IF NOT EXISTS before any INSERT/SELECT
3. Test every function with happy path
4. Test edge cases: None input, price=0, stock=0, missing dict key
5. For Flask app use app.test_client()
6. Every test must have at least one assert
7. Return ONLY valid Python code inside ```python ... ``` block

CODE ({label}):
{source_code[:1500]}
"""
    raw   = llm.invoke(prompt)
    match = re.search(r"```(?:python)?\s*\n(.*?)```", raw, re.DOTALL)
    return match.group(1).strip() if match else raw.strip()


def generate_test_code(source_code: str, label: str, timeout: int = 60) -> str:
    result_box = [""]
    error_box  = [None]

    def _call():
        try:
            result_box[0] = generate_test_code_llm(source_code, label)
        except Exception as e:
            error_box[0] = e

    t = threading.Thread(target=_call, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive() or not result_box[0].strip():
        print(f"        ⚠️  LLM timeout hoặc trả về rỗng — dùng fallback test")
        return generate_fallback_test(source_code)

    if error_box[0]:
        print(f"        ⚠️  LLM lỗi: {error_box[0]} — dùng fallback test")
        return generate_fallback_test(source_code)

    return result_box[0]


def run_pytest(source_code: str, test_code: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        patched = re.sub(
            r"sqlite3\.connect\(['\"].*?\.db['\"]\)",
            "sqlite3.connect(':memory:')",
            source_code
        )
        with open(os.path.join(tmpdir, "module.py"),      "w", encoding="utf-8") as f:
            f.write(patched)
        with open(os.path.join(tmpdir, "test_module.py"), "w", encoding="utf-8") as f:
            f.write(test_code)

        result = subprocess.run(
            ["python", "-m", "pytest", "test_module.py",
             "-v", "--tb=short", "-q", "--no-header"],
            capture_output=True, text=True,
            timeout=30, cwd=tmpdir
        )

    output   = (result.stdout + result.stderr)[:2000]
    passed_n = int(m.group(1)) if (m := re.search(r"(\d+) passed", output)) else 0
    failed_n = int(m.group(1)) if (m := re.search(r"(\d+) failed", output)) else 0

    return {
        "passed":   result.returncode == 0,
        "n_passed": passed_n,
        "n_failed": failed_n,
        "output":   output,
    }


# ══════════════════════════════════════════════
# NODE CHÍNH
# ══════════════════════════════════════════════

def tester_node(state: AgentState) -> dict:
    log_step(state["iteration"], "TESTER", "Bắt đầu kiểm tra code 3 lớp...")

    all_issues:   list = []
    test_results: dict = {}

    # ── Động theo active_task_types (không hardcode UI+DB) ───
    active_types = state.get("active_task_types", ["UI", "DB"])
    targets = []
    for task_type in active_types:
        config     = TASK_TYPES.get(task_type, {})
        code_field = config.get("state_field", f"code_{task_type.lower()}")
        code       = state.get(code_field, "")
        targets.append((task_type, code))

    if not targets:
        log_step(state["iteration"], "TESTER", "⚠️ Không có module nào để test")
        return {
            "test_results": {},
            "test_issues":  ["Không có code để test"],
            "history": [{"iteration": state["iteration"], "node": "TESTER",
                         "content": {"issues_count": 0, "issues": []}}],
        }

    for label, code in targets:
        if not code.strip():
            print(f"  ⚠️  [{label}] rỗng — bỏ qua")
            continue

        print(f"\n  {'─'*40}")
        print(f"  🔍 [{label}]")
        result = {}

        # ── Lớp 1: Syntax ──────────────────────
        print("  [1/3] Syntax check...")
        syntax = check_syntax(code, label)
        result["syntax"] = syntax
        if not syntax["passed"]:
            all_issues.append(f"[{label}] SyntaxError: {syntax['error']}")
            print(f"        ❌ {syntax['error']}")
            test_results[label] = result
            continue
        print("        ✅ OK")

        # ── Lớp 2: Static + pylint ─────────────
        print("  [2/3] Static analysis...")
        static = check_static(code, label)    # ← truyền task_type
        pylint = check_pylint(code, label)
        result["static"] = static
        result["pylint"] = pylint

        for issue in static:
            all_issues.append(f"[{label}] {issue}")
            print(f"        {issue}")
        for issue in pylint:
            all_issues.append(f"[{label}] pylint: {issue}")
            print(f"        ⚠️  {issue}")
        if not static and not pylint:
            print("        ✅ OK")

        # ── Lớp 3: Pytest ──────────────────────
        print("  [3/3] Chạy pytest...")
        try:
            test_code     = generate_test_code(code, label, timeout=60)
            pytest_result = run_pytest(code, test_code)
            result["pytest"] = pytest_result

            if pytest_result["passed"]:
                print(f"        ✅ {pytest_result['n_passed']} tests passed")
            else:
                msg = (f"[{label}] pytest: {pytest_result['n_failed']} failed, "
                       f"{pytest_result['n_passed']} passed\n{pytest_result['output']}")
                all_issues.append(msg)
                print(f"        ❌ {pytest_result['n_failed']} failed")
                print(f"        {pytest_result['output'][:300]}")
        except subprocess.TimeoutExpired:
            all_issues.append(f"[{label}] pytest timeout > 30s")
            print("        ⚠️  pytest timeout")
        except Exception as e:
            all_issues.append(f"[{label}] pytest error: {e}")
            print(f"        ⚠️  {e}")

        test_results[label] = result

    # ── Tổng kết ───────────────────────────────
    print(f"\n  {'─'*40}")
    if all_issues:
        log_step(state["iteration"], "TESTER", f"❌ {len(all_issues)} vấn đề cần fix")
    else:
        log_step(state["iteration"], "TESTER", "✅ Tất cả passed!")

    # Tăng retry counter nếu có lỗi (dùng để giới hạn vòng tester→planner)
    tester_retry_count = state.get("tester_retry_count", 0)
    if all_issues:
        tester_retry_count += 1

    return {
        "test_results":       test_results,
        "test_issues":        all_issues,
        "tester_retry_count": tester_retry_count,
        # ← Chỉ entry MỚI
        "history": [{
            "iteration": state["iteration"],
            "node":      "TESTER",
            "content": {
                "issues_count": len(all_issues),
                "issues":       all_issues,
                "results": {
                    k: {
                        "syntax_ok": v.get("syntax", {}).get("passed", False),
                        "pytest_ok": v.get("pytest", {}).get("passed", False),
                    }
                    for k, v in test_results.items()
                }
            }
        }],
    }