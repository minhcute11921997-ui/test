# nodes/context_loader.py
import os
from pathlib import Path
from langchain_ollama import OllamaLLM
from state import AgentState, log_to_history
from utils import log_step, parse_json_safe
import sqlite3

llm = OllamaLLM(
    model="qwen2.5:14b",
    temperature=0.1,
)

# Extensions được phép đọc
TEXT_EXTENSIONS  = {".txt", ".md", ".rst"}
CODE_EXTENSIONS  = {".py", ".js", ".ts", ".html", ".css", ".json"}
IGNORE_FOLDERS   = {"venv", "__pycache__", ".git", "node_modules"}


def _read_text_files(folder: str) -> str:
    """Đọc tất cả file .txt/.md trong folder"""
    content = ""
    for path in Path(folder).rglob("*"):
        if path.suffix in TEXT_EXTENSIONS and path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
                content += f"\n\n### FILE: {path.name} ###\n{text}"
                print(f"  📄 Đọc spec: {path.name}")
            except Exception as e:
                print(f"  ⚠️ Không đọc được {path.name}: {e}")
    return content


def _read_code_files(folder: str) -> dict:
    """Đọc tất cả file code trong folder"""
    code_files = {}
    for path in Path(folder).rglob("*"):
        # Bỏ qua các folder không cần thiết
        if any(ig in path.parts for ig in IGNORE_FOLDERS):
            continue
        if path.suffix in CODE_EXTENSIONS and path.is_file():
            try:
                code = path.read_text(encoding="utf-8")
                code_files[path.name] = code[:2000]  # Giới hạn 2000 ký tự/file
                print(f"  💻 Đọc code: {path.name}")
            except Exception as e:
                print(f"  ⚠️ Không đọc được {path.name}: {e}")
    return code_files

def _read_db_file(db_path: str) -> dict:
    """
    Đọc file .db và trích xuất:
    - Danh sách bảng
    - Schema từng bảng (tên cột, kiểu dữ liệu)
    - 3 dòng dữ liệu mẫu mỗi bảng
    """
    result = {
        "tables": [],
        "schemas": {},
        "samples": {},
        "summary": ""
    }

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Lấy danh sách bảng
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        result["tables"] = tables
        print(f"  🗄️  Tìm thấy {len(tables)} bảng: {tables}")

        for table in tables:
            # Schema từng bảng
            cursor.execute(f"PRAGMA table_info({table});")
            columns = cursor.fetchall()
            schema = [
                {
                    "column": col[1],
                    "type":   col[2],
                    "not_null": bool(col[3]),
                    "primary_key": bool(col[5])
                }
                for col in columns
            ]
            result["schemas"][table] = schema
            print(f"  📋 Schema [{table}]: {[c['column'] for c in schema]}")

            # Dữ liệu mẫu
            try:
                cursor.execute(f"SELECT * FROM {table} LIMIT 3;")
                rows = cursor.fetchall()
                col_names = [col[1] for col in columns]
                result["samples"][table] = [
                    dict(zip(col_names, row)) for row in rows
                ]
            except Exception:
                result["samples"][table] = []

        conn.close()

    except sqlite3.DatabaseError as e:
        print(f"  ❌ Lỗi đọc .db: {e}")
        result["summary"] = f"Lỗi: {e}"
        return result

    return result


def _format_db_for_prompt(db_info: dict) -> str:
    """Chuyển thông tin DB thành text dễ đọc cho LLM"""
    if not db_info["tables"]:
        return ""

    lines = ["DATABASE STRUCTURE:"]

    for table in db_info["tables"]:
        lines.append(f"\nTable: {table}")

        # Schema
        schema = db_info["schemas"].get(table, [])
        for col in schema:
            pk  = " [PRIMARY KEY]" if col["primary_key"] else ""
            nn  = " NOT NULL"      if col["not_null"]    else ""
            lines.append(f"  - {col['column']} {col['type']}{pk}{nn}")

        # Sample data
        samples = db_info["samples"].get(table, [])
        if samples:
            lines.append(f"  Sample data ({len(samples)} rows):")
            for row in samples:
                lines.append(f"    {row}")

    return "\n".join(lines)


def _summarize_context(spec: str, code_files: dict, db_context: str, user_request: str) -> str:
    """Dùng LLM tóm tắt context thành ghi chú ngắn cho các node sau"""
    code_summary = "\n".join([
        f"- {fname}: {code[:200]}..."
        for fname, code in code_files.items()
    ])

    prompt = f"""
Summarize this project context in 5-10 bullet points.
Focus on: existing features, tech stack, coding patterns, constraints.

USER REQUEST: {user_request}

SPEC FILES:
{spec[:1500]}

EXISTING CODE FILES:
{code_summary[:1500]}

DATABASE CONTEXT:
{db_context[:1500]}

Return plain text bullet points, no JSON needed.
"""
    return llm.invoke(prompt)


def context_loader_node(state: AgentState) -> AgentState:
    log_step(0, "CONTEXT LOADER", "Đang đọc dữ liệu dự án...")

    # ── Đọc folder project (code + spec) ──
    print("\n📁 Nhập đường dẫn thư mục dự án (Enter để bỏ qua):")
    folder = input("  Đường dẫn folder: ").strip()

    spec       = ""
    code_files = {}

    if folder and os.path.exists(folder):
        print("\n🔍 Đang đọc file spec (.txt/.md)...")
        spec = _read_text_files(folder)

        print("\n🔍 Đang đọc file code (.py/.js)...")
        code_files = _read_code_files(folder)
    else:
        print("  ⏭️  Bỏ qua folder")

    # ── Đọc file .db ──────────────────────────────────────────
    print("\n🗄️  Nhập đường dẫn file .db (Enter để bỏ qua):")
    db_path = input("  Đường dẫn .db: ").strip()
    db_path = db_path.replace("\\", "/") 
    db_info    = {}
    db_context = ""

    if db_path and os.path.exists(db_path):
        print("\n🔍 Đang đọc cấu trúc database...")
        db_info    = _read_db_file(db_path)
        db_context = _format_db_for_prompt(db_info)
        print(f"  ✅ Đọc xong: {len(db_info['tables'])} bảng")
    elif db_path:
        print(f"  ❌ Không tìm thấy file: {db_path}")

    # ── Kiểm tra có gì không ──
    if not spec and not code_files and not db_context:
        log_step(0, "CONTEXT LOADER", "⏭️  Không có context — chạy từ đầu")
        return {}

    # ── LLM tóm tắt toàn bộ context ──
    print("\n🧠 LLM đang phân tích context...")
    summary = _summarize_context(
        spec       = spec,
        code_files = code_files,
        db_context = db_context,          # ← thêm
        user_request = state["user_request"]
    )

    log_step(0, "CONTEXT LOADER",
             f"✅ Đọc xong\n"
             f"   Spec files : {len(spec)} ký tự\n"
             f"   Code files : {len(code_files)} file\n"
             f"   DB tables  : {db_info.get('tables', [])}\n\n"
             f"Tóm tắt:\n{summary}")

    return {
        "project_spec":    spec,
        "existing_code":   code_files,
        "context_summary": summary,
        "db_tables":       db_info.get("tables", []),
        "db_schemas":      db_info.get("schemas", {}),
        "history": [{
            "iteration": 0,
            "node": "CONTEXT LOADER",
            "content": {"summary": summary}
        }],
    }