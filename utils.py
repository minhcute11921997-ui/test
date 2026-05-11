# utils.py
import json
import re
import os
from datetime import datetime


def clean_code(raw: str) -> str:
    """
    Làm sạch output từ LLM:
    1. Bóc markdown code block (```python ... ```)
    2. Nếu không có markdown, tìm dòng bắt đầu code thực sự
    3. Xóa BOM và ký tự lạ
    """
    if not raw:
        return ""

    text = raw.strip()

    # ── Bước 1: Tìm block ```python ... ``` hoặc ``` ... ``` ──
    # Ưu tiên ```python, fallback về ``` bất kỳ
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if match:
        code = match.group(1).strip()
        return _clean_chars(code)

    # ── Bước 2: Không có markdown — tìm dòng đầu tiên trông như code Python ──
    # Code Python thường bắt đầu bằng: import, from, def, class, #, hoặc assignment
    code_start_re = re.compile(
        r"^(import\s+\w|from\s+\w|def\s+\w|class\s+\w|#|@\w|\w+\s*=)",
        re.MULTILINE,
    )
    match = code_start_re.search(text)
    if match:
        code = text[match.start():]
        # Cắt phần trailing text KHÔNG phải code (ví dụ "Hope this helps!")
        # Chỉ cắt nếu phần cuối là văn xuôi rõ ràng (không chứa dấu Python)
        code = _strip_trailing_prose(code)
        return _clean_chars(code)

    # ── Bước 3: Không nhận diện được — trả nguyên ──
    return _clean_chars(text)


def _strip_trailing_prose(code: str) -> str:
    """
    Cắt bỏ phần trailing text sau code.
    Chỉ cắt dòng cuối nếu nó trông như văn xuôi hoàn toàn
    (không có ký tự Python nào: =, :, (, ), [, ], ., import, def, return, #).
    An toàn hơn: chỉ cắt tối đa 3 dòng cuối.
    """
    python_chars = re.compile(r'[=:()\[\].@]|import\s|def\s|return\s|#')
    lines        = code.rstrip().split("\n")

    # Chỉ xét tối đa 3 dòng cuối
    cutoff = len(lines)
    for i in range(len(lines) - 1, max(len(lines) - 4, -1), -1):
        line = lines[i].strip()
        if not line:
            continue
        # Nếu dòng này có dấu hiệu Python → dừng, không cắt thêm
        if python_chars.search(line):
            break
        # Dòng này trông như văn xuôi → đánh dấu để cắt
        cutoff = i

    return "\n".join(lines[:cutoff]).rstrip()


def _clean_chars(code: str) -> str:
    """Xóa BOM và chuẩn hóa line endings"""
    return code.replace("\ufeff", "").replace("\r\n", "\n").strip()


def parse_json_safe(text: str) -> dict | None:
    """Parse JSON an toàn từ output LLM"""
    if not text:
        return None

    # Thử parse trực tiếp
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Tìm block JSON trong text (LLM hay thêm text thừa xung quanh)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Thử strip markdown fences rồi parse lại
    stripped = re.sub(r"```(?:json)?\s*\n?", "", text).replace("```", "").strip()
    try:
        return json.loads(stripped)
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
    """Lưu toàn bộ history ra file log"""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"logs/run_{timestamp}.json"

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