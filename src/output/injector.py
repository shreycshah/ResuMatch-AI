"""
LaTeX injector — updated for Shrey's template.

Handles:
  - Multi-line \\resumeItem{...} replacement (uses line_start:line_end range)
  - \\textbf{Category}{: items} skill row replacement
  - Raw-text summary replacement (not inside any \\section{})
  - Flat bullet sections (teaching)
  - LaTeX special character escaping in LLM output
"""

import copy
import re
from typing import Optional
from src.models.resume import ResumeJSON, Section


class LaTeXInjector:

    def inject(self, original_lines: list[str], resume: ResumeJSON, llm_output: dict) -> list[str]:
        """
        Returns a NEW list of lines with all modifications applied.
        Uses reverse line-order for multi-line replacements so that
        line numbers stay valid as we modify earlier lines.
        """
        lines = copy.deepcopy(original_lines)

        self._inject_project_selection(lines, resume, llm_output)
        self._inject_bullets(lines, resume, llm_output)
        self._inject_skills(lines, resume, llm_output)
        self._inject_summary(lines, resume, llm_output)

        return lines

    # ── Project selection (comment out unselected projects) ──

    def _inject_project_selection(self, lines: list[str], resume: ResumeJSON, llm_output: dict):
        """
        Comment out projects NOT selected by the LLM.
        Also removes trailing \\vspace after the last selected project.
        Preserves \\resumeSubHeadingListEnd and other section-level commands.
        """
        selection = llm_output.get("project_selection")
        if not selection:
            return

        selected = set(selection.get("selected_indices", []))
        if not selected:
            return

        projects_section = self._find_section(resume, "projects")
        if not projects_section or not projects_section.entries:
            return

        entries = projects_section.entries

        # ── Compute safe line ranges for each entry ──
        # An entry's commentable range is from its line_start to
        # the next entry's line_start - 1 (or section's content end).
        # We must EXCLUDE section-level commands like \resumeSubHeadingListEnd, \end{...}
        section_closers = {
            r'\resumeSubHeadingListEnd',
            r'\end{document}',
            r'\end{itemize}',
        }

        # Find where the actual project content ends (before section closers)
        content_end = projects_section.line_end
        for i in range(projects_section.line_end, projects_section.line_start, -1):
            stripped = lines[i].strip().replace(' ', '')
            if any(closer.replace(' ', '') in stripped for closer in section_closers):
                content_end = i - 1
            else:
                break

        # Build per-entry line ranges
        entry_ranges = []
        for idx, entry in enumerate(entries):
            start = entry.line_start
            if idx + 1 < len(entries):
                end = entries[idx + 1].line_start - 1
            else:
                end = content_end
            entry_ranges.append((start, end))

        # ── Comment out unselected entries (reverse order) ──
        for idx in range(len(entries) - 1, -1, -1):
            if idx in selected:
                continue

            start, end = entry_ranges[idx]
            for i in range(start, min(end + 1, len(lines))):
                if not lines[i].lstrip().startswith('%'):
                    lines[i] = '% ' + lines[i]

        # ── Remove trailing \vspace after the last selected project ──
        last_selected = max(selected)
        _, last_end = entry_ranges[last_selected]

        # Scan both inside the entry range (backwards from end)
        # and a few lines after it — the \vspace can be in either spot
        scan_start = max(last_end - 3, entry_ranges[last_selected][0])
        scan_end = min(last_end + 3, len(lines) - 1)

        for i in range(scan_end, scan_start - 1, -1):
            stripped = lines[i].strip()
            if r'\vspace' in stripped and not stripped.startswith('%'):
                # Only comment out vspace lines, not \resumeItemListEnd etc.
                lines[i] = '% ' + lines[i]
                break  # only remove the last/closest one

        rationale = selection.get("rationale", "")
        if rationale:
            print(f"   Projects selected: {sorted(selected)} — {rationale}")

    # ── Bullet rewrites (experience, projects, teaching) ──

    def _inject_bullets(self, lines: list[str], resume: ResumeJSON, llm_output: dict):
        # Sort rewrites by line number descending so later replacements don't shift earlier ones
        rewrites = sorted(
            llm_output.get("bullet_rewrites", []),
            key=lambda r: self._get_bullet_line(resume, r),
            reverse=True,
        )

        for rw in rewrites:
            section_name = rw["section"]
            section = self._find_section(resume, section_name)

            if not section:
                print(f"  ⚠ Section '{section_name}' not found, skipping")
                continue

            bullet = self._resolve_bullet(section, rw)
            if not bullet:
                print(f"  ⚠ Could not resolve bullet: {section_name}[{rw.get('entry_index')}][{rw.get('bullet_index')}]")
                continue

            new_text = rw["rewritten"]
            self._replace_bullet_lines(lines, bullet, new_text)

    def _resolve_bullet(self, section: Section, rw: dict):
        """Find the Bullet object matching the rewrite's indices."""
        entry_idx = rw.get("entry_index")
        bullet_idx = rw.get("bullet_index")

        # Flat bullet sections (teaching, achievements)
        if section.bullets and entry_idx is None:
            if bullet_idx is not None and bullet_idx < len(section.bullets):
                return section.bullets[bullet_idx]
            return None

        # Entry-based sections (experience, projects)
        if entry_idx is not None and entry_idx < len(section.entries):
            entry = section.entries[entry_idx]
            if bullet_idx is not None and bullet_idx < len(entry.bullets):
                return entry.bullets[bullet_idx]

        return None

    def _replace_bullet_lines(self, lines: list[str], bullet, new_text: str):
        """
        Replace a bullet that may span multiple lines.
        Reconstructs the \\resumeItem{new text} on the first line,
        removes any continuation lines.
        """
        start, end = bullet.line_start, bullet.line_end
        old_first = lines[start]

        # Escape LaTeX special chars that the LLM may have returned as plain text
        new_text = self._escape_latex(new_text)

        # Detect indentation from original
        indent = len(old_first) - len(old_first.lstrip())
        indent_str = ' ' * indent

        # Reconstruct based on the original wrapper pattern
        if r'\resumeItem{' in old_first:
            new_line = f"{indent_str}\\resumeItem{{{new_text}}}"
        elif re.search(r'\\item\s+', old_first):
            new_line = f"{indent_str}\\item {new_text}"
        else:
            new_line = f"{indent_str}{new_text}"

        # Replace the line range: first line gets new content, rest are removed
        lines[start] = new_line
        if end > start:
            del lines[start + 1:end + 1]

    def _get_bullet_line(self, resume: ResumeJSON, rw: dict) -> int:
        """Get the line number of a bullet for sorting. Returns 0 if not found."""
        section = self._find_section(resume, rw.get("section", ""))
        if not section:
            return 0
        bullet = self._resolve_bullet(section, rw)
        return bullet.line_start if bullet else 0

    # ── Skills reorder ──

    def _inject_skills(self, lines: list[str], resume: ResumeJSON, llm_output: dict):
        """
        Handles two formats from the LLM:

        1. Simple string: "Python, PyTorch, ..."
           → replaces items in the first skill row

        2. Dict of categories: {"Programming Languages": "Python, Java", ...}
           → replaces each category row individually
        """
        skills_data = llm_output.get("skills_reordered")
        if not skills_data:
            return

        section = self._find_section(resume, "skills")
        if not section or not section.skill_categories:
            return

        if isinstance(skills_data, dict):
            for cat in section.skill_categories:
                if cat.category in skills_data:
                    old_line = lines[cat.line_number]
                    m = re.search(
                        r'(\\textbf\{' + re.escape(cat.category) + r'\}\s*\{:\s*)(.+?)(\}\s*\\\\?\s*)$',
                        old_line,
                    )
                    if m:
                        lines[cat.line_number] = m.group(1) + self._escape_latex(skills_data[cat.category]) + m.group(3)
        elif isinstance(skills_data, str):
            first_cat = section.skill_categories[0]
            old_line = lines[first_cat.line_number]
            m = re.search(r'(\\textbf\{[^}]+\}\s*\{:\s*)(.+?)(\}\s*\\\\?\s*)$', old_line)
            if m:
                lines[first_cat.line_number] = m.group(1) + self._escape_latex(skills_data) + m.group(3)

    # ── Summary rewrite ──

    def _inject_summary(self, lines: list[str], resume: ResumeJSON, llm_output: dict):
        new_summary = llm_output.get("tailored_summary")
        if not new_summary or resume.summary_line_start == 0:
            return

        new_summary = self._escape_latex(new_summary)
        for i in range(resume.summary_line_start, resume.summary_line_end + 1):
            line = lines[i].strip()
            if not line or line.startswith('%') or line.startswith(r'\vspace'):
                continue
            lines[i] = new_summary
            return

    # ── LaTeX escaping ──

    def _escape_latex(self, text: str) -> str:
        """
        Escape LaTeX special characters in LLM output.
        The LLM returns plain text but sometimes includes raw &, %, #, $, _
        which break LaTeX compilation.
        """
        # Escape &, %, #, $ — protect already-escaped instances
        for char, escaped in [('&', '\\&'), ('%', '\\%'), ('#', '\\#'), ('$', '\\$')]:
            # Temporarily mark already-escaped chars
            placeholder = '\x00SAFE\x00'
            text = text.replace(escaped, placeholder)
            text = text.replace(char, escaped)
            text = text.replace(placeholder, escaped)

        # Underscore: escape unless inside a URL or already escaped
        result = []
        for i, ch in enumerate(text):
            if ch == '_':
                prev = text[i - 1] if i > 0 else ''
                if prev == '\\':
                    result.append('_')          # already escaped
                elif prev in ('/', '.', ':'):
                    result.append('_')          # likely inside a URL
                else:
                    result.append('\\_')
            else:
                result.append(ch)
        text = ''.join(result)

        # Safety net: ensure braces are balanced
        open_count = text.count('{') - text.count('}')
        if open_count > 0:
            text += '}' * open_count
        elif open_count < 0:
            text = '{' * abs(open_count) + text

        return text

    # ── Helpers ──

    def _find_section(self, resume: ResumeJSON, name: str) -> Optional[Section]:
        for s in resume.sections:
            if s.name == name:
                return s
        return None

    def _fuzzy_replace(self, line: str, new_text: str) -> str:
        """Last resort: replace everything inside the outermost braces."""
        m = re.search(r'(\\resumeItem\{)(.+?)(\}\s*)$', line)
        if m:
            return m.group(1) + new_text + m.group(3)
        m = re.search(r'(\\item\s+)(.+)$', line)
        if m:
            return m.group(1) + new_text
        return line