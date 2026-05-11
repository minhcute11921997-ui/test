python
# config/pipeline_config.py  (tạo folder config/ và file __init__.py rỗng)

# ── Retry & loop limits ─────────────────────────────────────────────
MAX_TESTER_RETRIES = 2
MAX_ITERATIONS     = 5

# ── Routing constants ───────────────────────────────────────────────
TESTER_ROUTE_RETRY    = "retry"
TESTER_ROUTE_PASS     = "pass"
TESTER_ROUTE_OPTIMIZE = "optimize"