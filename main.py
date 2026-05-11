# main.py
from state import create_initial_state
from graph import build_graph
from utils import save_log, log_step
from nodes.tester import extract_and_install_imports
import os


def _get_user_input() -> tuple[bool, str, str]:
    """Trả về (auto_mode, user_request, data_path)"""
    print("\n⚙️  Chế độ chạy:")
    print("  [1] Auto   — tự chạy hết, không hỏi lại từng vòng")
    print("  [2] Manual — hỏi xác nhận ở mỗi vòng (mặc định)")
    mode_input = input("\n  Chọn chế độ (1/2, Enter = Manual): ").strip()
    auto_mode  = (mode_input == "1")
    print(f"\n  ✅ Chế độ: {'⚡ AUTO' if auto_mode else '🖐️  MANUAL'}")

    user_request = input("\n📝 Nhập yêu cầu của bạn: ").strip()
    if not user_request:
        user_request = "Build a simple todo web app with Python"

    print("\n📂 Vị trí thư mục data/project hiện có (Enter để bỏ qua):")
    data_path = input("  Path: ").strip()

    return auto_mode, user_request, data_path
def main():
    print("\n" + "🚀" * 25)
    print("  MULTI-AGENT PIPELINE")
    print("🚀" * 25)

    auto_mode, user_request, data_path = _get_user_input() 

    # ── Nhập yêu cầu ────────────────────────────────────────
    user_request = input("\n📝 Nhập yêu cầu của bạn: ").strip()
    if not user_request:
        user_request = "Build a simple todo web app with Python"

    # ── Nhập vị trí data (nếu có) ───────────────────────────
    print("\n📂 Vị trí thư mục data/project hiện có (Enter để bỏ qua):")
    data_path = input("  Path: ").strip()

    print(f"\n✅ Bắt đầu với yêu cầu: {user_request}")
    if data_path:
        print(f"📂 Data path: {data_path}")
    if auto_mode:
        print("⚡ Pipeline sẽ tự chạy đến khi hoàn thành — không cần thao tác thêm\n")

    # ── Tạo state ban đầu ───────────────────────────────────
    state = create_initial_state(user_request, auto_mode=auto_mode)

    # ── Pre-install dependencies từ state ban đầu ──
if data_path:
    # Quét code hiện có nếu có data_path
    existing_codes = []
    for root, _, files in os.walk(data_path):
        for f in files:
            if f.endswith(".py"):
                try:
                    with open(os.path.join(root, f), encoding="utf-8") as fp:
                        existing_codes.append(fp.read())
                except Exception:
                    pass
    if existing_codes:
        print("\n🔍 Pre-scan dependencies từ code hiện có...")
        extract_and_install_imports(existing_codes)

    # Gắn data_path vào project_spec nếu có
    if data_path:
        state["project_spec"] = f"Data directory: {data_path}"

    # ── Build và chạy graph ─────────────────────────────────
    graph = build_graph()
    final_state = graph.invoke(state)

    # ── Kết quả cuối ────────────────────────────────────────
    print(f"\n{'='*55}")
    print("  📊 KẾT QUẢ CUỐI CÙNG")
    print(f"{'='*55}")
    print(f"  Tổng vòng lặp : {final_state['iteration']}")
    print(f"  Trạng thái    : {final_state['status']}")
    print(f"  Chế độ        : {'Auto' if auto_mode else 'Manual'}")
    print(f"  Output tại    : output/iteration_{final_state['iteration']}/")
    print(f"  Báo cáo tại   : reports/")
    print(f"{'='*55}")

    save_log(final_state["history"])


if __name__ == "__main__":
    main()