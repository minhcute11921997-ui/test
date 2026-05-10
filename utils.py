# utils.py
import json
import re
import os
from datetime import datetime

def parse_json_safe(text: str) -> dict | None:
    """Parse JSON an toàn từ output LLM"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    pattern = r'\{.*\}'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def log_step(iteration: int, node: str, content: str):
    """In log đẹp ra màn hình"""
    print(f"\n{'='*55}")
    print(f"  [Vòng {iteration}] ▶ {node}")
    print(f"{'─'*55}")
    print(content)
    print(f"{'='*55}")


def save_log(history: list, filename: str = None):
    """Lưu toàn bộ history ra file log — dùng cho báo cáo"""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs/run_{timestamp}.json"

    os.makedirs("logs", exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"\n📄 Log đã lưu: {filename}")


def save_code(code: str, filename: str):
    """Lưu code sinh ra vào thư mục output"""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"💾 Code đã lưu: {filename}")