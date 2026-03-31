"""
resume_tailor — Automated resume tailoring pipeline.

Usage:
    from resume_tailor.pipeline import ResumeTailorPipeline

    pipeline = ResumeTailorPipeline(model="anthropic")
    result = pipeline.run("master.tex", "Netflix", "ML Engineer", jd_text)
"""

from src.pipeline import ResumeTailorPipeline

__all__ = ["ResumeTailorPipeline"]
__version__ = "0.1.0"