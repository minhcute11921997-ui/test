# utils.py — thêm hàm này

import re

def clean_code(raw: str) -> str:
    """
    Làm sạch output từ LLM:
    1. Bóc markdown code block (```python ... ```)
    2. Xóa text thừa trước/sau code
    3. Xóa BOM và ký tự lạ
    """
    if not raw:
        return ""

    text = raw.strip()

    # ── Bước 1: Tìm và lấy nội dung trong ```python ... ``` ──
    # Ưu tiên block có từ khóa python
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # ── Bước 2: Nếu không có markdown, tìm dòng bắt đầu code ──
    # Code Python thường bắt đầu bằng: import, from, def, class, #
    code_start_patterns = [
        r"^(import\s+\w+)",
        r"^(from\s+\w+)",
        r"^(def\s+\w+)",
        r"^(class\s+\w+)",
        r"^(#.*)",
        r"^(\w+\s*=)",
    ]

    lines = text.split("\n")
    start_idx = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        for pattern in code_start_patterns:
            if re.match(pattern, stripped):
                start_idx = i
                break
        else:
            continue
        break

    # Lấy từ dòng code đầu tiên đến hết
    # Cắt bỏ text trailing sau code (nếu có)
    code_lines = lines[start_idx:]

    # Xóa trailing text sau block code cuối
    end_idx = len(code_lines)
    for i in range(len(code_lines) - 1, -1, -1):
        line = code_lines[i].strip()
        # Dòng text thuần (không phải code, không phải comment)
        if line and not line.startswith("#") and not line.startswith("\"\"\"") and \
           not any(c in line for c in ["=", ":", "(", ")", "[", "]", ".", "import", "return"]):
            # Có thể là text thừa — dừng ở đây
            if re.match(r"^[A-Z][a-z].*[.!]$", line):  # Câu hoàn chỉnh như "Hope this helps!"
                end_idx = i
        else:
            break

    result = "\n".join(code_lines[:end_idx]).strip()

    # ── Bước 3: Xóa BOM và ký tự lạ ─────────────────────────
    result = result.replace("\ufeff", "")   # BOM
    result = result.replace("\r\n", "\n")   # Windows line endings

    return result