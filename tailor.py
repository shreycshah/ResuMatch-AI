#!/usr/bin/env python3
"""
CLI entry point for the resume tailoring pipeline.

Usage:
    python tailor.py --resume master.tex --company Netflix --title "ML Engineer" --jd "We are looking for..."
    python tailor.py --resume master.tex --company "Meta AI" --title "Senior DS" --jd-file jd.txt --model openai
"""

import argparse
import os
import sys
import traceback

from src.pipeline import ResumeTailorPipeline


def main() -> int:
    args = parse_args()

    # Validate inputs
    if not os.path.exists(args.resume):
        print(f"Error: Resume file not found: {args.resume}")
        return 1

    jd_text = load_jd(args)
    if not jd_text or len(jd_text.strip()) < 20:
        print("Error: Job description is too short (min 20 characters)")
        return 1

    # Run pipeline
    pipeline = ResumeTailorPipeline(model=args.model, output_dir=args.output_dir)

    try:
        result = pipeline.run(
            resume_path=args.resume,
            company=args.company,
            title=args.title,
            jd_text=jd_text,
        )
    except Exception as e:
        print(f"\n✗ Pipeline failed: {e}")
        traceback.print_exc()
        return 1

    return 1 if result.get("error") else 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Tailor your resume for a specific job description.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tailor.py --resume master.tex --company Netflix --title "ML Engineer" --jd "We are looking for..."
  python tailor.py --resume master.tex --company "Meta AI" --title "Senior DS" --jd-file jd.txt --model openai
        """,
    )
    p.add_argument('--resume', required=True, help='Path to master resume .tex file')
    p.add_argument('--company', required=True, help='Company name (e.g. "Netflix", "Meta AI")')
    p.add_argument('--title', required=True, help='Job title (e.g. "ML Engineer")')

    jd = p.add_mutually_exclusive_group(required=True)
    jd.add_argument('--jd', help='Job description text (inline)')
    jd.add_argument('--jd-file', help='Path to a .txt file containing the JD')

    p.add_argument('--model', choices=['anthropic', 'openai'], default='anthropic',
                   help='LLM: anthropic (Haiku 4.5) or openai (GPT-4.1 mini). Default: anthropic')
    p.add_argument('--output-dir', default='output', help='Base output directory. Default: output/')

    return p.parse_args()


def load_jd(args: argparse.Namespace) -> str:
    if args.jd_file:
        if not os.path.exists(args.jd_file):
            print(f"Error: JD file not found: {args.jd_file}")
            sys.exit(1)
        with open(args.jd_file, 'r', encoding='utf-8') as f:
            return f.read()
    return args.jd


if __name__ == "__main__":
    sys.exit(main())