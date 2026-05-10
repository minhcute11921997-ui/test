# test_ollama.py
from langchain_ollama import OllamaLLM
import json

# Khởi tạo model
llm = OllamaLLM(
    model="qwen2.5:14b",
    format="json",        # Bắt buộc ra JSON
    temperature=0.1,      # Thấp = ổn định hơn
)

# Prompt test đơn giản
prompt = """
You are a task planner. Return ONLY valid JSON, no explanation.

User request: "Build a simple todo web app"

Return this exact structure:
{
  "tasks": [
    {"id": 1, "name": "task name", "type": "UI or DB or API"},
    {"id": 2, "name": "task name", "type": "UI or DB or API"}
  ]
}
"""

print("Đang gọi model...")
response = llm.invoke(prompt)
print("\n--- Raw response ---")
print(response)

# Parse thử
try:
    data = json.loads(response)
    print("\n--- Parsed JSON ---")
    print(json.dumps(data, indent=2))
    print("\n✅ JSON hợp lệ!")
except json.JSONDecodeError as e:
    print(f"\n❌ JSON lỗi: {e}")