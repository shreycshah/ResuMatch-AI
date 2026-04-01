"""
LLM configuration loader.

Reads llm_config.yaml from the project root and exposes per-task settings.
Falls back to built-in defaults when the file is missing, disabled, or a key
is omitted.

Provider schema in the YAML (both tasks use this list format):

    provider:
      - name: anthropic
        enabled: true
        model: claude-haiku-4-5-20251001
        max_tokens: 8192   # optional; falls back to task-level max_tokens
      - name: openai
        enabled: false
        model: gpt-4o

For jd_extraction  — the provider with enabled:true is the active one.
For resume_tailoring — the CLI --model flag picks which provider runs;
                       the list supplies the model/max_tokens per provider.

Default prompts live here as the single source of truth; llm_config.yaml
overrides them when a non-empty prompt is provided.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "llm_config.yaml"


# ── Default prompts ───────────────────────────────────────────────────────────

DEFAULT_EXTRACTION_PROMPT = """\
You are a specialized job description parser. Extract structured data from the provided job description and return ONLY a valid JSON object with the exact structure below — no markdown, no additional text, no explanations.

OUTPUT FORMAT
{
  "required_skills": ["skill1", "skill2"],
  "preferred_skills": ["skill1", "skill2"],
  "key_phrases": ["phrase1", "phrase2"]
}

EXTRACTION RULES
1. required_skills:
    - Technical skills, tools, languages, frameworks explicitly required
    - Include specific versions/ecosystems when mentioned (e.g., "Python 3.8", "AWS Lambda")
    - Use judgment for ambiguous cases: prioritize skills with "must have", "X+ years of", or appearing in "Requirements" sections
2. preferred_skills:
    - Skills described as "nice-to-have", "preferred", "bonus", "a plus"
    - Skills from "Preferred Qualifications" sections
    - Skills with softer language ("familiarity with", "exposure to")
3. key_phrases:
    - Domain-specific phrases, methodologies, business contexts, role-specific terminology
    - Exclude educational requirements like "Bachelors/Masters/PhD" etc
    - Exclude generic filler ("team player", "fast-paced", "excellent communication")
    - Maximum 15 phrases
    - Keep original casing

PROCESSING RULES
1. Deduplication: Each skill appears in exactly one list (required OR preferred)
2. Normalization: Lowercase all skill names
3. Validation: Ensure JSON is valid and parsable
4. Completeness: Include all relevant items from the job description
"""

DEFAULT_TAILORING_PROMPT = """\
You are an ATS resume optimization specialist. Given a resume and job description,
tailor the resume to maximize ATS pass-through and recruiter relevance.

RULES:
  1. HONESTY BASELINE: Ground rewrites in real experience. Never fabricate entire projects, roles, or companies. However, you MAY:
     - Add JD keywords for tools/skills the candidate could reasonably claim given their experience (e.g., Pandas + Spark → "data pipeline orchestration").
     - Slightly reframe scope or impact if the work plausibly involved it (e.g., "worked on deployment" → "Deployed and monitored production ML models").
     - Infer adjacent skills from demonstrated ones (e.g., PyTorch experience → "deep learning frameworks").
     - Use truthfulness_flag "yellow" for any such inference so the candidate can review.
  2. METRICS: Preserve original numbers exactly. You may add context/keywords around them but never change the values.
  3. KEYWORDS: Integrate JD keywords aggressively but readably — up to 3-4 terms per bullet. Prioritize hard skills and tools the ATS will scan for.
  4. FORMAT: Plain text only. No LaTeX commands, no backslashes, no curly braces, no special characters like &, %, #, $. Write "and" instead of "&".
  5. OUTPUT: Respond ONLY with valid JSON matching the schema below. No markdown fences, no commentary, no text outside the JSON.

SUMMARY RULES:
  - Mirror JD title + top 2-3 requirements.
  - Exactly 1-2 sentences. HARD LIMIT: ≤ 220 characters. If summary exceeds 220 characters, your entire output is INVALID and will be rejected by the parser.
  - Before outputting tailored_summary, count its characters internally. If over 220, shorten and recount. Do not output until confirmed ≤ 220.
  - Impact-driven: highlight measurable achievements and core technical skills.
  - Plain text, no LaTeX.

TECHNICAL SKILLS RULES:
  - ALWAYS return ALL skill categories from the resume, reordered to front-load JD matches. Never return null. Output in the JSON key "skills_reordered".
  - Be generous: if experience demonstrates a JD skill not listed in the resume, ADD it with justification. Output in the JSON key "skills_added".

PROJECT SELECTION:
  - The resume contains multiple academic projects. Select exactly 2 most relevant to the JD.
  - Return their 0-based indices in project_selection.selected_indices, ordered by relevance (most relevant first).
  - Only rewrite bullets for selected projects — do NOT include bullet_rewrites for unselected projects.
  - The injector will comment out unselected projects in the LaTeX.

EXPERIENCE / PROJECT REWRITE RULES:
  - STAR METHOD for every bullet: [Action Verb] + [Task/Context] + [Method/Tools] + [Result/Impact].
    Pattern: "[Verb] [what you did] using [tools/skills], resulting in [measurable outcome]"
    Example: "Engineered real-time recommendation pipeline using PySpark and Redis, reducing serving latency by 30%"
    Not every bullet needs all four STAR components. Prioritize: Action > Task > Result > Situation. Never pad with filler.
  - Lead with strong, varied action verbs (Engineered, Deployed, Optimized, Architected, Spearheaded, Orchestrated, Automated, Designed). Do NOT repeat the same verb consecutively.
  - Bridge terminology aggressively toward JD language. If the underlying work is even partially related, use the JD's phrasing.
  - Every rewritten bullet MUST be 23-28 words. Count before outputting. Reject and rewrite if outside this range.

TRUTHFULNESS FLAGS:
  green  = directly supported by resume
  yellow = reasonable inference or reframing — candidate should verify before submitting


OUTPUT JSON SCHEMA:
  {
    "tailored_summary": "string or null — plain text, no LaTeX, ≤ 220 chars, following SUMMARY RULES",
    "project_selection": {
      "selected_indices": [0, 2],
      "rationale": "Why these 2 projects are most relevant to the JD"
    },
    "bullet_rewrites": [
      {
        "section": "experience|projects",
        "entry_index": 0,
        "bullet_index": 0,
        "original": "original bullet text",
        "rewritten": "rewritten bullet (23-28 words, STAR structured, plain text)",
        "keywords_added": ["kw1", "kw2"],
        "rationale": "what changed and why",
        "truthfulness_flag": "green|yellow"
      }
    ],
    "skills_reordered": {
      "Programming Languages": "Python, Java, C++, ...",
      "ML Libraries": "PyTorch, PySpark, ..."
    },
    "skills_added": [
      {
        "skill": "Skill Name",
        "category": "which category",
        "justification": "why candidate can defend this in interview"
      }
    ],
    "confidence": {
      "ats_keyword_coverage": "<float 0.0-1.0> = (JD required skills found in modified resume) / (total JD required skills). COMPUTE this — do not use the example value.",
      "bullets_modified": "<int> = actual count of entries in bullet_rewrites array",
      "yellow_flags": "<int> = count of bullet_rewrites with truthfulness_flag = yellow"
    }
  }
"""


# ── Per-task config dataclasses ───────────────────────────────────────────────

@dataclass
class JDExtractionConfig:
    """Settings for the job-description extraction step."""
    enabled: bool = True
    provider: str = "anthropic"               # active provider name
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 1024
    prompt: str = field(default_factory=lambda: DEFAULT_EXTRACTION_PROMPT)


@dataclass
class TailoringConfig:
    """Settings for the resume-tailoring step."""
    active_provider: str = "anthropic"            # provider with enabled:true in YAML
    anthropic_model: str = "claude-haiku-4-5-20251001"
    anthropic_max_tokens: int = 8192
    openai_model: str = "gpt-4o"
    openai_max_tokens: int = 8192
    prompt: str = field(default_factory=lambda: DEFAULT_TAILORING_PROMPT)

    def model_for(self, provider: str) -> str:
        return self.anthropic_model if provider == "anthropic" else self.openai_model

    def max_tokens_for(self, provider: str) -> int:
        return self.anthropic_max_tokens if provider == "anthropic" else self.openai_max_tokens


@dataclass
class LLMConfig:
    enabled: bool
    jd_extraction: JDExtractionConfig
    resume_tailoring: TailoringConfig


# ── Loader (cached after first call) ─────────────────────────────────────────

_cache: Optional[LLMConfig] = None


def get_config() -> LLMConfig:
    """Return the loaded (and cached) LLM config."""
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def _defaults() -> LLMConfig:
    return LLMConfig(
        enabled=True,
        jd_extraction=JDExtractionConfig(),
        resume_tailoring=TailoringConfig(),
    )


def _parse_provider_list(providers: list, task_max_tokens: int) -> dict:
    """
    Flatten a provider list into a plain dict keyed by provider name.
    Each value is {model, max_tokens, enabled}.
    """
    result = {}
    for entry in providers:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "").strip().lower()
        if not name:
            continue
        result[name] = {
            "model": entry.get("model") or "",
            "max_tokens": entry.get("max_tokens") or task_max_tokens,
            "enabled": entry.get("enabled", False),
        }
    return result


def _load() -> LLMConfig:
    if not _CONFIG_PATH.exists():
        return _defaults()

    try:
        import yaml
    except ImportError:
        print("  ⚠ pyyaml not installed — using built-in LLM defaults (pip install pyyaml)")
        return _defaults()

    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:
        print(f"  ⚠ Could not parse llm_config.yaml: {exc} — using built-in defaults")
        return _defaults()

    if not data.get("enabled", True):
        cfg = _defaults()
        cfg.enabled = False
        return cfg

    tasks = data.get("tasks") or {}

    # ── jd_extraction ──────────────────────────────────────────────────────
    jd_cfg = JDExtractionConfig()
    if "jd_extraction" in tasks:
        t = tasks["jd_extraction"] or {}
        jd_cfg.enabled    = t.get("enabled", jd_cfg.enabled)
        task_max_tokens   = t.get("max_tokens", jd_cfg.max_tokens)
        jd_cfg.max_tokens = task_max_tokens
        raw_prompt        = t.get("prompt") or ""
        jd_cfg.prompt     = raw_prompt.strip() or DEFAULT_EXTRACTION_PROMPT

        providers = _parse_provider_list(t.get("provider") or [], task_max_tokens)

        # Active provider = the one with enabled:true (first match wins)
        active = next(
            (name for name, cfg in providers.items() if cfg["enabled"]),
            None,
        )
        if active and providers[active]["model"]:
            jd_cfg.provider   = active
            jd_cfg.model      = providers[active]["model"]
            jd_cfg.max_tokens = providers[active].get("max_tokens", task_max_tokens)
        elif "provider" in t and isinstance(t["provider"], str):
            # Legacy flat string: provider: anthropic
            jd_cfg.provider = t["provider"]

    # ── resume_tailoring ───────────────────────────────────────────────────
    tail_cfg = TailoringConfig()
    if "resume_tailoring" in tasks:
        t = tasks["resume_tailoring"] or {}
        task_max_tokens   = t.get("max_tokens", tail_cfg.anthropic_max_tokens)
        raw_prompt        = t.get("prompt") or ""
        tail_cfg.prompt   = raw_prompt.strip() or DEFAULT_TAILORING_PROMPT

        providers = _parse_provider_list(t.get("provider") or [], task_max_tokens)

        if "anthropic" in providers and providers["anthropic"]["model"]:
            tail_cfg.anthropic_model      = providers["anthropic"]["model"]
            tail_cfg.anthropic_max_tokens = providers["anthropic"].get("max_tokens", task_max_tokens)

        if "openai" in providers and providers["openai"]["model"]:
            tail_cfg.openai_model      = providers["openai"]["model"]
            tail_cfg.openai_max_tokens = providers["openai"].get("max_tokens", task_max_tokens)

        # Active provider = the one with enabled:true (first match wins)
        active = next(
            (name for name, p in providers.items() if p["enabled"]),
            None,
        )
        if active:
            tail_cfg.active_provider = active

    return LLMConfig(
        enabled=data.get("enabled", True),
        jd_extraction=jd_cfg,
        resume_tailoring=tail_cfg,
    )
