# ResuMatch-AI

An automated resume tailoring and ATS optimization pipeline. Takes a master LaTeX resume and a job description, uses an LLM to tailor content, injects changes back into LaTeX, and compiles a polished PDF.

---

## How It Works

1. **Parse** your master `.tex` resume into structured JSON (sections, bullets, skills, summary)
2. **Extract** required skills, preferred skills, and key phrases from the job description via LLM (falls back to regex heuristics if disabled)
3. **Tailor** via LLM — rewrites bullets using STAR methodology, reorders skills, selects the most relevant projects, and optimizes the summary for ATS
4. **Inject** changes back into the original `.tex` using line-number metadata (surgical replacement, no formatting breakage)
5. **Compile** to PDF via `pdflatex` / `tectonic` / `xelatex` / `lualatex` (auto-detected)
6. **Log** every run to `output/applications_log.csv` for tracking

---

## Prerequisites

- **Python 3.10+**
- **Anthropic API key** and/or **OpenAI API key**
- A LaTeX compiler — any one of: `pdflatex` (BasicTeX/TeX Live), `tectonic`, `xelatex`, `lualatex`

---

## Setup

### 1. Install a LaTeX compiler

**macOS — BasicTeX (recommended, ~100 MB):**

```bash
brew install --cask basictex
eval "$(/usr/libexec/path_helper)"   # reload PATH
```

Install extra packages needed by Jake's Resume template:

```bash
sudo tlmgr update --self
sudo tlmgr install latexmk enumitem fontaxes preprint ragged2e
```

> If compilation fails with a missing package error, the `.log` file will name the missing `.sty` — install it with `sudo tlmgr install <package-name>`.

**PyCharm / IDE users:** If `pdflatex` works in terminal but not in your IDE, add `/Library/TeX/texbin` to your run configuration's `PATH`.

### 2. Clone and create a virtual environment

```bash
git clone https://github.com/<your-username>/ResuMatch-AI.git
cd ResuMatch-AI

python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**`requirements.txt`**
```
anthropic>=0.40.0
openai>=1.50.0
python-dotenv
pyyaml>=6.0
```

### 4. Set API keys

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...        # only needed if using OpenAI in llm_config.yaml
```

---

## Project Structure

```
ResuMatch-AI/
├── tailor.py                        # CLI entry point
├── llm_config.yaml                  # LLM model + prompt configuration (per task)
├── requirements.txt
├── .env                             # API keys (gitignored)
├── src/
│   ├── pipeline.py                  # Orchestrates the full tailoring flow
│   ├── config.py                    # Loads llm_config.yaml, exposes per-task settings
│   ├── models/
│   │   ├── resume.py                # Resume data structures (sections, bullets, skills)
│   │   └── job_description.py       # Job description data model
│   ├── parser/
│   │   ├── latex_parser.py          # .tex → ResumeJSON
│   │   └── jd_parser.py             # Job description → skills/phrases (LLM + regex fallback)
│   ├── llm/
│   │   ├── api.py                   # Anthropic / OpenAI API call functions
│   │   ├── prompts.py               # Builds the per-application user prompt
│   │   └── validator.py             # Validates and parses LLM JSON output
│   └── output/
│       ├── injector.py              # Injects LLM changes back into .tex
│       ├── compiler.py              # Compiles .tex → .pdf, cleans build artifacts
│       ├── file_manager.py          # Output paths, date-based directories, deduplication
│       └── tracker.py               # Appends run metadata to applications_log.csv
└── output/                          # Generated resumes (gitignored)
    ├── YYYY-MM-DD/
    │   ├── Resume_Company_Job_Title.tex
    │   └── Resume_Company_Job_Title.pdf
    └── applications_log.csv
```

---

## Usage

```bash
# Basic run
python tailor.py \
  --resume master.tex \
  --company "Anthropic" \
  --title "Machine Learning Engineer" \
  --jd-file jd.txt

# Inline job description
python tailor.py \
  --resume master.tex \
  --company "Netflix" \
  --title "Senior Data Scientist" \
  --jd "We are looking for..."
```

### Arguments

| Flag | Required | Description |
|---|---|---|
| `--resume` | Yes | Path to master `.tex` resume |
| `--company` | Yes | Target company name |
| `--title` | Yes | Target job title |
| `--jd` | One of these | Job description as inline text |
| `--jd-file` | One of these | Path to a `.txt` file with the job description |
| `--output-dir` | No | Base output directory (default: `output/`) |

### Output

Each run produces:
- **Tailored `.tex`** — modified copy of your master resume
- **Compiled `.pdf`** — saved to `output/YYYY-MM-DD/Resume_{Company}_{Title}.pdf` (auto-deduplicated)
- **Console diff** — shows every bullet rewrite, project selection, and skill change
- **CSV log** — run appended to `output/applications_log.csv`

---

## LLM Configuration (`llm_config.yaml`)

Model selection, token limits, and prompts are configured in `llm_config.yaml` at the project root — no code changes needed.

There are two independent LLM tasks:

### `jd_extraction`
Extracts skills and key phrases from the job description.

```yaml
jd_extraction:
  enabled: true          # false → skip LLM, use regex fallback instead
  provider:
    - name: anthropic
      enabled: false
      model: claude-haiku-4-5-20251001
    - name: openai
      enabled: true
      model: gpt-4.1-mini
  max_tokens: 1024
  prompt: ""             # leave blank to use the built-in prompt
```

### `resume_tailoring`
Rewrites bullets, reorders skills, selects projects, and updates the summary.

```yaml
resume_tailoring:
  provider:
    - name: anthropic
      enabled: true
      model: claude-haiku-4-5-20251001
      max_tokens: 8192
    - name: openai
      enabled: false
      model: gpt-4o
      max_tokens: 8192
  prompt: ""             # leave blank to use the built-in prompt
```

**To switch providers:** flip the `enabled` flags in the provider list.  
**To override a prompt:** paste your custom prompt under the `prompt:` key of that task. The tailoring prompt must produce the exact JSON schema the pipeline expects — see `src/config.py` for the schema.

---

## Cost

At moderate usage (a few runs per day), expect low single-digit dollars per month with Claude Haiku 4.5. Anthropic prompt caching is enabled by default on the tailoring system prompt.

---

## License

MIT
