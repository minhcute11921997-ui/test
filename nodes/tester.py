# nodes/tester.py
import os
import re
import subprocess
import tempfile
from langchain_ollama import OllamaLLM
from state import AgentState, log_to_history
from utils import log_step

llm = OllamaLLM(
    model="qwen2.5:14b",
    temperature=0.1,
)


# ══════════════════════════════════════════════
# LỚP 1 — SYNTAX CHECK (py_compile)
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
    passed = result.returncode == 0
    error  = result.stderr.strip().replace(fname, f"{label}.py")
    return {"passed": passed, "error": error}


# ══════════════════════════════════════════════
# LỚP 2 — STATIC ANALYSIS (pylint/ruff)
# ══════════════════════════════════════════════

# Checklist cứng — không phụ thuộc LLM
STATIC_RULES = [
    (r"CREATE TABLE IF NOT EXISTS",           "Thiếu init_db() — không có CREATE TABLE"),
    (r"\.get\(['\"](?:name|price|stock|id)",  "Dùng dict['key'] thay vì dict.get() — dễ KeyError"),
    (r"\bis None\b|\bis not None\b",          "Thiếu kiểm tra None đúng cách (dùng is None thay vì falsy)"),
    (r"except\s+Exception\s+as",              "Thiếu xử lý exception"),
    (r"conn\.close\(\)",                      "Dùng conn.close() thủ công — nên dùng with statement"),
]

def check_static(code: str) -> list[str]:
    issues = []
    for pattern, message in STATIC_RULES:
        if not re.search(pattern, code):
            issues.append(f"⚠️  {message}")
    return issues


def check_pylint(code: str, label: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                     delete=False, encoding="utf-8") as f:
        f.write(code)
        fname = f.name
    result = subprocess.run(
        ["python", "-m", "pylint", fname,
         "--disable=C,R",          # bỏ convention/refactor, chỉ giữ warning/error
         "--score=no",
         "--output-format=text"],
        capture_output=True, text=True
    )
    os.unlink(fname)
    output = result.stdout.replace(fname, f"{label}.py")
    # Lọc chỉ lấy dòng W/E
    lines = [l for l in output.splitlines()
             if re.search(r"\s[WE]\d{4}:", l)]
    return {"issues": lines}


# ══════════════════════════════════════════════
# LỚP 3 — PYTEST (LLM sinh test + chạy thật)
# ══════════════════════════════════════════════

def generate_test_code(source_code: str, label: str) -> str:
    prompt = f"""You are a Python test engineer. Write pytest test cases for the following code.

RULES:
1. Use sqlite3.connect(":memory:") for all database operations — never use a real file
2. Always create the required tables before testing (CREATE TABLE IF NOT EXISTS)
3. Test happy path for every function
4. Test edge cases: None input, price=0, stock=0, empty string, missing dict keys
5. For Flask endpoints use app.test_client()
6. Each test must have at least one assert statement
7. Return ONLY pytest code, no explanation, no markdown

CODE ({label}):
{source_code}
"""
    raw = llm.invoke(prompt)

    # Bóc markdown nếu LLM trả về có ```python
    match = re.search(r"```(?:python)?\s*\n(.*?)```", raw, re.DOTALL)
    return match.group(1).strip() if match else raw.strip()


def run_pytest(source_code: str, test_code: str, label: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path  = os.path.join(tmpdir, "module.py")
        test_path = os.path.join(tmpdir, "test_module.py")

        # Patch sqlite3.connect trong source để dùng :memory:
        patched = source_code.replace(
            "sqlite3.connect('products.db')",
            "sqlite3.connect(':memory:')"
        ).replace(
            'sqlite3.connect("products.db")',
            'sqlite3.connect(":memory:")'
        )

        with open(src_path,  "w", encoding="utf-8") as f:
            f.write(patched)
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)

        result = subprocess.run(
            ["python", "-m", "pytest", test_path,
             "-v", "--tb=short", "--no-header", "-q"],
            capture_output=True, text=True,
            timeout=30, cwd=tmpdir
        )

    output = result.stdout + result.stderr
    passed = result.returncode == 0

    # Parse số test passed/failed
    summary_match = re.search(r"(\d+) passed", output)
    failed_match  = re.search(r"(\d+) failed", output)
    n_passed = int(summary_match.group(1)) if summary_match else 0
    n_failed = int(failed_match.group(1))  if failed_match  else 0

    return {
        "passed":   passed,
        "n_passed": n_passed,
        "n_failed": n_failed,
        "output":   output[:2000],  # giới hạn log
    }


# ══════════════════════════════════════════════
# NODE CHÍNH
# ══════════════════════════════════════════════

def tester_node(state: AgentState) -> AgentState:
    log_step(state["iteration"], "TESTER", "Bắt đầu kiểm tra code 3 lớp...")

    all_issues:  list[str] = []
    test_results: dict     = {}

    targets = [
        ("UI", state.get("ui_code", "")),
        ("DB", state.get("db_code", "")),
    ]

    for label, code in targets:
        if not code.strip():
            continue

        print(f"\n  {'─'*40}")
        print(f"  🔍 Kiểm tra [{label}]")
        result = {}

        # ── Lớp 1: Syntax ──────────────────────
        print(f"  [1/3] Syntax check...")
        syntax = check_syntax(code, label)
        result["syntax"] = syntax
        if not syntax["passed"]:
            all_issues.append(f"[{label}] SyntaxError: {syntax['error']}")
            print(f"       ❌ {syntax['error']}")
            test_results[label] = result
            continue  # syntax lỗi thì không cần check tiếp
        print(f"       ✅ OK")

        # ── Lớp 2: Static analysis ─────────────
        print(f"  [2/3] Static analysis...")
        static_issues = check_static(code)
        pylint_result = check_pylint(code, label)
        result["static"] = static_issues
        result["pylint"] = pylint_result["issues"]

        for issue in static_issues:
            all_issues.append(f"[{label}] {issue}")
            print(f"       {issue}")
        for issue in pylint_result["issues"][:5]:  # giới hạn 5 dòng pylint
            all_issues.append(f"[{label}] pylint: {issue.strip()}")
            print(f"       ⚠️  {issue.strip()}")
        if not static_issues and not pylint_result["issues"]:
            print(f"       ✅ OK")

        # ── Lớp 3: Pytest ──────────────────────
        print(f"  [3/3] Sinh và chạy pytest...")
        try:
            test_code = generate_test_code(code, label)
            pytest_result = run_pytest(code, test_code, label)
            result["pytest"] = pytest_result

            if pytest_result["passed"]:
                print(f"       ✅ {pytest_result['n_passed']} tests passed")
            else:
                msg = (f"[{label}] pytest: "
                       f"{pytest_result['n_failed']} failed / "
                       f"{pytest_result['n_passed']} passed\n"
                       f"{pytest_result['output']}")
                all_issues.append(msg)
                print(f"       ❌ {pytest_result['n_failed']} failed")
                print(f"       {pytest_result['output'][:300]}")
        except subprocess.TimeoutExpired:
            all_issues.append(f"[{label}] pytest timeout > 30s")
            print(f"       ⚠️  Timeout")
        except Exception as e:
            all_issues.append(f"[{label}] pytest error: {str(e)}")
            print(f"       ⚠️  {e}")

        test_results[label] = result

    # ── Tổng kết ───────────────────────────────
    print(f"\n  {'─'*40}")
    if all_issues:
        log_step(state["iteration"], "TESTER",
                 f"❌ Phát hiện {len(all_issues)} vấn đề cần fix")
    else:
        log_step(state["iteration"], "TESTER", "✅ Tất cả kiểm tra passed!")

    history = state.get("history", [])
    history.append({
        "iteration": state["iteration"],
        "node":      "TESTER",
        "content": {
            "issues_count": len(all_issues),
            "issues":       all_issues,
            "results":      {k: {
                "syntax_ok": v.get("syntax", {}).get("passed", False),
                "pytest_ok": v.get("pytest", {}).get("passed", False),
            } for k, v in test_results.items()}
        }
    })

    return {
        "test_results": test_results,
        "test_issues":  all_issues,
        "history":      history,
    }