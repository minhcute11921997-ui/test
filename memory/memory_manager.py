# memory/memory_manager.py
import json
import os
from datetime import datetime

TEMPLATES_PATH = "memory/templates.json"
PATTERNS_PATH  = "memory/patterns.json"


def _load(path: str) -> dict:
    os.makedirs("memory", exist_ok=True)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save(path: str, data: dict):
    os.makedirs("memory", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Templates ────────────────────────────────────────────────

def save_template(request: str, plan: dict):
    """
    Lưu plan thành công vào templates.json.
    Key là 3 từ đầu của request (dùng làm request_type).
    """
    templates = _load(TEMPLATES_PATH)

    request_type = _extract_type(request)
    templates[request_type] = {
        "request_sample": request,
        "plan":           plan,
        "saved_at":       datetime.now().isoformat(),
        "use_count":      templates.get(request_type, {}).get("use_count", 0),
    }

    _save(TEMPLATES_PATH, templates)
    print(f"  💾 Đã lưu template: [{request_type}]")


def load_template(request: str) -> dict | None:
    """
    Tìm template gần nhất khớp với request hiện tại.
    Trả về plan nếu tìm thấy, None nếu không.
    """
    templates = _load(TEMPLATES_PATH)
    if not templates:
        return None

    request_type = _extract_type(request)

    # Khớp chính xác
    if request_type in templates:
        entry = templates[request_type]
        # Tăng use_count
        entry["use_count"] = entry.get("use_count", 0) + 1
        _save(TEMPLATES_PATH, templates)
        print(f"  📂 Tìm thấy template: [{request_type}] (dùng {entry['use_count']} lần)")
        return entry["plan"]

    # Khớp một phần — tìm key nào có từ chung
    request_words = set(request.lower().split())
    best_match    = None
    best_score    = 0

    for key, entry in templates.items():
        key_words = set(key.lower().split())
        score = len(request_words & key_words)
        if score > best_score:
            best_score = score
            best_match = (key, entry)

    if best_match and best_score >= 2:
        key, entry = best_match
        print(f"  📂 Template gần nhất: [{key}] (score: {best_score})")
        return entry["plan"]

    return None


# ── Patterns ─────────────────────────────────────────────────

def save_patterns(history: list):
    """
    Quét history, trích xuất các lỗi đã gặp + cách fix,
    lưu vào patterns.json.
    """
    patterns = _load(PATTERNS_PATH)

    for entry in history:
        if entry.get("node") != "REVIEWER":
            continue

        content = entry.get("content", {})
        if not isinstance(content, dict):
            continue

        for task_type in ["UI", "DB"]:
            fb_key  = f"feedback_{task_type.lower()}"
            fb      = content.get(fb_key, {})
            issues  = fb.get("issues", [])
            suggestions = fb.get("suggestions", [])

            for i, issue in enumerate(issues):
                # Dùng issue làm key (chuẩn hóa)
                key = issue.strip().lower()[:80]
                if key not in patterns:
                    patterns[key] = {
                        "issue":      issue,
                        "task_type":  task_type,
                        "fix":        suggestions[i] if i < len(suggestions) else "",
                        "seen_count": 0,
                        "last_seen":  None,
                    }
                patterns[key]["seen_count"] += 1
                patterns[key]["last_seen"]   = datetime.now().isoformat()

    _save(PATTERNS_PATH, patterns)
    print(f"  💾 Đã cập nhật patterns.json ({len(patterns)} patterns)")


def load_relevant_patterns(task_type: str, code: str = "") -> list:
    """
    Trả về list pattern hay gặp nhất cho task_type,
    để inject vào prompt của Reviewer hoặc Coder.
    """
    patterns = _load(PATTERNS_PATH)
    if not patterns:
        return []

    relevant = [
        p for p in patterns.values()
        if p.get("task_type") == task_type and p.get("seen_count", 0) >= 2
    ]

    # Sắp xếp theo tần suất gặp
    relevant.sort(key=lambda x: x["seen_count"], reverse=True)
    return relevant[:5]  # Chỉ lấy top 5


# ── Helpers ───────────────────────────────────────────────────

def _extract_type(request: str) -> str:
    """Lấy 3 từ đầu làm request_type key"""
    words = request.strip().lower().split()
    return " ".join(words[:3]) if len(words) >= 3 else request.lower()