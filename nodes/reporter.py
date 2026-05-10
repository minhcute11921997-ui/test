# nodes/reporter.py
import os
from datetime import datetime
from langchain_ollama import OllamaLLM
from state import AgentState, log_to_history
from utils import log_step
from memory.memory_manager import save_template, save_patterns

llm = OllamaLLM(
    model="qwen2.5:14b",
    temperature=0.2,
)


# ── Các hàm tạo từng phần báo cáo ────────────────────────────

def _summary_section(state: AgentState) -> str:
    """LLM tóm tắt những gì đã làm được"""
    prompt = f"""
You are a technical writer. Write a concise project summary in Vietnamese.

USER REQUEST: {state['user_request']}
TOTAL ITERATIONS: {state['iteration']}
FINAL STATUS: {state['status']}
ORIGINAL PLAN: {state['original_plan']}
FINAL PLAN: {state['current_plan']}

Write 3-5 sentences summarizing:
- What was requested
- What was built
- How many iterations it took and why
Return plain text only, no JSON, no markdown headers.
"""
    return llm.invoke(prompt)


def _iteration_table(state: AgentState) -> str:
    """Tạo bảng tóm tắt từng vòng lặp từ history"""
    rows = []
    rows.append("| Vòng | Node | Nội dung |")
    rows.append("|------|------|----------|")

    for entry in state["history"]:
        iteration = entry.get("iteration", "?")
        node      = entry.get("node", "?")
        content   = str(entry.get("content", ""))[:80].replace("\n", " ")
        rows.append(f"| {iteration} | {node} | {content} |")

    return "\n".join(rows)


def _quality_table(state: AgentState) -> str:
    """Bảng điểm chất lượng từng vòng"""
    # Lấy tất cả feedback từ history
    rows = []
    rows.append("| Vòng | Module | Syntax | Pylint | LLM | Score | Status |")
    rows.append("|------|--------|--------|--------|-----|-------|--------|")

    for entry in state["history"]:
        if entry.get("node") == "REVIEWER":
            content = entry.get("content", {})
            if isinstance(content, dict):
                iteration = entry.get("iteration", "?")
                for task_type, fb in [("UI", content.get("feedback_ui", {})),
                                       ("DB", content.get("feedback_db", {}))]:
                    if fb:
                        syntax  = "✅" if fb.get("passed_syntax") else "❌"
                        pylint  = "✅" if fb.get("passed_pylint") else "❌"
                        llm_r   = "✅" if fb.get("llm_review") == "ok" else "❌"
                        score   = fb.get("quality_score", "?")
                        status  = fb.get("status", "?")
                        rows.append(f"| {iteration} | {task_type} | {syntax} | {pylint} | {llm_r} | {score}/10 | {status} |")

    return "\n".join(rows)




def _issues_section(state: AgentState) -> str:
    """Liệt kê tất cả lỗi đã gặp và cách fix"""
    sections = []

    for entry in state["history"]:
        if entry.get("node") == "REVIEWER":
            content = entry.get("content", {})
            if isinstance(content, dict):
                iteration = entry.get("iteration", "?")
                for task_type, fb in [("UI", content.get("feedback_ui", {})),
                                       ("DB", content.get("feedback_db", {}))]:
                    if fb and fb.get("issues"):
                        sections.append(f"\n**Vòng {iteration} — {task_type}:**")
                        for issue in fb["issues"]:
                            sections.append(f"- ❌ {issue}")
                        for suggestion in fb.get("suggestions", []):
                            sections.append(f"  → 💡 {suggestion}")

    return "\n".join(sections) if sections else "_Không có lỗi nào được ghi nhận._"


def _code_section(state: AgentState) -> str:
    """Hiển thị code cuối cùng"""
    iteration = state["iteration"]
    ui_file   = f"output/iteration_{iteration}/ui_code.py"
    db_file   = f"output/iteration_{iteration}/db_code.py"

    sections = []

    for label, filepath in [("UI", ui_file), ("DB", db_file)]:
        sections.append(f"\n### {label} Code\n")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                code = f.read()
            sections.append(f"```python\n{code}\n```")
        else:
            sections.append("_File không tìm thấy._")

    return "\n".join(sections)


def _context_section(state: AgentState) -> str:
    """Thông tin context dự án nếu có"""
    if not state.get("context_summary"):
        return "_Không có context dự án._"
    return state["context_summary"]


# ── Node chính ────────────────────────────────────────────────

def reporter_node(state: AgentState) -> AgentState:
    log_step(state["iteration"], "REPORTER", "Đang tạo báo cáo tự động...")

    timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_file  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_folder = f"output/iteration_{state['iteration']}"
    os.makedirs(out_folder, exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    # ── Tạo từng phần ──
    print("  📝 Đang tóm tắt kết quả...")
    summary = _summary_section(state)

    print("  📊 Đang tạo bảng vòng lặp...")
    iter_table = _iteration_table(state)

    print("  🔍 Đang tổng hợp chất lượng code...")
    quality = _quality_table(state)

    print("  ⚠️  Đang liệt kê lỗi và cách fix...")
    issues = _issues_section(state)

    print("  💻 Đang ghi code cuối cùng...")
    code = _code_section(state)

    context = _context_section(state)

    # ── Ghép thành file .md ──
    report = f"""# 📋 BÁO CÁO PIPELINE — {timestamp}

---

## 1. Tổng quan

**Yêu cầu:** {state['user_request']}
**Tổng vòng lặp:** {state['iteration']}
**Trạng thái cuối:** {state['status']}
**Thời gian:** {timestamp}

### Tóm tắt
{summary}

---

## 2. Context Dự Án

{context}

---

## 3. Lịch sử thực thi

{iter_table}

---

## 4. Chất lượng Code theo Vòng

{quality}

---

## 5. Lỗi đã gặp & Cách xử lý

{issues}

---

## 6. Code Cuối Cùng

{code}

---

## 7. File Output

| File | Đường dẫn |
|------|-----------|
| Báo cáo này | `reports/report_{date_file}.md` |
| Code tích hợp | `{out_folder}/integrated.py` |
| Log JSON | `logs/run_*.json` |

---
_Báo cáo được tạo tự động bởi Multi-Agent Pipeline_
"""

    # ── Lưu file ──
    report_path = f"reports/report_{date_file}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    log_step(state["iteration"], "REPORTER", f"✅ Báo cáo đã lưu: {report_path}")

     # ── Lưu memory nếu pipeline thành công ──────────────────
    if state["status"] == "done":
        print("\n  🧠 Lưu memory...")
        save_template(
            request = state["user_request"],
            plan    = state["current_plan"],
        )
        save_patterns(
            history = state["history"],   # ← toàn bộ history các vòng
        )
        print("  ✅ Memory đã cập nhật")
    # ────────────────────────────────────────────────────────
    history = state.get("history", [])
    history.append({"iteration": state["iteration"], "node": "REPORTER", "content": report_path})

    # ← Chỉ trả về field thay đổi
    return {
    "history": history
}