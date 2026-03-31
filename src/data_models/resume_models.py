"""
Data models used across the pipeline.
All structured representations of resumes, JDs, and LLM output.
"""

from dataclasses import dataclass, field


@dataclass
class Bullet:
    text: str
    line_start: int                               # first line of this \resumeItem (may span multiple lines)
    line_end: int = 0                              # last line (same as line_start if single-line)
    metrics: list = field(default_factory=list)
    raw_latex: str = ""                            # the full original LaTeX lines (for safe reconstruction)


@dataclass
class SkillCategory:
    """One row in the skills section, e.g. 'ML Libraries': 'Pandas, PySpark, ...'"""
    category: str       # e.g. "Programming Languages"
    items: str          # e.g. "Python, Java, C++, C, R"
    line_number: int = 0


@dataclass
class ExperienceEntry:
    company: str
    title: str
    location: str
    dates: str
    bullets: list = field(default_factory=list)    # list[Bullet]
    line_start: int = 0
    line_end: int = 0


@dataclass
class ProjectEntry:
    name: str
    dates: str
    bullets: list = field(default_factory=list)    # list[Bullet]
    line_start: int = 0
    line_end: int = 0


@dataclass
class Section:
    name: str           # canonical: "summary", "experience", "skills", "education", "projects", "patents", "teaching"
    raw_name: str       # original name from .tex, e.g. "PROFESSIONAL EXPERIENCE"
    content: str        # raw text content of the full section
    line_start: int = 0
    line_end: int = 0
    entries: list = field(default_factory=list)          # list[ExperienceEntry | ProjectEntry]
    skill_categories: list = field(default_factory=list) # list[SkillCategory] (only for skills section)
    bullets: list = field(default_factory=list)           # list[Bullet] (for flat sections like teaching)


@dataclass
class ResumeJSON:
    preamble: str                                  # everything before \begin{document}
    postamble: str                                 # \end{document} and after
    header: str                                    # name + contact line block
    header_line_start: int = 0
    header_line_end: int = 0
    summary: str = ""                              # raw text summary (between header and first \section)
    summary_line_start: int = 0
    summary_line_end: int = 0
    sections: list = field(default_factory=list)   # list[Section]