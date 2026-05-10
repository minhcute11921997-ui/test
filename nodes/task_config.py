# nodes/task_config.py

# Tất cả task type được hỗ trợ
TASK_TYPES = {
    "UI":     {"desc": "Frontend/UI code",          "state_field": "code_ui",     "feedback_field": "feedback_ui"},
    "DB":     {"desc": "Database/model code",        "state_field": "code_db",     "feedback_field": "feedback_db"},
    "API":    {"desc": "API/backend routes code",    "state_field": "code_api",    "feedback_field": "feedback_api"},
    "AUTH":   {"desc": "Authentication/auth code",   "state_field": "code_auth",   "feedback_field": "feedback_auth"},
    "TEST":   {"desc": "Unit/integration test code", "state_field": "code_test",   "feedback_field": "feedback_test"},
}

# Ngưỡng phân loại độ phức tạp (dùng để hint cho LLM)
COMPLEXITY_HINTS = {
    "simple":  "2 tasks: UI + DB only",
    "medium":  "3 tasks: UI + DB + API",
    "complex": "4-5 tasks: UI + DB + API + AUTH and/or TEST",
}