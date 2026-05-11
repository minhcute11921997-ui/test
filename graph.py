# graph.py
from langgraph.graph import StateGraph, END
from state import AgentState
from nodes.planner import planner_node
from nodes.coder import (
    coder_a_node, coder_b_node,
    coder_api_node, coder_auth_node, coder_test_node
)
from nodes.reviewer  import reviewer_node
from nodes.integrator import integrator_node
from nodes.evaluator  import evaluator_node
from nodes.human_gate import human_gate_node
from nodes.context_loader import context_loader_node
from nodes.reporter  import reporter_node
from nodes.tester import tester_node
from config.pipeline_config import MAX_TESTER_RETRIES


CODER_NODES = {
    "UI":   ("coder_ui",   coder_a_node),
    "DB":   ("coder_db",   coder_b_node),
    "API":  ("coder_api",  coder_api_node),
    "AUTH": ("coder_auth", coder_auth_node),
    "TEST": ("coder_test", coder_test_node),
}


def route_to_first_coder(state: AgentState) -> str:
    types = state.get("active_task_types", ["UI"])
    first = types[0] if types else "UI"
    node_name, _ = CODER_NODES.get(first, ("coder_ui", coder_a_node))
    return node_name


def route_between_coders(task_type: str):
    def _route(state: AgentState) -> str:
        types = state.get("active_task_types", ["UI", "DB"])
        try:
            idx = types.index(task_type)
        except ValueError:
            return "tester"

        next_idx = idx + 1
        if next_idx >= len(types):
            return "tester"

        next_type    = types[next_idx]
        next_node, _ = CODER_NODES.get(next_type, ("tester", None))
        return next_node
    return _route


MAX_TESTER_RETRIES = 2

def route_after_tester(state: AgentState) -> str:
    hard_issues    = state.get("hard_test_issues", [])
    timeout_issues = state.get("timeout_issues", [])

    # Không có gì → pass thẳng
    if not hard_issues and not timeout_issues:
        return "pass"

    # Chỉ có timeout (không có lỗi thật) → đi tiếp nhưng báo coder cần tối ưu
    if not hard_issues and timeout_issues:
        print(f"\n  ⏱️  Chỉ có timeout issues ({len(timeout_issues)}) — tiếp tục nhưng yêu cầu tối ưu")
        return "optimize"   # ← route mới → đến reviewer (không retry planner)

    # Có lỗi thật → retry planner nếu còn lượt
    tester_retry_count = state.get("tester_retry_count", 0)
    if tester_retry_count >= MAX_TESTER_RETRIES:
        print(f"\n  ⚠️  Tester đã retry {MAX_TESTER_RETRIES} lần — bỏ qua, tiếp tục reviewer")
        return "pass"

    return "retry"


def should_continue(state: AgentState) -> str:
    if state["status"] in ["done", "stopped"]:
        return "end"
    if state["iteration"] >= state["max_iterations"]:
        print(f"\n⚠️  Đã đạt giới hạn {state['max_iterations']} vòng lặp!")
        return "end"
    return "continue"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("context_loader", context_loader_node)
    graph.add_node("planner",        planner_node)
    graph.add_node("human_gate",     human_gate_node)
    graph.add_node("tester",         tester_node)
    graph.add_node("reviewer",       reviewer_node)
    graph.add_node("integrator",     integrator_node)
    graph.add_node("evaluator",      evaluator_node)
    graph.add_node("reporter",       reporter_node)

    for type_name, (node_name, node_fn) in CODER_NODES.items():
        graph.add_node(node_name, node_fn)

    graph.set_entry_point("context_loader")
    graph.add_edge("context_loader", "planner")
    graph.add_edge("planner",        "human_gate")

    graph.add_conditional_edges(
        "human_gate",
        route_to_first_coder,
        {node_name: node_name for _, (node_name, _) in CODER_NODES.items()},
    )

    for type_name, (node_name, _) in CODER_NODES.items():
        next_nodes = {n: n for _, (n, _) in CODER_NODES.items()}
        next_nodes["tester"] = "tester"
        graph.add_conditional_edges(
            node_name,
            route_between_coders(type_name),
            next_nodes,
        )

    graph.add_conditional_edges(
        "tester",
        route_after_tester,
        {"retry": "planner", "pass": "reviewer", "optimize": "reviewer"},
    )

    graph.add_edge("reviewer",   "integrator")
    graph.add_edge("integrator", "evaluator")

    graph.add_conditional_edges(
        "evaluator",
        should_continue,
        {"continue": "planner", "end": "reporter"},
    )
    graph.add_edge("reporter", END)

    return graph.compile()