# state.py
from typing import TypedDict, Optional, Annotated
from operator import add

class AgentState(TypedDict):
    # ── Thông tin cơ bản ──────────────────────────
    user_request: str
    iteration: int
    max_iterations: int

    # ── Auto mode ─────────────────────────────────
    auto_mode: bool          # ← THÊM: True = không hỏi lại ở human_gate

    # ── Plan ──────────────────────────────────────
    original_plan: dict
    current_plan: dict

    # ── Output của các Coder ──────────────────────
    code_ui: str
    code_db: str
    code_api:  str
    code_auth: str
    code_test: str

    # ── Feedback từ Reviewer ──────────────────────
    feedback_ui: dict
    feedback_db: dict
    feedback_api:  dict
    feedback_auth: dict
    feedback_test: dict

    # ── Quyết định từ Evaluator ───────────────────
    all_good: bool
    new_plan: dict

    # ── Human intervention ────────────────────────
    human_decision: str
    extra_requirement: str
    status: str

    # ── Lịch sử (cho báo cáo) ────────────────────
    history: Annotated[list, add]

    # ── Context từ dự án ──────────────────────────
    project_spec: str
    existing_code: dict
    context_summary: str

    # ── DB context ────────────────────────────────
    db_tables:  list
    db_schemas: dict

    # ── Task types đang active ────────────────────
    active_task_types: list

    # ── Complexity ────────────────────────────────
    complexity: str

    # ── Tester ────────────────────────────────────
    test_results:       dict
    test_issues:        list
    hard_test_issues:   list   # ← THÊM: lỗi thật
    timeout_issues:     list
    tester_retry_count: int


def create_initial_state(user_request: str, auto_mode: bool = False) -> AgentState:
    return AgentState(
        user_request=user_request,
        iteration=0,
        max_iterations=5,

        auto_mode=auto_mode,         # ← THÊM

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

        test_results       = {},
        test_issues        = [],
        hard_test_issues   = [],
        timeout_issues     = [],
        tester_retry_count = 0,
        complexity         = "",
    )


def log_to_history(state: AgentState, node: str, content: str) -> dict:
    return {
        "history": [{
            "iteration": state["iteration"],
            "node": node,
            "content": content,
        }]
    }