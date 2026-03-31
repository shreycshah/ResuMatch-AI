"""
PDF compiler.
Auto-detects available LaTeX compiler (tectonic > pdflatex > xelatex > lualatex)
and compiles .tex → .pdf with timeout and error handling.

Tectonic-specific: strips \\input{glyphtounicode} and \\pdfgentounicode=1 from
the .tex before compiling, since tectonic's XeTeX backend handles Unicode natively
and doesn't ship glyphtounicode.tex.
"""

import os
import re
import shutil
import subprocess


# Lines that break tectonic but are only needed for pdflatex ATS compatibility
TECTONIC_STRIP_PATTERNS = [
    re.compile(r'^\s*\\input\{glyphtounicode\}\s*$'),
    re.compile(r'^\s*\\pdfgentounicode\s*=\s*1\s*$'),
]


class PDFCompiler:

    def __init__(self):
        self.compiler = self._detect_compiler()

    def compile(self, tex_path: str, output_dir: str) -> str:
        """
        Compile .tex to .pdf.
        Returns absolute path to the output PDF.
        Raises RuntimeError on failure or timeout.
        """
        tex_path = os.path.abspath(tex_path)
        output_dir = os.path.abspath(output_dir)

        # If using tectonic, strip incompatible lines before compiling
        if self.compiler == 'tectonic':
            self._strip_tectonic_incompatible(tex_path)

        cmd = self._build_command(tex_path, output_dir)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise RuntimeError("LaTeX compilation timed out (60s)")

        basename = os.path.splitext(os.path.basename(tex_path))[0]
        pdf_path = os.path.join(output_dir, f"{basename}.pdf")

        if not os.path.exists(pdf_path):
            err = result.stderr or result.stdout or "Unknown compilation error"
            raise RuntimeError(
                f"LaTeX compilation failed ({self.compiler}).\n"
                f"Command: {' '.join(cmd)}\n"
                f"Output:\n{err[:2000]}"
            )

        return pdf_path

    def get_page_count(self, pdf_path: str) -> int:
        """Return page count of a PDF, or -1 if unknown."""
        if shutil.which('pdfinfo'):
            result = subprocess.run(
                ['pdfinfo', pdf_path], capture_output=True, text=True,
            )
            m = re.search(r'Pages:\s+(\d+)', result.stdout)
            if m:
                return int(m.group(1))

        # Fallback: naive byte search
        try:
            with open(pdf_path, 'rb') as f:
                data = f.read()
            return data.count(b'/Type /Page') - data.count(b'/Type /Pages')
        except Exception:
            return -1

    # ── Private ──

    def _detect_compiler(self) -> str:
        for cmd in ['pdflatex', 'tectonic', 'xelatex', 'lualatex']:
            if shutil.which(cmd):
                return cmd
        raise EnvironmentError(
            "No LaTeX compiler found. Install one of:\n"
            "  macOS:   brew install tectonic\n"
            "  Ubuntu:  sudo apt install texlive-latex-base\n"
            "  Docker:  docker pull texlive/texlive"
        )

    def _build_command(self, tex_path: str, output_dir: str) -> list[str]:
        if self.compiler == 'tectonic':
            return [
                'tectonic',
                '-o', output_dir,
                '--untrusted',              # sandbox mode
                tex_path,
            ]
        else:
            return [
                self.compiler,
                f'-output-directory={output_dir}',
                '-interaction=nonstopmode',
                tex_path,
            ]

    def _strip_tectonic_incompatible(self, tex_path: str):
        """
        Remove lines from the .tex file that are incompatible with tectonic.
        These are pdflatex-specific commands for ATS Unicode support;
        tectonic handles Unicode natively via its XeTeX backend.
        """
        with open(tex_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        changed = False
        filtered = []
        for line in lines:
            if any(pat.match(line) for pat in TECTONIC_STRIP_PATTERNS):
                filtered.append(f'% [auto-stripped for tectonic] {line}')
                changed = True
            else:
                filtered.append(line)

        if changed:
            with open(tex_path, 'w', encoding='utf-8') as f:
                f.writelines(filtered)