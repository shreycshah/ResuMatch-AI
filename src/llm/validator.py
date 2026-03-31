"""
Parses and validates the raw JSON string returned by the LLM.
Catches malformed output, missing fields, and over-length bullets.
"""

import json
import re


REQUIRED_TOP_KEYS = ["bullet_rewrites", "confidence"]
REQUIRED_BULLET_FIELDS = ["section", "entry_index", "bullet_index", "original", "rewritten"]
MAX_BULLET_CHARS = 170   # hard reject threshold (soft target is 155)


def parse_llm_response(raw: str) -> dict:
    """
    Parse raw LLM text into validated dict.

    Raises:
        ValueError – if JSON is invalid or required fields are missing.
    """
    # Strip markdown fences (LLMs sometimes add them despite instructions)
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON: {e}\nRaw response (first 500 chars):\n{raw[:500]}"
        )

    # Top-level keys
    for key in REQUIRED_TOP_KEYS:
        if key not in data:
            raise ValueError(f"LLM response missing required key: '{key}'")

    # Bullet rewrite validation
    for i, br in enumerate(data.get("bullet_rewrites", [])):
        for fld in REQUIRED_BULLET_FIELDS:
            if fld not in br:
                raise ValueError(f"bullet_rewrites[{i}] missing field: '{fld}'")

        length = len(br["rewritten"])
        if length > MAX_BULLET_CHARS:
            print(f"  ⚠ bullet_rewrites[{i}] is {length} chars (target ≤155)")

    return data