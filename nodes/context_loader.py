# nodes/context_loader.py
import os
from pathlib import Path
from langchain_ollama import OllamaLLM
from state import AgentState
from utils import log_step
import sqlite3

llm = OllamaLLM(
    model="qwen3.5:9b",
    temperature=0.1,
)

TEXT_EXTENSIONS  = {".txt", ".md", ".rst"}
CODE_EXTENSIONS  = {".py", ".js", ".ts", ".html", ".css", ".json"}
IGNORE_FOLDERS   = {"venv", "__pycache__", ".git", "node_modules", "output", "logs", "reports"}


def _read_text_files(folder: str) -> str:
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
    code_files = {}
    for path in Path(folder).rglob("*"):
        if any(ig in path.parts for ig in IGNORE_FOLDERS):
            continue
        if path.suffix in CODE_EXTENSIONS and path.is_file():
            try:
                code = path.read_text(encoding="utf-8")
                code_files[path.name] = code[:2000]
                print(f"  💻 Đọc code: {path.name}")
            except Exception as e:
                print(f"  ⚠️ Không đọc được {path.name}: {e}")
    return code_files


def _read_db_file(db_path: str) -> dict:
    result = {
        "tables":  [],
        "schemas": {},
        "samples": {},
    }

    try:
        conn   = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        result["tables"] = tables
        print(f"  🗄️  Tìm thấy {len(tables)} bảng: {tables}")

        for table in tables:
            cursor.execute(f"PRAGMA table_info({table});")
            columns = cursor.fetchall()
            result["schemas"][table] = [
                {
                    "column":      col[1],
                    "type":        col[2],
                    "not_null":    bool(col[3]),
                    "primary_key": bool(col[5]),
                }
                for col in columns
            ]
            print(f"  📋 Schema [{table}]: {[c['column'] for c in result['schemas'][table]]}")

            try:
                cursor.execute(f"SELECT * FROM {table} LIMIT 3;")
                rows      = cursor.fetchall()
                col_names = [col[1] for col in columns]
                result["samples"][table] = [dict(zip(col_names, row)) for row in rows]
            except Exception:
                result["samples"][table] = []

        conn.close()

    except sqlite3.DatabaseError as e:
        print(f"  ❌ Lỗi đọc .db: {e}")

    return result


def _format_db_for_prompt(db_info: dict) -> str:
    if not db_info.get("tables"):
        return ""

    lines = ["DATABASE STRUCTURE:"]
    for table in db_info["tables"]:
        lines.append(f"\nTable: {table}")
        for col in db_info["schemas"].get(table, []):
            pk = " [PRIMARY KEY]" if col["primary_key"] else ""
            nn = " NOT NULL"      if col["not_null"]    else ""
            lines.append(f"  - {col['column']} {col['type']}{pk}{nn}")

        samples = db_info["samples"].get(table, [])
        if samples:
            lines.append(f"  Sample data ({len(samples)} rows):")
            for row in samples:
                lines.append(f"    {row}")

    return "\n".join(lines)


def _summarize_context(spec: str, code_files: dict, db_context: str, user_request: str) -> str:
    """
    Dùng LLM tóm tắt context.
    Guard: chỉ gọi khi thực sự có nội dung để tóm tắt.
    """
    has_content = bool(spec.strip() or code_files or db_context.strip())
    if not has_content:
        return ""   # ← tránh gọi LLM với prompt rỗng

    code_summary = "\n".join([
        f"- {fname}: {code[:200]}..."
        for fname, code in code_files.items()
    ])

    prompt = f"""
Summarize this project context in 5-10 bullet points.
Focus on: existing features, tech stack, coding patterns, constraints.

USER REQUEST: {user_request}

SPEC FILES:
{spec[:1500] if spec else "(none)"}

EXISTING CODE FILES:
{code_summary[:1500] if code_summary else "(none)"}

DATABASE CONTEXT:
{db_context[:1500] if db_context else "(none)"}

Return plain text bullet points, no JSON needed.
"""
    return llm.invoke(prompt)


def context_loader_node(state: AgentState) -> dict:
    log_step(0, "CONTEXT LOADER", "Đang đọc dữ liệu dự án...")

    # ── Đọc folder project ────────────────────────────────────
    print("\n📁 Nhập đường dẫn thư mục dự án (Enter để bỏ qua):")
    folder = input("  Đường dẫn folder: ").strip()

    spec       = ""
    code_files = {}

    if folder and os.path.exists(folder):
        print("\n🔍 Đang đọc file spec (.txt/.md)...")
        spec = _read_text_files(folder)

        print("\n🔍 Đang đọc file code (.py/.js)...")
        code_files = _read_code_files(folder)
    elif folder:
        print(f"  ❌ Không tìm thấy folder: {folder}")
    else:
        print("  ⏭️  Bỏ qua folder")

    # ── Đọc file .db ──────────────────────────────────────────
    print("\n🗄️  Nhập đường dẫn file .db (Enter để bỏ qua):")
    db_path = input("  Đường dẫn .db: ").strip().replace("\\", "/")

    db_info    = {}
    db_context = ""

    if db_path and os.path.exists(db_path):
        print("\n🔍 Đang đọc cấu trúc database...")
        db_info    = _read_db_file(db_path)
        db_context = _format_db_for_prompt(db_info)
        print(f"  ✅ Đọc xong: {len(db_info.get('tables', []))} bảng")
    elif db_path:
        print(f"  ❌ Không tìm thấy file: {db_path}")

    # ── Kiểm tra có gì không ──────────────────────────────────
    if not spec and not code_files and not db_context:
        log_step(0, "CONTEXT LOADER", "⏭️  Không có context — chạy từ đầu")
        return {}

    # ── LLM tóm tắt — chỉ khi có nội dung thực sự ───────────
    print("\n🧠 LLM đang phân tích context...")
    summary = _summarize_context(
        spec         = spec,
        code_files   = code_files,
        db_context   = db_context,
        user_request = state["user_request"],
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
        "db_tables":       db_info.get("tables",  []),
        "db_schemas":      db_info.get("schemas", {}),
        "history": [{
            "iteration": 0,
            "node":      "CONTEXT LOADER",
            "content":   {"summary": summary},
        }],
    }