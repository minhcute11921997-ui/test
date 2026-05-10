# nodes/tester.py
import os
import re
import subprocess
import tempfile
from langchain_ollama import OllamaLLM
from state import AgentState
from utils import log_step

llm = OllamaLLM(
    model="qwen2.5:14b",
    temperature=0.1,
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

STATIC_RULES = [
    (r"CREATE TABLE IF NOT EXISTS",          "Thiếu init_db() — không có CREATE TABLE"),
    (r"\.get\(['\"](?:name|price|stock|id)", "Dùng dict.get() thay vì dict['key'] — tránh KeyError"),
    (r"with sqlite3\.connect",               "Không dùng context manager (with) cho sqlite3"),
    (r"except",                              "Thiếu xử lý exception"),
]

def check_static(code: str) -> list:
    issues = []
    for pattern, message in STATIC_RULES:
        if not re.search(pattern, code):
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
    return lines[:5]  # giới hạn 5 dòng


# ══════════════════════════════════════════════
# LỚP 3 — PYTEST (LLM sinh test + chạy thật)
# ══════════════════════════════════════════════

def generate_test_code(source_code: str, label: str) -> str:
    prompt = f"""You are a Python test engineer. Write pytest test cases for the code below.

STRICT RULES:
1. Use sqlite3.connect(":memory:") for ALL database connections
2. Always run CREATE TABLE IF NOT EXISTS before any INSERT/SELECT
3. Test every function with happy path
4. Test edge cases: None input, price=0, stock=0, missing dict key
5. For Flask app use app.test_client()
6. Every test must have at least one assert
7. Return ONLY valid Python pytest code — no markdown, no explanation

CODE ({label}):
{source_code}
"""
    raw = llm.invoke(prompt)
    match = re.search(r"```(?:python)?\s*\n(.*?)```", raw, re.DOTALL)
    return match.group(1).strip() if match else raw.strip()


def run_pytest(source_code: str, test_code: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        # Patch db path → :memory: để không tạo file thật
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
            ["python", "-m", "pytest", "test_module.py", "-v", "--tb=short", "-q"],
            capture_output=True, text=True, timeout=30, cwd=tmpdir
        )

    output = (result.stdout + result.stderr)[:2000]
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

def tester_node(state: AgentState) -> AgentState:
    log_step(state["iteration"], "TESTER", "Bắt đầu kiểm tra code 3 lớp...")

    all_issues:   list = []
    test_results: dict = {}

    # ← Dùng đúng key từ state.py: code_ui, code_db
    targets = [
        ("UI", state.get("code_ui", "")),
        ("DB", state.get("code_db", "")),
    ]

    for label, code in targets:
        if not code.strip():
            continue

        print(f"\n  {'─'*40}")
        print(f"  🔍 [{label}]")
        result = {}

        # ── Lớp 1: Syntax ──────────────────────
        print("  [1/3] Syntax check...")
        syntax = check_syntax(code, label)
        result["syntax"] = syntax
        if not syntax["passed"]:
            err = f"[{label}] SyntaxError: {syntax['error']}"
            all_issues.append(err)
            print(f"        ❌ {syntax['error']}")
            test_results[label] = result
            continue  # lỗi syntax → bỏ qua lớp 2, 3
        print("        ✅ OK")

        # ── Lớp 2: Static + pylint ─────────────
        print("  [2/3] Static analysis...")
        static = check_static(code)
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
            test_code     = generate_test_code(code, label)
            pytest_result = run_pytest(code, test_code)
            result["pytest"] = pytest_result

            if pytest_result["passed"]:
                print(f"        ✅ {pytest_result['n_passed']} tests passed")
            else:
                msg = (f"[{label}] pytest: {pytest_result['n_failed']} failed, "
                       f"{pytest_result['n_passed']} passed\n{pytest_result['output']}")
                all_issues.append(msg)
                print(f"        ❌ {pytest_result['n_failed']} failed")
        except subprocess.TimeoutExpired:
            all_issues.append(f"[{label}] pytest timeout > 30s")
            print("        ⚠️  Timeout")
        except Exception as e:
            all_issues.append(f"[{label}] pytest error: {e}")
            print(f"        ⚠️  {e}")

        test_results[label] = result

    # ── Tổng kết ───────────────────────────────
    if all_issues:
        log_step(state["iteration"], "TESTER",
                 f"❌ {len(all_issues)} vấn đề cần fix")
    else:
        log_step(state["iteration"], "TESTER", "✅ Tất cả passed!")

    history = state.get("history", [])
    history.append({
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
    })

    return {
        "test_results": test_results,
        "test_issues":  all_issues,
        "history":      history,
    }