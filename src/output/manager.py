"""
Output manager.
Handles directory creation, file naming convention, and deduplication.

Naming:  Resume_{CompanyFirstWord}_{Job_Title_Underscored}.pdf
Dir:     {base_dir}/{YYYY-MM-DD}/
Dedup:   _2, _3, ... suffix if file already exists (never overwrites).
"""

import os
import re
import shutil
from datetime import datetime


class OutputManager:

    def __init__(self, base_dir: str = "output"):
        self.base_dir = base_dir

    def get_output_paths(self, company: str, title: str) -> tuple[str, str, str]:
        """
        Returns (tex_path, pdf_path, output_dir).
        Creates the date directory if it doesn't exist.
        Auto-deduplicates filenames.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        day_dir = os.path.join(self.base_dir, today)
        os.makedirs(day_dir, exist_ok=True)

        base_name = self._build_filename(company, title)

        tex_path = os.path.join(day_dir, f"{base_name}.tex")
        pdf_path = os.path.join(day_dir, f"{base_name}.pdf")

        counter = 2
        while os.path.exists(tex_path) or os.path.exists(pdf_path):
            tex_path = os.path.join(day_dir, f"{base_name}_{counter}.tex")
            pdf_path = os.path.join(day_dir, f"{base_name}_{counter}.pdf")
            counter += 1

        return tex_path, pdf_path, day_dir

    def save_tex(self, lines: list[str], tex_path: str) -> str:
        """Write modified .tex lines to disk."""
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return tex_path

    def rename_pdf(self, source: str, target: str):
        """Move/rename compiled PDF to the target filename."""
        if source != target:
            shutil.move(source, target)

    # ── Private ──

    def _build_filename(self, company: str, title: str) -> str:
        # Company: first word only if multi-word
        parts = company.strip().split()
        company_slug = re.sub(r'[^a-zA-Z0-9]', '', parts[0] if parts else "Unknown")

        # Title: underscores for spaces, strip special chars
        title_slug = re.sub(r'[^a-zA-Z0-9\s]', '', title.strip())
        title_slug = '_'.join(title_slug.split())

        return f"Resume_{company_slug}_{title_slug}"