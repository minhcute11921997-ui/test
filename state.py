# state.py
from typing import TypedDict, Optional, Annotated
from operator import add

class AgentState(TypedDict):
    # ── Thông tin cơ bản ──────────────────────────
    user_request: str           # Yêu cầu gốc từ user
    iteration: int              # Đang ở vòng lặp thứ mấy
    max_iterations: int         # Giới hạn vòng lặp tối đa

    # ── Plan ──────────────────────────────────────
    original_plan: dict         # Plan đầu tiên, không đổi
    current_plan: dict          # Plan hiện tại (có thể được cập nhật)

    # ── Output của các Coder ──────────────────────
    code_ui: str                # Code UI từ Coder A
    code_db: str                # Code DB từ Coder B
    code_api:  str    
    code_auth: str    
    code_test: str    

    # ── Feedback từ Reviewer ──────────────────────
    feedback_ui: dict           # {"status": "ok/error", "comment": "..."}
    feedback_db: dict
    feedback_api:  dict    # ← thêm
    feedback_auth: dict    # ← thêm
    feedback_test: dict  

    # ── Quyết định từ Evaluator ───────────────────
    all_good: bool              # True = hoàn thành
    new_plan: dict              # Plan mới nếu có lỗi

    # ── Human intervention ────────────────────────
    human_decision: str         # "continue" / "stop" / "modify"
    extra_requirement: str      # Yêu cầu thêm từ người dùng
    status: str                 # "running" / "stopped" / "done" / "awaiting_human"

    # ── Lịch sử (cho báo cáo) ────────────────────
    history: Annotated[list, add]              # Log toàn bộ các vòng lặp

    # ── Context từ dự án ──────────────────────────
    project_spec: str       # Nội dung file .txt/.md
    existing_code: dict     # {"filename": "code content"}
    context_summary: str    # Tóm tắt context (do LLM tạo)
    # ── DB context ────────────────────────────────────────────
    db_tables:  list    # ["users", "tasks", ...]
    db_schemas: dict    # {"users": {"id": "int", "name": "str"}, ...}
    # ── Danh sách task type thực tế ở vòng này ───────────────
    active_task_types: list  # ← thêm: ["UI","DB"] hoặc ["UI","DB","API","AUTH"]

    test_results: dict    # kết quả chi tiết từng lớp
    test_issues:  list    # danh sách lỗi → tester trả về để graph routing

def create_initial_state(user_request: str) -> AgentState:
    """Tạo state ban đầu khi bắt đầu pipeline"""
    return AgentState(
        user_request=user_request,
        iteration=0,
        max_iterations=5,

        original_plan={},
        current_plan={},

        code_ui="",
        code_db="",
        code_api   = "",
        code_auth  = "",
        code_test  = "",

        feedback_ui={},
        feedback_db={},
        feedback_api  = {},
        feedback_auth = {},
        feedback_test = {},

        active_task_types = [],

        all_good=False,
        new_plan={},

        human_decision="",
        extra_requirement="",
        status="running",

        history=[],

        project_spec="",
        existing_code={},
        context_summary="",
        db_tables=[],
        db_schemas={},
    )


def log_to_history(state: AgentState, node: str, content: str) -> AgentState:
    return {
        "history": [{
            "iteration": state["iteration"],
            "node": node,
            "content": content,
        }]
    }