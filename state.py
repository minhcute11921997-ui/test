# state.py
from typing import TypedDict, Optional, Annotated
from operator import add
from config.pipeline_config import MAX_ITERATIONS

# ── Các field BẮT BUỘC phải có ngay từ đầu ────────────────────────
class _RequiredState(TypedDict):
    user_request:   str
    iteration:      int
    max_iterations: int
    auto_mode:      bool
    status:         str
    history:        Annotated[list, add]


# ── Các field TUỲ CHỌN — chỉ có sau khi node tương ứng chạy ───────
class _OptionalState(TypedDict, total=False):
    # Plan
    original_plan:     dict
    current_plan:      dict
    complexity:        str
    active_task_types: list
    module_contracts:  dict        # ← THÊM MỚI

    # Code output
    code_ui:   str
    code_db:   str
    code_api:  str
    code_auth: str
    code_test: str

    # Feedback từ Reviewer
    feedback_ui:   dict
    feedback_db:   dict
    feedback_api:  dict
    feedback_auth: dict
    feedback_test: dict

    # Evaluator
    all_good: bool
    new_plan: dict

    # Human gate
    human_decision:    str
    extra_requirement: str

    # Context
    project_spec:    str
    existing_code:   dict
    context_summary: str
    db_tables:       list
    db_schemas:      dict

    # Tester
    test_results:       dict
    test_issues:        list
    hard_test_issues:   list
    timeout_issues:     list
    tester_retry_count: int


class AgentState(_RequiredState, _OptionalState):
    """State tổng hợp — required + optional fields."""
    pass


def create_initial_state(user_request: str, auto_mode: bool = False) -> AgentState:
    return AgentState(
        user_request=user_request,
        iteration=0,
        max_iterations=MAX_ITERATIONS,

        auto_mode=auto_mode,

        original_plan={},
        current_plan={},
        module_contracts={},       # ← THÊM MỚI

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