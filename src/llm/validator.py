"""
Parses and validates the raw JSON string returned by the LLM.
Catches malformed output, missing fields, over-length bullets,
and extra trailing content after the JSON.
"""

import json
import re


REQUIRED_TOP_KEYS = ["bullet_rewrites", "confidence"]
MAX_BULLET_CHARS = 200   # hard reject threshold


def parse_llm_response(raw: str) -> dict:
    """
    Parse raw LLM text into validated dict.

    Raises:
        ValueError – if JSON is invalid or required fields are missing.
    """
    # Strip markdown fences
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw)

    # Try direct parse first
    data = _try_parse(raw)

    if data is None:
        # "Extra data" error — LLM appended text after the JSON.
        # Find the outermost matching {} and parse just that.
        data = _extract_first_json_object(raw)

    if data is None:
        raise ValueError(
            f"LLM returned invalid JSON.\n"
            f"Raw response (first 500 chars):\n{raw[:500]}"
        )

    # Validate required fields
    for key in REQUIRED_TOP_KEYS:
        if key not in data:
            raise ValueError(f"LLM response missing required key: '{key}'")

    # Validate bullet rewrites
    for i, br in enumerate(data.get("bullet_rewrites", [])):
        for fld in ["section", "bullet_index", "original", "rewritten"]:
            if fld not in br:
                raise ValueError(f"bullet_rewrites[{i}] missing field: '{fld}'")

        length = len(br["rewritten"])
        if length > MAX_BULLET_CHARS:
            print(f"  ⚠ bullet_rewrites[{i}] is {length} chars (target ≤180)")

    return data


def _try_parse(raw: str) -> dict | None:
    """Try to parse the entire string as JSON."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _extract_first_json_object(raw: str) -> dict | None:
    """
    Find the first complete top-level { ... } in the string
    by counting brace depth. Handles the common case where
    the LLM appends commentary after the JSON.
    """
    start = raw.find('{')
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(raw)):
        ch = raw[i]

        if escape_next:
            escape_next = False
            continue

        if ch == '\\' and in_string:
            escape_next = True
            continue

        if ch == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                # Found the complete JSON object
                candidate = raw[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None

    return None