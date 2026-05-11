# nodes/prompt_builder.py

def build_coder_prompt(
    task: dict,
    task_type: str,
    mode: str,                    # "new" | "fix" | "improve"
    prev_code: str = "",
    error_detail: str = "",
    fix_instruction: str = "",
    cross_context: str = "",
    relevant_code: str = "",
    context_summary: str = "",
    timeout_issues: list = None,
) -> str:
    timeout_issues = timeout_issues or []

    # ── Block cơ bản luôn có ──────────────────────────────────
    base = f"""RULES:
- Write COMPLETE, FULLY FUNCTIONAL code — no stubs, no placeholders.
- Include ALL imports, ALL function bodies, ALL error handling.
- If multiple files needed, use format:
    ### filename.ext
    ```python
    ...code...
    ```
- No explanation text.

You are an expert Python developer.
Task   : {task.get('name', task_type)}
Type   : {task_type}
Goal   : {task.get('description', f'Build {task_type} module')}"""

    # ── Block spec chi tiết (nếu planner có sinh ra) ──────────
    spec_block = ""
    required_functions  = task.get("required_functions", [])
    required_endpoints  = task.get("required_endpoints", [])
    acceptance_criteria = task.get("acceptance_criteria", [])

    if required_functions:
        spec_block += "\n\nREQUIRED FUNCTIONS (implement ALL):\n"
        spec_block += "\n".join(f"  - {f}" for f in required_functions)

    if required_endpoints:
        spec_block += "\n\nREQUIRED ENDPOINTS (implement ALL):\n"
        spec_block += "\n".join(f"  - {e}" for e in required_endpoints)

    if acceptance_criteria:
        spec_block += "\n\nACCEPTANCE CRITERIA:\n"
        spec_block += "\n".join(f"  - {c}" for c in acceptance_criteria)

    # ── Block context dự án (nếu có) ──────────────────────────
    context_block = ""
    if context_summary:
        context_block = f"\n\nPROJECT CONTEXT:\n{context_summary[:500]}"

    # ── Block code liên quan từ module khác (nếu có) ──────────
    cross_block = ""
    if cross_context:
        cross_block = f"\n\nRELATED MODULES (your code must integrate with these):\n{cross_context}"

    # ── Block code hiện có của dự án (nếu có) ─────────────────
    existing_block = ""
    if relevant_code:
        existing_block = f"\n\nEXISTING CODE TO EXTEND:\n{relevant_code}"

    # ── Block theo mode ───────────────────────────────────────
    if mode == "new":
        mode_block = "\n\nWrite clean, working Python code."
        if relevant_code:
            mode_block = "\n\nExtend the existing code above — do NOT rewrite from scratch."
        mode_block += "\nAlso create a requirements.txt listing all pip packages used."

    elif mode == "fix":
        mode_block = f"""

PREVIOUS CODE WITH ISSUES:
{prev_code}

ERRORS TO FIX (fix ALL of these):
{error_detail}"""
        if fix_instruction:
            mode_block += f"\n\nADDITIONAL FIX INSTRUCTION:\n{fix_instruction}"

    elif mode == "improve":
        perf_block = ""
        if timeout_issues:
            perf_block = (
                "\n\nPERFORMANCE ISSUES (tests timed out > 30s):\n"
                + "\n".join(f"  - {i}" for i in timeout_issues)
                + "\nOptimize: reduce complexity, avoid nested loops O(n²)+, use generators."
            )
        mode_block = f"""

CURRENT CODE:
{prev_code}

IMPROVEMENT NEEDED:
{fix_instruction}{perf_block}"""

    else:
        mode_block = ""

    # ── Ghép tất cả lại ───────────────────────────────────────
    parts = [base, spec_block, context_block, existing_block, cross_block, mode_block]
    return "\n".join(p for p in parts if p.strip())