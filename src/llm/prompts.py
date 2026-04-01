"""
Prompt definitions and builder.
The SYSTEM_PROMPT is identical across all runs → cached by Anthropic's API.
The user prompt is built fresh per application from resume + JD JSON.

Updated to handle:
  - Standalone summary (not inside a \\section{})
  - Per-category skill rows
  - Flat bullet sections (teaching)
  - Multi-line bullets serialized as single strings
"""

import json
import re
from src.data_models.resume_models import ResumeJSON
from src.data_models.jd_model import JobDescription

# ─────────────────────────────────────────────
# SYSTEM PROMPT (cached across all calls)
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are an ATS resume optimization specialist. Given a resume and job description,
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

# ─────────────────────────────────────────────
# USER PROMPT BUILDER
# ─────────────────────────────────────────────

def build_user_prompt(resume: ResumeJSON, jd: JobDescription) -> str:
    """Build the per-application user message. Compact JSON to minimize tokens."""

    resume_data = {}

    # Summary
    if resume.summary:
        resume_data["summary"] = _strip_all_latex(resume.summary)

    # Sections
    resume_data["sections"] = []
    for section in resume.sections:
        s = {"name": section.name}

        if section.entries:
            s["entries"] = []
            for entry in section.entries:
                e = {"bullets": [b.text for b in entry.bullets]}
                # ExperienceEntry has company/title/location/dates
                if hasattr(entry, 'company'):
                    e["company"] = entry.company
                    e["title"] = getattr(entry, 'title', '')
                # ProjectEntry has name/dates
                if hasattr(entry, 'name') and not hasattr(entry, 'company'):
                    e["name"] = entry.name
                e["dates"] = entry.dates
                s["entries"].append(e)

        elif section.skill_categories:
            s["skill_categories"] = {
                cat.category: cat.items
                for cat in section.skill_categories
            }

        elif section.bullets:
            s["bullets"] = [b.text for b in section.bullets]

        else:
            s["content"] = _strip_all_latex(section.content)

        resume_data["sections"].append(s)

    jd_data = {
        "company": jd.company,
        "title": jd.title,
        "required_skills": jd.required_skills,
        "preferred_skills": jd.preferred_skills,
        "key_phrases": jd.key_phrases,
        "raw_description": jd.raw_text[:3000],
    }

    return json.dumps(
        {"resume": resume_data, "job_description": jd_data},
        indent=None,
        ensure_ascii=False,
    )


def _strip_all_latex(text: str) -> str:
    """Aggressively strip LaTeX for LLM consumption."""
    text = re.sub(r'\\section\{[^}]*\}', '', text)
    text = re.sub(r'\\subsection\{[^}]*\}', '', text)
    text = re.sub(r'\\begin\{[^}]*\}', '', text)
    text = re.sub(r'\\end\{[^}]*\}', '', text)
    text = re.sub(r'\\resumeSubheading\{[^}]*\}\{[^}]*\}\{[^}]*\}\{[^}]*\}', '', text)
    text = re.sub(r'\\resumeItem\{(.+?)\}', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\\item\s+', '', text)
    text = re.sub(r'\\textbf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\textit\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\href\{[^}]*\}\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\vspace\{[^}]*\}', '', text)
    text = re.sub(r'\$\|?\$', '', text)
    text = re.sub(r'\\[a-zA-Z]+\*?\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+\*?', '', text)
    text = re.sub(r'[{}]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()