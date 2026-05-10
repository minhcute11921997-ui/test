# test_coder.py
from langchain_ollama import OllamaLLM

llm_coder = OllamaLLM(
    model="qwen2.5-coder:7b",
    temperature=0.1,
)

prompt = """
Write a simple Python function to connect to SQLite database.
Return ONLY the code, no explanation.
"""

print("Đang gọi Coder model...")
response = llm_coder.invoke(prompt)
print("\n--- Code sinh ra ---")
print(response)