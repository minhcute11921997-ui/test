# nodes/reporter.py
import os
from datetime import datetime
from langchain_ollama import OllamaLLM
from state import AgentState
from utils import log_step
from memory.memory_manager import save_template, save_patterns
from nodes.task_config import TASK_TYPES

llm = OllamaLLM(
    model="qwen2.5:14b",
    temperature=0.2,
)


def _summary_section(state: AgentState) -> str:
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
    rows = [
        "| Vòng | Node | Nội dung |",
        "|------|------|----------|",
    ]
    for entry in state["history"]:
        iteration = entry.get("iteration", "?")
        node      = entry.get("node", "?")
        content   = str(entry.get("content", ""))[:80].replace("\n", " ")
        rows.append(f"| {iteration} | {node} | {content} |")
    return "\n".join(rows)


def _quality_table(state: AgentState) -> str:
    """Bảng điểm chất lượng — động theo active_task_types"""
    rows = [
        "| Vòng | Module | Syntax | Pylint | LLM | Score | Status |",
        "|------|--------|--------|--------|-----|-------|--------|",
    ]

    for entry in state["history"]:
        if entry.get("node") != "REVIEWER":
            continue
        content = entry.get("content", {})
        if not isinstance(content, dict):
            continue

        iteration = entry.get("iteration", "?")
        # Duyệt tất cả key feedback_* trong content
        for key, fb in content.items():
            if not key.startswith("feedback_") or not isinstance(fb, dict):
                continue
            task_type = key.replace("feedback_", "").upper()
            syntax = "✅" if fb.get("passed_syntax") else "❌"
            pylint = "✅" if fb.get("passed_pylint") else "❌"
            llm_r  = "✅" if fb.get("llm_review") == "ok" else "❌"
            score  = fb.get("quality_score", "?")
            status = fb.get("status", "?")
            rows.append(f"| {iteration} | {task_type} | {syntax} | {pylint} | {llm_r} | {score}/10 | {status} |")

    if len(rows) == 2:
        rows.append("| — | — | — | — | — | — | Chưa có dữ liệu |")
    return "\n".join(rows)


def _issues_section(state: AgentState) -> str:
    """Liệt kê lỗi từ tất cả module — động"""
    sections = []

    for entry in state["history"]:
        if entry.get("node") != "REVIEWER":
            continue
        content = entry.get("content", {})
        if not isinstance(content, dict):
            continue

        iteration = entry.get("iteration", "?")
        for key, fb in content.items():
            if not key.startswith("feedback_") or not isinstance(fb, dict):
                continue
            if not fb.get("issues"):
                continue
            task_type = key.replace("feedback_", "").upper()
            sections.append(f"\n**Vòng {iteration} — {task_type}:**")
            for issue in fb["issues"]:
                sections.append(f"- ❌ {issue}")
            for suggestion in fb.get("suggestions", []):
                sections.append(f"  → 💡 {suggestion}")

    return "\n".join(sections) if sections else "_Không có lỗi nào được ghi nhận._"


def _code_section(state: AgentState) -> str:
    """Hiển thị code cuối cùng — động theo active_task_types"""
    iteration    = state["iteration"]
    active_types = state.get("active_task_types", ["UI", "DB"])
    sections     = []

    for task_type in active_types:
        config   = TASK_TYPES.get(task_type, {})
        fname    = f"output/iteration_{iteration}/{task_type.lower()}_code.py"
        sections.append(f"\n### {task_type} — {config.get('desc', '')}\n")
        if os.path.exists(fname):
            with open(fname, "r", encoding="utf-8") as f:
                code = f.read()
            sections.append(f"```python\n{code}\n```")
        else:
            sections.append(f"_File không tìm thấy: `{fname}`_")

    return "\n".join(sections)


def _context_section(state: AgentState) -> str:
    if not state.get("context_summary"):
        return "_Không có context dự án._"
    return state["context_summary"]


def reporter_node(state: AgentState) -> dict:
    log_step(state["iteration"], "REPORTER", "Đang tạo báo cáo tự động...")

    timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_file  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_folder = f"output/iteration_{state['iteration']}"
    os.makedirs(out_folder, exist_ok=True)
    os.makedirs("reports", exist_ok=True)

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

    active_types = state.get("active_task_types", [])
    report = f"""# 📋 BÁO CÁO PIPELINE — {timestamp}

---

## 1. Tổng quan

**Yêu cầu:** {state['user_request']}
**Modules:** {', '.join(active_types)}
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

    report_path = f"reports/report_{date_file}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    log_step(state["iteration"], "REPORTER", f"✅ Báo cáo đã lưu: {report_path}")

    if state["status"] == "done":
        print("\n  🧠 Lưu memory...")
        save_template(request=state["user_request"], plan=state["current_plan"])
        save_patterns(history=state["history"])
        print("  ✅ Memory đã cập nhật")

    # ← Chỉ entry MỚI
    return {
        "history": [{"iteration": state["iteration"], "node": "REPORTER",
                     "content": report_path}]
    }