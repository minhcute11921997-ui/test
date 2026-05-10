# main.py
from state import create_initial_state
from graph import build_graph
from utils import save_log, log_step

def main():
    print("\n" + "🚀" * 25)
    print("  MULTI-AGENT PIPELINE")
    print("🚀" * 25)

    user_request = input("\n📝 Nhập yêu cầu của bạn: ").strip()
    if not user_request:
        user_request = "Build a simple todo web app with Python"

    print(f"\n✅ Bắt đầu với yêu cầu: {user_request}")

    # Tạo state ban đầu
    state = create_initial_state(user_request)

    # Build và chạy graph
    graph = build_graph()
    final_state = graph.invoke(state)

    # Kết quả cuối
    print(f"\n{'='*55}")
    print("  📊 KẾT QUẢ CUỐI CÙNG")
    print(f"{'='*55}")
    print(f"  Tổng vòng lặp : {final_state['iteration']}")
    print(f"  Trạng thái    : {final_state['status']}")
    print(f"  Output tại    : output/iteration_{final_state['iteration']}/")
    print(f"  Báo cáo tại   : reports/")
    print(f"{'='*55}")

    # Lưu log cuối
    save_log(final_state["history"])

if __name__ == "__main__":
    main()