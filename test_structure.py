# test_structure.py
from state import create_initial_state, log_to_history
from utils import log_step, save_log

# Test tạo state
state = create_initial_state("Build a simple todo web app")
print("✅ State tạo thành công:")
print(f"   Request: {state['user_request']}")
print(f"   Max iterations: {state['max_iterations']}")
print(f"   Status: {state['status']}")

# Test log
state = log_to_history(state, "TEST", "Đây là test entry")
log_step(0, "TEST NODE", "Cấu trúc project hoạt động tốt!")

# Test save log
save_log(state["history"])
print("\n✅ Tất cả OK — sẵn sàng sang Bước 4!")