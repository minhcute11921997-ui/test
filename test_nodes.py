# test_nodes.py
from state import create_initial_state
from nodes.planner import planner_node
from nodes.human_gate import human_gate_node

print("Test Planner + Human Gate...")
state = create_initial_state("Build a simple todo web app")
state = planner_node(state)
state = human_gate_node(state)

print(f"\n✅ Plan: {state['current_plan']}")
print(f"✅ Decision: {state['human_decision']}")