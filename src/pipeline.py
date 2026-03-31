"""
Main pipeline orchestrator.
Wires together parsing → LLM → injection → compilation.
"""

import os
from src.parser import LaTeXParser, JDParser
from src.llm import call_anthropic, call_openai
from src.output.injector import LaTeXInjector
from src.output.compiler import  PDFCompiler
from src.output.manager import OutputManager

class ResumeTailorPipeline:
    """
    Flow:
        1. Parse master .tex  → ResumeJSON + original lines
        2. Parse JD text      → JobDescription
        3. Call LLM           → tailoring JSON
        4. Inject changes     → modified lines
        5. Write .tex + PDF   → output directory
        6. Validate page count
    """

    MODEL_LABELS = {
        "anthropic": "Claude Haiku 4.5",
        "openai": "GPT-4o mini",
    }

    def __init__(self, model: str = "anthropic", output_dir: str = "output"):
        self.model = model
        self.parser = LaTeXParser()
        self.jd_parser = JDParser()
        self.injector = LaTeXInjector()
        self.compiler = PDFCompiler()
        self.output_mgr = OutputManager(base_dir=output_dir)

    def run(self, resume_path: str, company: str, title: str, jd_text: str) -> dict:
        """
        Execute the full pipeline.

        Returns dict:
            tex_path, pdf_path, changes, llm_output, error (if any)
        """
        self._banner(company, title)

        # ① Parse master resume
        print("① Parsing master resume...")
        resume, original_lines = self.parser.parse(resume_path)
        n_entry_bullets = sum(len(e.bullets) for s in resume.sections for e in s.entries)
        n_flat_bullets = sum(len(s.bullets) for s in resume.sections)
        n_skills = sum(len(s.skill_categories) for s in resume.sections)
        print(f"   {len(resume.sections)} sections, {n_entry_bullets + n_flat_bullets} bullets, {n_skills} skill categories")
        if resume.summary:
            print(f"   Summary: \"{resume.summary.strip()[:80]}...\"\n")
        else:
            print()

        # ② Parse job description
        print("② Parsing job description...")
        jd = self.jd_parser.parse(company, title, jd_text)
        print(f"   Required: {', '.join(jd.required_skills[:8])}{'...' if len(jd.required_skills) > 8 else ''}")
        print(f"   Preferred: {', '.join(jd.preferred_skills[:5])}\n")

        # ③ Call LLM
        print(f"③ Calling {self.MODEL_LABELS.get(self.model, self.model)} API...")
        llm_fn = call_anthropic if self.model == "anthropic" else call_openai
        llm_output = llm_fn(resume, jd)
        conf = llm_output.get("confidence", {})
        print(f"   {len(llm_output.get('bullet_rewrites', []))} bullet rewrites")
        print(f"   ATS coverage: {conf.get('ats_keyword_coverage', 'N/A')}")
        print(f"   Truthfulness violations: {conf.get('truthfulness_violations', 'N/A')}\n")

        # ④ Inject changes
        print("④ Injecting changes into LaTeX...")
        modified_lines = self.injector.inject(original_lines, resume, llm_output)

        # ⑤ Write .tex + compile PDF
        print("⑤ Compiling PDF...")
        tex_path, pdf_path, out_dir = self.output_mgr.get_output_paths(company, title)
        self.output_mgr.save_tex(modified_lines, tex_path)

        try:
            compiled = self.compiler.compile(tex_path, out_dir)
            # Rename if compiler output name differs from target
            expected = os.path.join(
                out_dir,
                os.path.splitext(os.path.basename(tex_path))[0] + ".pdf",
            )
            actual_pdf = expected if os.path.exists(expected) else compiled
            if actual_pdf != pdf_path:
                self.output_mgr.rename_pdf(actual_pdf, pdf_path)
        except RuntimeError as e:
            print(f"\n   ⚠ Compilation failed: {e}")
            print(f"   .tex saved to: {tex_path}")
            return self._result(tex_path, None, llm_output, error=str(e))

        # ⑥ Validate page count
        pages = self.compiler.get_page_count(pdf_path)
        if pages > 1:
            print(f"   ⚠ Resume is {pages} pages — consider shortening bullets")

        # Done
        self._footer(tex_path, pdf_path, pages)
        self._print_diff(llm_output)

        return self._result(tex_path, pdf_path, llm_output)

    # ── Output formatting ──

    def _banner(self, company: str, title: str):
        label = self.MODEL_LABELS.get(self.model, self.model)
        print(f"\n{'='*60}")
        print(f"  Resume Tailor Pipeline")
        print(f"  Target: {title} @ {company}")
        print(f"  Model:  {label}")
        print(f"{'='*60}\n")

    def _footer(self, tex_path: str, pdf_path: str, pages: int):
        print(f"\n{'='*60}")
        print(f"  ✓ Tailored resume saved:")
        print(f"    .tex → {tex_path}")
        print(f"    .pdf → {pdf_path}")
        if pages > 0:
            print(f"    Pages: {pages}")
        print(f"{'='*60}\n")

    def _print_diff(self, llm_output: dict):
        print("── Changes Applied ──\n")

        if llm_output.get("tailored_summary"):
            print(f"  Summary: (rewritten)")
            print(f"    → {llm_output['tailored_summary'][:100]}...\n")

        for br in llm_output.get("bullet_rewrites", []):
            icon = {"green": "✓", "yellow": "~", "cannot_bridge": "✗"}.get(
                br.get("truthfulness_flag", "?"), "?"
            )
            print(f"  [{icon}] {br['section']}[{br['entry_index']}] bullet {br['bullet_index']}")
            print(f"      OLD: {br['original'][:90]}...")
            print(f"      NEW: {br['rewritten'][:90]}...")
            print(f"      WHY: {br.get('rationale', 'N/A')}\n")

        if llm_output.get("skills_reordered"):
            skills = llm_output["skills_reordered"]
            if isinstance(skills, dict):
                preview = ", ".join(f"{k}: {v[:30]}..." for k, v in list(skills.items())[:3])
            else:
                preview = str(skills)[:100]
            print(f"  Skills reordered: {preview}\n")

        for sa in llm_output.get("skills_added", []):
            print(f"  Skill added: {sa['skill']} — {sa['justification']}\n")

    def _result(self, tex_path, pdf_path, llm_output, error=None) -> dict:
        changes = {
            "bullets_modified": len(llm_output.get("bullet_rewrites", [])),
            "summary_modified": llm_output.get("tailored_summary") is not None,
            "skills_reordered": llm_output.get("skills_reordered") is not None,
            "skills_added": len(llm_output.get("skills_added", [])),
            "ats_coverage": llm_output.get("confidence", {}).get("ats_keyword_coverage"),
        }
        result = {
            "tex_path": tex_path,
            "pdf_path": pdf_path,
            "changes": changes,
            "llm_output": llm_output,
        }
        if error:
            result["error"] = error
        return result