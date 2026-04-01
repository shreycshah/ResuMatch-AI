"""
Data models used across the pipeline.
All structured representations of resumes, JDs, and LLM output.
"""

from dataclasses import dataclass, field

@dataclass
class JobDescription:
    company: str
    title: str
    raw_text: str
    required_skills: list = field(default_factory=list)
    preferred_skills: list = field(default_factory=list)
    key_phrases: list = field(default_factory=list)