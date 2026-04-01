"""
LLM API clients for Anthropic and OpenAI.
Each function takes parsed resume + JD, returns validated dict.

Model names, max_tokens, and system prompt are read from llm_config.yaml
(via src.config); built-in values are used as fallbacks.
"""

from src.models.resume import ResumeJSON
from src.models.job_description import JobDescription
from src.llm.prompt_builder import build_user_prompt
from src.llm.validator import parse_llm_response
from src.config import get_config

from dotenv import load_dotenv
from pathlib import Path
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_env_path)

MAX_RETRIES = 1

def call_anthropic(resume: ResumeJSON, jd: JobDescription) -> dict:
    """Call Anthropic with prompt caching on the system prompt."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("Install the Anthropic SDK:  pip install anthropic")

    cfg = get_config().resume_tailoring
    model = cfg.model_for("anthropic")
    max_tokens = cfg.max_tokens_for("anthropic")
    system_prompt = cfg.prompt

    print(f"   [resume_tailoring] anthropic / {model}")
    client = anthropic.Anthropic()
    user_msg = build_user_prompt(resume, jd)

    for attempt in range(1 + MAX_RETRIES):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": user_msg,
            }],
        )

        raw = response.content[0].text.strip()
        stop = response.stop_reason

        # Check if output was truncated
        if stop == "max_tokens":
            if attempt < MAX_RETRIES:
                print(f"  ⚠ Response truncated (hit {max_tokens} tokens), retrying with shorter prompt...")
                user_msg = _shorten_prompt(user_msg)
                continue
            else:
                print(f"  ⚠ Response still truncated after retry — attempting partial JSON recovery")
                return _recover_truncated_json(raw)

        return parse_llm_response(raw)

    # Should not reach here, but just in case
    return parse_llm_response(raw)


def call_openai(resume: ResumeJSON, jd: JobDescription) -> dict:
    """Call OpenAI with JSON mode enabled."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Install the OpenAI SDK:  pip install openai")

    cfg = get_config().resume_tailoring
    model = cfg.model_for("openai")
    max_tokens = cfg.max_tokens_for("openai")
    system_prompt = cfg.prompt

    print(f"   [resume_tailoring] openai / {model}")
    client = OpenAI()
    user_msg = build_user_prompt(resume, jd)

    for attempt in range(1 + MAX_RETRIES):
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.3,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
        )

        choice = response.choices[0]
        raw = choice.message.content.strip()
        finish = choice.finish_reason

        # Check if output was truncated
        if finish == "length":
            if attempt < MAX_RETRIES:
                print(f"  ⚠ Response truncated (hit {max_tokens} tokens), retrying with shorter prompt...")
                user_msg = _shorten_prompt(user_msg)
                continue
            else:
                print(f"  ⚠ Response still truncated after retry — attempting partial JSON recovery")
                return _recover_truncated_json(raw)

        return parse_llm_response(raw)

    return parse_llm_response(raw)


# ── Truncation helpers ──

def _shorten_prompt(user_msg: str) -> str:
    """
    Reduce the prompt size by trimming the raw JD description.
    This is the fattest variable-length component.
    """
    import json
    try:
        data = json.loads(user_msg)
        jd = data.get("job_description", {})
        raw = jd.get("raw_description", "")
        # Cut to 1500 chars (from 3000 default)
        jd["raw_description"] = raw[:1500]
        return json.dumps(data, indent=None, ensure_ascii=False)
    except Exception:
        return user_msg


def _recover_truncated_json(raw: str) -> dict:
    """
    Attempt to salvage a truncated JSON response.
    Strategy: close all open braces/brackets, then parse.
    We'll get a partial result (some bullets may be missing) but it's
    better than crashing.
    """
    import json

    # Strip markdown fences
    import re
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw)

    # Find the last complete bullet_rewrite entry (ends with })
    # Truncate everything after it, then close the arrays/objects
    last_complete = raw.rfind('"truthfulness_flag"')
    if last_complete == -1:
        last_complete = raw.rfind('"rationale"')
    if last_complete == -1:
        last_complete = raw.rfind('"rewritten"')

    if last_complete > 0:
        # Find the closing } of that object
        brace_pos = raw.find('}', last_complete)
        if brace_pos > 0:
            raw = raw[:brace_pos + 1]

    # Close any open structures
    open_brackets = raw.count('[') - raw.count(']')
    open_braces = raw.count('{') - raw.count('}')

    raw = raw.rstrip(', \n')
    raw += ']' * max(0, open_brackets)
    raw += '}' * max(0, open_braces)

    # Add missing top-level fields if they were truncated
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Last resort: build minimal valid response
        print("  ⚠ Could not recover truncated JSON — returning empty result")
        return {
            "tailored_summary": None,
            "bullet_rewrites": [],
            "skills_reordered": None,
            "skills_added": [],
            "confidence": {
                "ats_keyword_coverage": 0.0,
                "bullets_modified": 0,
                "truthfulness_violations": 0,
            },
        }

    # Ensure required keys exist
    data.setdefault("bullet_rewrites", [])
    data.setdefault("confidence", {
        "ats_keyword_coverage": 0.0,
        "bullets_modified": len(data.get("bullet_rewrites", [])),
        "truthfulness_violations": 0,
    })
    data.setdefault("tailored_summary", None)
    data.setdefault("skills_reordered", None)
    data.setdefault("skills_added", [])

    n = len(data["bullet_rewrites"])
    print(f"  ⚠ Recovered {n} bullet rewrites from truncated response")

    return data