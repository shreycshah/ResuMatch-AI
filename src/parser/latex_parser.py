"""
LaTeX resume parser — tailored for Shrey's Jake-style template.

Handles:
  - Raw-text summary between header and first \\section{}
  - ALL-CAPS section names (PROFESSIONAL EXPERIENCE, TECHNICAL SKILLS, etc.)
  - Multi-line \\resumeItem{...} spanning 2-3 source lines
  - \\textbf{category}{: items} skill rows
  - \\resumeProjectHeading for patents/projects
  - Flat bullet sections (TEACHING EXPERIENCE) with no subheading
  - Commented-out lines (% ...) are ignored
"""

import re
from src.data_models.resume_models import (
    Bullet, SkillCategory, ExperienceEntry, ProjectEntry,
    Section, ResumeJSON,
)


class LaTeXParser:
    # ── Regex patterns ──

    SECTION_RE = re.compile(r'\\section\{([^}]+)\}', re.IGNORECASE)

    # \resumeSubheading{company}{location}{title}{dates}
    # Handles multi-line: each { } group may be on the same or next line
    SUBHEADING_RE = re.compile(
        r'\\resumeSubheading\s*'
        r'\{([^}]*)\}'  # 1: company / school
        r'\s*\{([^}]*)\}'  # 2: location / dates-right
        r'\s*\{([^}]*)\}'  # 3: title / degree
        r'\s*\{([^}]*)\}',  # 4: dates / GPA
        re.DOTALL,
    )

    # \resumeProjectHeading{name}{dates}
    PROJECT_HEADING_RE = re.compile(
        r'\\resumeProjectHeading\s*'
        r'\{(.*?)\}'  # 1: project name (may contain \textbf, \href, etc.)
        r'\s*\{([^}]*)\}',  # 2: dates
        re.DOTALL,
    )

    # \textbf{Category}{: items}  — in the skills section
    SKILL_ROW_RE = re.compile(
        r'\\textbf\{([^}]+)\}\s*\{:\s*([^}]+)\}',
    )

    # Metrics in bullet text
    METRIC_RE = re.compile(r'(\d+[\d,.]*[%xX]?|\$[\d,.]+[MBKmk]?)')

    # ── Section name normalization ──

    SECTION_NAME_MAP = {
        'technical skills': 'skills',
        'skills': 'skills',
        'education': 'education',
        'experience': 'experience',
        'professional experience': 'experience',
        'work experience': 'experience',
        'research experience': 'experience',
        'granted patents': 'patents',
        'patents': 'patents',
        'academic projects': 'projects',
        'projects': 'projects',
        'publications': 'publications',
        'summary': 'summary',
        'objective': 'summary',
        'teaching experience': 'teaching',
        'teaching': 'teaching',
        'leadership & achievements': 'achievements',
    }

    ENTRY_SECTIONS = frozenset({'experience', 'projects', 'patents'})
    FLAT_BULLET_SECTIONS = frozenset({'teaching', 'achievements'})

    # ── Public API ──

    def parse(self, tex_path: str) -> tuple[ResumeJSON, list[str]]:
        with open(tex_path, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')
        resume = ResumeJSON(preamble="", postamble="", header="")

        doc_start = self._find_line(lines, r'\begin{document}')
        doc_end = self._find_line(lines, r'\end{document}', reverse=True)

        resume.preamble = '\n'.join(lines[:doc_start + 1])
        resume.postamble = '\n'.join(lines[doc_end:])

        section_starts = self._find_sections(lines, doc_start + 1, doc_end)

        # ── Header + Summary (between \begin{document} and first \section) ──
        if section_starts:
            first_section_line = section_starts[0][0]
            pre_section = lines[doc_start + 1:first_section_line]
            header_end, summary_start = self._split_header_summary(
                pre_section, doc_start + 1
            )
            resume.header = '\n'.join(lines[doc_start + 1:header_end + 1])
            resume.header_line_start = doc_start + 1
            resume.header_line_end = header_end

            if summary_start is not None:
                resume.summary = '\n'.join(lines[summary_start:first_section_line])
                resume.summary_line_start = summary_start
                resume.summary_line_end = first_section_line - 1
        else:
            resume.header = '\n'.join(lines[doc_start + 1:doc_end])
            resume.header_line_start = doc_start + 1
            resume.header_line_end = doc_end - 1

        # ── Parse each section ──
        for idx, (start_line, raw_name) in enumerate(section_starts):
            end_line = (
                section_starts[idx + 1][0] - 1
                if idx + 1 < len(section_starts)
                else doc_end - 1
            )

            canonical = self._normalize_name(raw_name)

            section = Section(
                name=canonical,
                raw_name=raw_name,
                content='\n'.join(lines[start_line:end_line + 1]),
                line_start=start_line,
                line_end=end_line,
            )

            if canonical in self.ENTRY_SECTIONS:
                section.entries = self._parse_entries(lines, start_line, end_line, canonical)
            elif canonical == 'skills':
                section.skill_categories = self._parse_skills(lines, start_line, end_line)
            elif canonical in self.FLAT_BULLET_SECTIONS:
                section.bullets = self._parse_flat_bullets(lines, start_line, end_line)

            resume.sections.append(section)

        return resume, lines

    # ── Header / Summary splitter ──

    def _split_header_summary(self, pre_lines: list[str], offset: int) -> tuple[int, int | None]:
        """
        The header is the \\begin{center}...\\end{center} block.
        The summary is any plain text after \\end{center} and before
        the first \\section{}.

        Returns (header_end_line, summary_start_line_or_None).
        """
        center_end = None
        for i, line in enumerate(pre_lines):
            if r'\end{center}' in line:
                center_end = offset + i
                break

        if center_end is None:
            # No center block — treat everything as header
            return offset + len(pre_lines) - 1, None

        # Look for first non-blank, non-vspace line after \end{center}
        summary_start = None
        for i in range(center_end - offset + 1, len(pre_lines)):
            line = pre_lines[i].strip()
            if line and not line.startswith('%') and not line.startswith(r'\vspace'):
                summary_start = offset + i
                break

        return center_end, summary_start

    # ── Section finding ──

    def _find_line(self, lines: list[str], marker: str, reverse: bool = False) -> int:
        rng = range(len(lines) - 1, -1, -1) if reverse else range(len(lines))
        for i in rng:
            if marker in lines[i]:
                return i
        raise ValueError(f"Could not find '{marker}' in the .tex file")

    def _find_sections(self, lines: list[str], start: int, end: int) -> list[tuple[int, str]]:
        results = []
        for i in range(start, end):
            # Skip commented lines
            if lines[i].lstrip().startswith('%'):
                continue
            m = self.SECTION_RE.search(lines[i])
            if m:
                results.append((i, m.group(1).strip()))
        return results

    def _normalize_name(self, name: str) -> str:
        return self.SECTION_NAME_MAP.get(name.lower(), name.lower())

    # ── Entry parsing (experience, projects, patents) ──

    def _parse_entries(self, lines: list[str], sec_start: int, sec_end: int, section_type: str) -> list:
        entries = []
        current = None

        i = sec_start + 1
        while i <= sec_end:
            line = lines[i]

            # Skip comments
            if line.lstrip().startswith('%'):
                i += 1
                continue

            # ── \resumeSubheading (experience, education) ──
            # May span multiple lines — join up to 4 lines to match
            joined = ' '.join(lines[i:min(i + 4, sec_end + 1)])
            sub_m = self.SUBHEADING_RE.search(joined)
            if sub_m and r'\resumeSubheading' in line:
                if current:
                    current.line_end = i - 1
                    entries.append(current)
                current = ExperienceEntry(
                    company=self._strip_latex(sub_m.group(1)),
                    location=self._strip_latex(sub_m.group(2)),
                    title=self._strip_latex(sub_m.group(3)),
                    dates=self._strip_latex(sub_m.group(4)),
                    line_start=i,
                )
                i += 1
                continue

            # ── \resumeProjectHeading (projects, patents) ──
            proj_m = self.PROJECT_HEADING_RE.search(joined)
            if proj_m and r'\resumeProjectHeading' in line:
                if current:
                    current.line_end = i - 1
                    entries.append(current)
                current = ProjectEntry(
                    name=self._strip_latex(proj_m.group(1)),
                    dates=self._strip_latex(proj_m.group(2)),
                    line_start=i,
                )
                i += 1
                continue

            # ── Bullet points (\resumeItem{...} — may span multiple lines) ──
            if current is not None:
                bullet = self._try_parse_bullet(lines, i, sec_end)
                if bullet:
                    current.bullets.append(bullet)
                    i = bullet.line_end + 1
                    continue

            i += 1

        if current:
            current.line_end = sec_end
            entries.append(current)

        return entries

    # ── Flat bullet sections (teaching, achievements) ──

    def _parse_flat_bullets(self, lines: list[str], sec_start: int, sec_end: int) -> list[Bullet]:
        bullets = []
        i = sec_start + 1
        while i <= sec_end:
            if lines[i].lstrip().startswith('%'):
                i += 1
                continue
            bullet = self._try_parse_bullet(lines, i, sec_end)
            if bullet:
                bullets.append(bullet)
                i = bullet.line_end + 1
            else:
                i += 1
        return bullets

    # ── Multi-line bullet parser ──

    def _try_parse_bullet(self, lines: list[str], start: int, sec_end: int) -> Bullet | None:
        """
        Detect and parse a \\resumeItem{...} that may span multiple lines.
        Returns a Bullet with correct line_start/line_end, or None.
        """
        line = lines[start]

        # Must start with \resumeItem{ (possibly indented)
        if r'\resumeItem{' not in line and not re.search(r'\\item\s+', line):
            return None

        # ── \resumeItem{...} (may span lines) ──
        if r'\resumeItem{' in line:
            # Find the matching closing brace by counting braces
            combined = line
            end = start
            brace_count = 0
            found_open = False

            for ci, ch in enumerate(combined):
                if ch == '{' and combined[max(0, ci - 11):ci + 1].endswith(r'\resumeItem{'):
                    found_open = True
                if found_open:
                    if ch == '{':
                        brace_count += 1
                    elif ch == '}':
                        brace_count -= 1

            # If braces aren't balanced, keep joining lines
            while brace_count > 0 and end < sec_end:
                end += 1
                next_line = lines[end]
                combined += '\n' + next_line
                for ch in next_line:
                    if ch == '{':
                        brace_count += 1
                    elif ch == '}':
                        brace_count -= 1
                    if brace_count == 0:
                        break

            # Extract text content
            m = re.search(r'\\resumeItem\{(.+)\}', combined, re.DOTALL)
            if m:
                text = self._strip_latex(m.group(1).strip())
                return Bullet(
                    text=text,
                    line_start=start,
                    line_end=end,
                    metrics=self.METRIC_RE.findall(text),
                    raw_latex=combined,
                )

        # ── \item ... (single line) ──
        item_m = re.search(r'\\item\s+(.+)$', line)
        if item_m:
            text = self._strip_latex(item_m.group(1))
            return Bullet(
                text=text,
                line_start=start,
                line_end=start,
                metrics=self.METRIC_RE.findall(text),
                raw_latex=line,
            )

        return None

    # ── Skills section parser ──

    def _parse_skills(self, lines: list[str], sec_start: int, sec_end: int) -> list[SkillCategory]:
        categories = []
        for i in range(sec_start, sec_end + 1):
            if lines[i].lstrip().startswith('%'):
                continue
            m = self.SKILL_ROW_RE.search(lines[i])
            if m:
                categories.append(SkillCategory(
                    category=m.group(1).strip(),
                    items=m.group(2).strip(),
                    line_number=i,
                ))
        return categories

    # ── LaTeX stripping ──

    def _strip_latex(self, text: str) -> str:
        """Remove LaTeX commands, preserving readable text."""
        text = re.sub(r'\\textbf\{([^}]*)\}', r'\1', text)
        text = re.sub(r'\\textit\{([^}]*)\}', r'\1', text)
        text = re.sub(r'\\emph\{([^}]*)\}', r'\1', text)
        text = re.sub(r'\\underline\{([^}]*)\}', r'\1', text)
        text = re.sub(r'\\href\{[^}]*\}\{([^}]*)\}', r'\1', text)
        text = re.sub(r'\\scshape\s*', '', text)
        text = re.sub(r'\$\|?\$', '', text)  # $|$ separators
        text = re.sub(r'\\vspace\{[^}]*\}', '', text)
        text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
        text = re.sub(r'\\[a-zA-Z]+\*?', '', text)
        text = re.sub(r'[{}]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()