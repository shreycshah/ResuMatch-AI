"""
PDF compiler.
Auto-detects available LaTeX compiler (tectonic > pdflatex > xelatex > lualatex)
and compiles .tex → .pdf with timeout and error handling.

Tectonic fix: copies glyphtounicode.tex into the output directory so tectonic
can find it (it doesn't ship this file in its bundle). If the file can't be
sourced, falls back to stripping the \\input{glyphtounicode} line.
"""

import os
import re
import shutil
import subprocess
import urllib.request

# URL to download glyphtounicode.tex if not found locally
GLYPHTOUNICODE_URL = (
    "https://raw.githubusercontent.com/latex3/unicode-data/main/glyphtounicode.tex"
)

# Lines to strip only as a last resort
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

        # Ensure tectonic can find glyphtounicode.tex
        if self.compiler == 'tectonic':
            self._ensure_glyphtounicode(tex_path, output_dir)

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

        # Clean up pdflatex build artifacts (.aux, .log, .out, .fls, .fdb_latexmk, .synctex.gz)
        self._cleanup_build_artifacts(output_dir, basename)

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
            return ['tectonic', '-o', output_dir, tex_path]
        else:
            return [
                self.compiler,
                f'-output-directory={output_dir}',
                '-interaction=nonstopmode',
                tex_path,
            ]

    def _ensure_glyphtounicode(self, tex_path: str, output_dir: str):
        """
        Make glyphtounicode.tex available to tectonic.

        Strategy:
        1. Check if it already exists next to the .tex file → done
        2. Check if it exists in the project root → copy it
        3. Download it from GitHub → save next to the .tex file
        4. If all fail → strip the \\input line as fallback
        """
        tex_dir = os.path.dirname(tex_path)
        target = os.path.join(tex_dir, "glyphtounicode.tex")

        # Already in the output directory
        if os.path.exists(target):
            return

        # Check project root (one level up from output dir, or cwd)
        for search_dir in [os.getcwd(), os.path.dirname(output_dir)]:
            candidate = os.path.join(search_dir, "glyphtounicode.tex")
            if os.path.exists(candidate):
                shutil.copy2(candidate, target)
                print(f"   Copied glyphtounicode.tex from {candidate}")
                return

        # Download from GitHub
        try:
            print(f"   Downloading glyphtounicode.tex...")
            urllib.request.urlretrieve(GLYPHTOUNICODE_URL, target)
            print(f"   Saved to {target}")
            return
        except Exception as e:
            print(f"   ⚠ Could not download glyphtounicode.tex: {e}")

        # Last resort: strip the incompatible lines
        print(f"   ⚠ Stripping \\input{{glyphtounicode}} as fallback")
        self._strip_tectonic_incompatible(tex_path)

    def _strip_tectonic_incompatible(self, tex_path: str):
        """Remove lines from .tex that are incompatible with tectonic."""
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

    def _cleanup_build_artifacts(self, output_dir: str, basename: str):
        """Remove pdflatex build artifacts, keeping only .tex and .pdf."""
        junk_extensions = ['.aux', '.log', '.out', '.fls', '.fdb_latexmk', '.synctex.gz', '.nav', '.snm', '.toc']
        for ext in junk_extensions:
            path = os.path.join(output_dir, basename + ext)
            if os.path.exists(path):
                os.remove(path)