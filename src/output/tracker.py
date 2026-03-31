"""
Application tracker.
Appends a row to a CSV file for every pipeline run, logging
company, role, model used, changes made, file paths, and per-bullet rationale.

CSV is created on first run and appended to on subsequent runs.
"""

import csv
import os
from datetime import datetime


CSV_HEADERS = [
    "timestamp",
    "company",
    "job_title",
    "model",
    "pdf_path",
    "tex_path",
    "summary_modified",
    "bullets_modified",
    "skills_reordered",
    "skills_added",
    "ats_keyword_coverage",
    "truthfulness_violations",
    "bullet_changes",       # condensed: "section[entry].bullet: OLD → NEW (rationale)"
    "skills_added_detail",  # condensed: "Skill Name (category): justification"
    "new_summary",
    "status",               # success / compilation_failed / llm_error
]


class ApplicationTracker:

    def __init__(self, csv_path: str = "output/applications_log.csv"):
        self.csv_path = csv_path

    def log(
        self,
        company: str,
        title: str,
        model: str,
        result: dict,
    ):
        """
        Append one row to the tracker CSV.

        Args:
            company: target company name
            title: target job title
            model: "anthropic" or "openai"
            result: dict returned by ResumeTailorPipeline.run()
        """
        # Ensure directory exists
        csv_dir = os.path.dirname(self.csv_path)
        if csv_dir:
            os.makedirs(csv_dir, exist_ok=True)

        file_exists = os.path.exists(self.csv_path)

        llm_output = result.get("llm_output", {})
        confidence = llm_output.get("confidence", {})
        changes = result.get("changes", {})

        # Build condensed bullet change log
        bullet_log = self._format_bullet_changes(llm_output.get("bullet_rewrites", []))

        # Build condensed skills added log
        skills_log = self._format_skills_added(llm_output.get("skills_added", []))

        # Determine status
        if result.get("error"):
            status = "compilation_failed"
        elif result.get("pdf_path"):
            status = "success"
        else:
            status = "unknown_error"

        row = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "company": company,
            "job_title": title,
            "model": "Claude Haiku 4.5" if model == "anthropic" else "GPT-4.1 mini",
            "pdf_path": result.get("pdf_path", "N/A"),
            "tex_path": result.get("tex_path", "N/A"),
            "summary_modified": changes.get("summary_modified", False),
            "bullets_modified": changes.get("bullets_modified", 0),
            "skills_reordered": changes.get("skills_reordered", False),
            "skills_added": changes.get("skills_added", 0),
            "ats_keyword_coverage": confidence.get("ats_keyword_coverage", "N/A"),
            "truthfulness_violations": confidence.get("truthfulness_violations", 0),
            "bullet_changes": bullet_log,
            "skills_added_detail": skills_log,
            "new_summary": llm_output.get("tailored_summary", "N/A"),
            "status": status,
        }

        with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

        print(f"   📋 Logged to {self.csv_path}")

    # ── Formatters ──

    def _format_bullet_changes(self, rewrites: list) -> str:
        """
        Condense bullet rewrites into a readable single-cell string.
        Format: section[entry_idx].bullet_idx | flag | OLD → NEW | rationale
        """
        if not rewrites:
            return "No changes"

        parts = []
        for rw in rewrites:
            section = rw.get("section", "?")
            entry = rw.get("entry_index", "?")
            bullet = rw.get("bullet_index", "?")
            flag = rw.get("truthfulness_flag", "?")
            old = rw.get("original", "")[:60]
            new = rw.get("rewritten", "")[:60]
            rationale = rw.get("rationale", "N/A")

            loc = f"{section}[{entry}].{bullet}"
            parts.append(f"{loc} [{flag}]: \"{old}...\" → \"{new}...\" ({rationale})")

        return " || ".join(parts)

    def _format_skills_added(self, skills: list) -> str:
        """Condense skills_added into a single-cell string."""
        if not skills:
            return "None"

        parts = []
        for s in skills:
            name = s.get("skill", "?")
            cat = s.get("category", "?")
            why = s.get("justification", "N/A")
            parts.append(f"{name} ({cat}): {why}")

        return " || ".join(parts)