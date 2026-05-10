# graph.py
from langgraph.graph import StateGraph, END
from state import AgentState
from nodes.planner import planner_node
from nodes.coder import coder_a_node, coder_b_node
from nodes.reviewer import reviewer_node
from nodes.integrator import integrator_node
from nodes.evaluator import evaluator_node
from nodes.human_gate import human_gate_node
from nodes.context_loader import context_loader_node
from nodes.reporter import reporter_node


def should_continue(state: AgentState) -> str:
    """
    Hàm điều hướng sau Evaluator:
    - Nếu xong hoặc bị dừng → END
    - Nếu còn lỗi và chưa hết vòng → quay lại Planner
    """
    if state["status"] in ["done", "stopped"]:
        return "end"
    if state["iteration"] >= state["max_iterations"]:
        print(f"\n⚠️  Đã đạt giới hạn {state['max_iterations']} vòng lặp!")
        return "end"
    return "continue"


def build_graph():
    """Xây dựng và compile graph"""
    graph = StateGraph(AgentState)

    # Thêm các node
    graph.add_node("context_loader", context_loader_node)
    graph.add_node("planner",    planner_node)
    graph.add_node("human_gate", human_gate_node)
    graph.add_node("coder_a",    coder_a_node)
    graph.add_node("coder_b",    coder_b_node)
    graph.add_node("reviewer",   reviewer_node)
    graph.add_node("integrator", integrator_node)
    graph.add_node("evaluator",  evaluator_node)
    graph.add_node("reporter",   reporter_node)
    # Kết nối các node theo thứ tự
    graph.set_entry_point("context_loader")
    graph.add_edge("context_loader", "planner")
    graph.add_edge("planner",    "human_gate")   # Checkpoint #1: duyệt plan
    graph.add_edge("human_gate", "coder_a")
    graph.add_edge("coder_a",    "coder_b")
    graph.add_edge("coder_b",    "reviewer")
    graph.add_edge("reviewer",   "integrator")
    graph.add_edge("integrator", "evaluator")
    graph.add_edge("evaluator",  "reporter")
    # Điều hướng có điều kiện sau Evaluator
    graph.add_conditional_edges(
        "evaluator",
        should_continue,
        {
            "continue": "planner",
            "end": "reporter"           
        }
    )
    graph.add_edge("reporter", END) 

    return graph.compile()