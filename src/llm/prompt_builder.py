"""
User prompt builder for the resume-tailoring LLM call.

The system prompt (and its default) live in src/config.py and are loaded from
llm_config.yaml at runtime.  This module only handles the per-application user
message that encodes the resume + job description as compact JSON.
"""

import json
import re
from src.models.resume import ResumeJSON
from src.models.job_description import JobDescription

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