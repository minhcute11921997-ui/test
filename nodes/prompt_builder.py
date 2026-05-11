# nodes/prompt_builder.py

TASK_SKELETONS = {
    "DB": """
STRUCTURE TO FOLLOW (fill in the logic, adapt class/function names to the domain):
```python
import sqlite3  # hoặc sqlalchemy, pymongo, etc. tuỳ task

class {ModelName}DB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.create_table()

    def _execute(self, query: str, params: tuple = (), fetch=False):
        # shared execute với error handling
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(query, params)
            conn.commit()
            return cur.fetchall() if fetch else cur.lastrowid
        except sqlite3.Error as e:
            conn.rollback()
            raise RuntimeError(f"DB error: {e}") from e
        finally:
            conn.close()

    def create_table(self): ...          # CREATE TABLE IF NOT EXISTS
    def insert(self, data: dict): ...    # validate rồi INSERT
    def get_by_id(self, id: int): ...    # SELECT + trả None nếu không tìm thấy
    def get_all(self, filters=None): ... # SELECT với optional WHERE
    def update(self, id: int, data: dict): ...  # UPDATE + check tồn tại
    def delete(self, id: int): ...       # DELETE + check tồn tại
```""",

    "API": """
STRUCTURE TO FOLLOW (adapt framework and routes to the domain):
```python
from flask import Flask, request, jsonify  # hoặc fastapi, etc.

app = Flask(__name__)

# Helper responses — dùng nhất quán trong toàn file
def _ok(data, code=200):   return jsonify({"data": data, "error": None}), code
def _err(msg, code=400):   return jsonify({"data": None, "error": msg}), code

# Pattern cho mỗi resource:
# GET    /resource        → list tất cả (có filter query params)
# GET    /resource/<id>   → get 1 item, trả 404 nếu không có
# POST   /resource        → validate body rồi create
# PUT    /resource/<id>   → validate body rồi update, trả 404 nếu không có
# DELETE /resource/<id>   → delete, trả 404 nếu không có

@app.errorhandler(404)
def not_found(e): return _err("Not found", 404)

@app.errorhandler(500)
def server_error(e): return _err("Internal server error", 500)
```""",

    "AUTH": """
STRUCTURE TO FOLLOW:
```python
import hashlib, secrets, hmac

# Các hàm BẮT BUỘC phải có:
def hash_password(plain: str) -> str:
    # dùng hashlib.pbkdf2_hmac hoặc bcrypt
    ...

def verify_password(plain: str, hashed: str) -> bool:
    # so sánh an toàn, không dùng == trực tiếp
    ...

def generate_token(user_id: int, secret: str) -> str:
    # JWT hoặc signed token
    ...

def verify_token(token: str, secret: str) -> dict | None:
    # trả dict {user_id, ...} hoặc None nếu invalid/expired
    ...

def register(username: str, password: str, **kwargs) -> dict | None:
    # validate → hash password → insert DB → trả user dict
    ...

def login(username: str, password: str) -> dict | None:
    # lookup → verify_password → generate_token → trả {token, user}
    ...
```""",

    "TEST": """
STRUCTURE TO FOLLOW:
```python
import pytest
import sqlite3

# ── Fixtures ──────────────────────────────────────────────────
@pytest.fixture
def db():
    # LUÔN dùng :memory: — không tạo file .db thật
    conn = sqlite3.connect(":memory:")
    # setup schema ở đây
    yield conn
    conn.close()

@pytest.fixture
def client():
    # Flask test client
    from app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

# ── Happy path ─────────────────────────────────────────────────
def test_{feature}_success(db): ...
def test_{feature}_returns_correct_data(db): ...

# ── Edge cases ─────────────────────────────────────────────────
def test_{feature}_empty_input(): ...
def test_{feature}_invalid_type(): ...
def test_{feature}_not_found(): ...
def test_{feature}_duplicate(): ...

# ── Integration ────────────────────────────────────────────────
def test_{feature}_end_to_end(client): ...
```""",

    "UI": """
STRUCTURE TO FOLLOW (adapt to project type: CLI / web template / desktop / game):
```python
# Các entry point BẮT BUỘC phải có:

def show_{screen}():
    # render/display màn hình hoặc output
    ...

def handle_{action}(input_data):
    # xử lý input từ user, gọi API/service layer
    # KHÔNG xử lý business logic ở đây — chỉ delegate
    ...

def validate_{form}(data: dict) -> tuple[bool, str]:
    # trả (True, "") nếu hợp lệ
    # trả (False, "error message") nếu không
    ...

def format_{data}(raw) -> str:
    # format data để hiển thị
    ...

def main():
    # entry point chính
    ...
```""",
}


def _build_spec_block(task: dict) -> str:
    """Sinh spec block từ các field planner đã thêm."""
    parts = []

    required_functions = task.get("required_functions", [])
    required_endpoints = task.get("required_endpoints", [])
    acceptance_criteria = task.get("acceptance_criteria", [])
    edge_cases = task.get("edge_cases", [])
    data_contract = task.get("data_contract", {})

    if required_functions:
        parts.append("REQUIRED FUNCTIONS (implement ALL — exact names matter):")
        parts.extend(f"  - {f}" for f in required_functions)

    if required_endpoints:
        parts.append("\nREQUIRED ENDPOINTS (implement ALL):")
        parts.extend(f"  - {e}" for e in required_endpoints)

    if data_contract:
        parts.append("\nDATA CONTRACT (input/output shapes):")
        for name, shape in data_contract.items():
            parts.append(f"  - {name}: {shape}")

    if acceptance_criteria:
        parts.append("\nACCEPTANCE CRITERIA (code MUST satisfy all):")
        parts.extend(f"  - {c}" for c in acceptance_criteria)

    if edge_cases:
        parts.append("\nEDGE CASES (must handle these):")
        parts.extend(f"  - {e}" for e in edge_cases)

    return "\n".join(parts)


def _build_contract_block(module_contracts: dict, task_type: str) -> str:
    """Sinh contract block — module này phải implement/gọi gì."""
    if not module_contracts:
        return ""

    contract = module_contracts.get(task_type, {})
    if not contract:
        return ""

    lines = ["MODULE CONTRACT (your code must respect these interfaces):"]

    if contract.get("exposes"):
        lines.append("  This module EXPOSES (must implement):")
        lines.extend(f"    - {x}" for x in contract["exposes"])

    if contract.get("calls"):
        lines.append("  This module CALLS (assume these exist in other modules):")
        lines.extend(f"    - {x}" for x in contract["calls"])

    if contract.get("owns_tables"):
        lines.append("  This module OWNS these DB tables:")
        lines.extend(f"    - {t}" for t in contract["owns_tables"])

    return "\n".join(lines)


def build_coder_prompt(
    task: dict,
    task_type: str,
    mode: str,                      # "new" | "fix" | "improve"
    prev_code: str = "",
    error_detail: str = "",
    fix_instruction: str = "",
    cross_context: str = "",
    relevant_code: str = "",
    context_summary: str = "",
    timeout_issues: list = None,
    module_contracts: dict = None,
) -> str:
    timeout_issues   = timeout_issues or []
    module_contracts = module_contracts or {}

    # ── Rules luôn có ──────────────────────────────────────────
    rules = """RULES:
- Write COMPLETE, FULLY FUNCTIONAL code — no stubs, no "# TODO", no bare "pass".
- Include ALL imports, ALL function bodies, ALL error handling.
- If multiple files needed, use:
    ### filename.ext
    ```python
    ...code...
    ```
- No explanation text."""

    # ── Base ───────────────────────────────────────────────────
    base = f"""You are an expert Python developer.
Task   : {task.get('name', task_type)}
Type   : {task_type}
Goal   : {task.get('description', f'Build {task_type} module')}"""

    # ── Spec block (planner fields) ────────────────────────────
    spec_block = _build_spec_block(task)

    # ── Contract block ─────────────────────────────────────────
    contract_block = _build_contract_block(module_contracts, task_type)

    # ── Context & cross-module (chỉ mode new) ──────────────────
    context_block = ""
    if context_summary:
        context_block = f"PROJECT CONTEXT:\n{context_summary[:500]}"

    existing_block = ""
    if relevant_code:
        existing_block = f"EXISTING CODE TO EXTEND:\n{relevant_code}"

    cross_block = ""
    if cross_context:
        cross_block = f"RELATED MODULES (integrate with these):\n{cross_context}"

    # ── Skeleton (chỉ mode new, chèn trước instruction) ────────
    skeleton_block = ""
    if mode == "new":
        skeleton = TASK_SKELETONS.get(task_type, "")
        if skeleton:
            skeleton_block = (
                skeleton.strip()
                + "\n\nAdapt this structure to the task. "
                  "Add/remove methods as needed. "
                  "Replace placeholder names with domain-specific names."
            )

    # ── Mode-specific block ────────────────────────────────────
    if mode == "new":
        action_block = (
            "Extend the existing code above."
            if relevant_code
            else "Write clean, complete Python code following the structure above."
        )
        action_block += "\nAlso create a requirements.txt listing all pip packages used."
        action_block += "\nReturn each file separately using the ### filename format."

    elif mode == "fix":
        action_block = f"""PREVIOUS CODE WITH ISSUES:
{prev_code}

ERRORS TO FIX (fix ALL — do not skip any):
{error_detail}"""
        if fix_instruction:
            action_block += f"\n\nADDITIONAL FIX INSTRUCTION:\n{fix_instruction}"
        action_block += "\n\nReturn ONLY the corrected Python code."

    elif mode == "improve":
        perf_note = ""
        if timeout_issues:
            perf_note = (
                "\n\nPERFORMANCE ISSUES (tests timed out > 30s):\n"
                + "\n".join(f"  - {i}" for i in timeout_issues)
                + "\nOptimize: reduce O(n²) loops, use generators, add early returns."
            )
        action_block = f"""CURRENT CODE:
{prev_code}

IMPROVEMENT NEEDED:
{fix_instruction}{perf_note}

Return ONLY the improved Python code."""

    else:
        action_block = ""

    # ── Ghép theo thứ tự: rules → base → spec → contract → context → skeleton → action
    sections = [
        rules,
        base,
        spec_block,
        contract_block,
        context_block,
        existing_block,
        cross_block,
        skeleton_block,
        action_block,
    ]
    return "\n\n".join(s.strip() for s in sections if s.strip())