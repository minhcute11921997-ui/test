import subprocess, os, tempfile, textwrap
from state import AgentState, log_to_history
from utils import log_step

BASIC_CHECKS = textwrap.dedent("""
import sqlite3, pytest

# Auto-generated basic tests
def test_init_db_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import importlib, sys
    # Kiểm tra có hàm init_db không
    assert hasattr(module_under_test, 'init_db'), "Missing init_db()"

def test_no_key_error_on_missing_field():
    # Simulate thiếu field
    pass
""")

def run_syntax_check(code: str) -> dict:
    """Chạy py_compile để check syntax"""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        fname = f.name
    result = subprocess.run(
        ["python", "-m", "py_compile", fname],
        capture_output=True, text=True
    )
    os.unlink(fname)
    return {
        "passed": result.returncode == 0,
        "error": result.stderr.strip()
    }

def run_runtime_check(code: str) -> dict:
    """Thực thi code trong sandbox, bắt ImportError, NameError..."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        # Inject init + basic call để test runtime
        f.write(code + "\n\n# Auto test\nif hasattr(globals().get('create_product', None), '__call__'): pass\n")
        fname = f.name
    result = subprocess.run(
        ["python", fname],
        capture_output=True, text=True, timeout=10
    )
    os.unlink(fname)
    return {
        "passed": result.returncode == 0,
        "error": result.stderr.strip()
    }

def tester_node(state: AgentState) -> AgentState:
    log_step(state["iteration"], "TESTER", "Đang chạy kiểm tra code...")
    iteration = state["iteration"]

    test_results = {}
    issues_found = []

    for label, code_key in [("UI", "ui_code"), ("DB", "db_code")]:
        code = state.get(code_key, "")
        if not code:
            continue

        syntax = run_syntax_check(code)
        runtime = run_runtime_check(code)

        test_results[label] = {
            "syntax": syntax,
            "runtime": runtime,
        }

        if not syntax["passed"]:
            issues_found.append(f"{label} SyntaxError: {syntax['error']}")
        if not runtime["passed"]:
            issues_found.append(f"{label} RuntimeError: {runtime['error']}")

    # Nếu có lỗi → đưa feedback vào state để coder fix ngay
    if issues_found:
        log_step(iteration, "TESTER", f"❌ Phát hiện {len(issues_found)} lỗi:\n" + "\n".join(issues_found))
        return {
            "test_results": test_results,
            "test_issues": issues_found,
            "status": "fixing",   # → buộc pipeline lặp lại
        }

    log_step(iteration, "TESTER", "✅ Tất cả kiểm tra passed!")
    return {
        "test_results": test_results,
        "test_issues": [],
    }