"""
Job description parser.
Uses an LLM to extract required_skills, preferred_skills,
and key_phrases from raw job description text.

Provider, model, max_tokens, and extraction prompt are read from
llm_config.yaml (via src.config); the default prompt lives in src/config.py.

Falls back to regex heuristics if the LLM call fails.
"""

import json
import re
from typing import Optional, Union

import anthropic
import openai

from src.models.job_description import JobDescription
from src.config import get_config

class JDParser:
    """Parse a job description into structured fields via LLM, with regex fallback."""

    def __init__(self, client: Optional[Union[anthropic.Anthropic, openai.OpenAI]] = None):
        self._cfg = get_config().jd_extraction
        if client is not None:
            # Caller supplied a client (e.g. for testing) — honour it
            self._client = client
            self._provider = "openai" if isinstance(client, openai.OpenAI) else "anthropic"
        else:
            # Create a client based on llm_config.yaml provider setting
            if self._cfg.provider == "openai":
                self._client = openai.OpenAI()
                self._provider = "openai"
            else:
                self._client = anthropic.Anthropic()
                self._provider = "anthropic"

    # ── Public API ──

    def parse(self, company: str, title: str, raw_text: str) -> JobDescription:
        jd = JobDescription(company=company, title=title, raw_text=raw_text)

        if not self._cfg.enabled:
            print("JD extraction disabled in llm_config.yaml — falling back to regex heuristics")
            self._regex_fallback(jd, raw_text)
            return jd

        extracted = self._llm_extract(raw_text)
        if extracted:
            jd.required_skills = extracted["required_skills"]
            jd.preferred_skills = extracted["preferred_skills"]
            jd.key_phrases = extracted["key_phrases"]
        else:
            print("LLM extraction failed — falling back to regex heuristics")
            self._regex_fallback(jd, raw_text)

        return jd

    # ── LLM extraction ──

    def _llm_extract(self, raw_text: str) -> Optional[dict]:
        print(f"   [jd_extraction] {self._provider} / {self._cfg.model}")
        try:
            if self._provider == "anthropic":
                text = self._call_anthropic(raw_text)
            else:
                text = self._call_openai(raw_text)

            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

            data = json.loads(text)
            print("JD extraction successful via LLM")
            return self._validate_extraction(data)

        except (
            anthropic.APIError,
            openai.APIError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
        ) as exc:
            print(f"LLM extraction error: {exc}")
            return None

    def _call_anthropic(self, raw_text: str) -> str:
        prompt = self._cfg.prompt
        response = self._client.messages.create(
            model=self._cfg.model,
            max_tokens=self._cfg.max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"{prompt}\n\n"
                        f"--- JOB DESCRIPTION ---\n{raw_text}"
                    ),
                }
            ],
        )
        return response.content[0].text.strip()

    def _call_openai(self, raw_text: str) -> str:
        prompt = self._cfg.prompt
        response = self._client.chat.completions.create(
            model=self._cfg.model,
            max_tokens=self._cfg.max_tokens,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"--- JOB DESCRIPTION ---\n{raw_text}"},
            ],
        )
        return response.choices[0].message.content.strip()

    # ── Validation ──

    @staticmethod
    def _validate_extraction(data: dict) -> Optional[dict]:
        """Ensure the LLM response has the right shape and types."""
        required_keys = {"required_skills", "preferred_skills", "key_phrases"}
        if not required_keys.issubset(data.keys()):
            print(f"Missing keys in LLM response: {required_keys - data.keys()}")
            return None

        for key in required_keys:
            if not isinstance(data[key], list):
                return None
            data[key] = [str(item) for item in data[key]]

        data["key_phrases"] = data["key_phrases"][:15]

        preferred_set = set(data["preferred_skills"]) - set(data["required_skills"])
        data["preferred_skills"] = [s for s in data["preferred_skills"] if s in preferred_set]

        return data

    # ── Regex fallback ──

    _TECH_KEYWORDS = {
        'python', 'java', 'c++', 'javascript', 'typescript', 'go', 'rust', 'scala', 'r',
        'sql', 'nosql', 'mongodb', 'postgresql', 'mysql', 'redis', 'elasticsearch',
        'pytorch', 'tensorflow', 'keras', 'scikit-learn', 'sklearn', 'xgboost', 'lightgbm',
        'spark', 'pyspark', 'hadoop', 'airflow', 'kafka', 'flink',
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'k8s', 'terraform',
        'mlflow', 'wandb', 'dvc', 'mlops', 'ci/cd', 'github actions',
        'pandas', 'numpy', 'scipy', 'matplotlib',
        'fastapi', 'flask', 'django', 'react', 'node.js',
        'bert', 'gpt', 'transformers', 'llm', 'rag', 'embeddings', 'vector database',
        'pinecone', 'weaviate', 'chromadb', 'faiss',
        'a/b testing', 'recommendation systems', 'nlp', 'computer vision',
        'deep learning', 'machine learning', 'neural networks', 'reinforcement learning',
        'feature engineering', 'feature store', 'model serving', 'model monitoring',
        'databricks', 'snowflake', 'dbt', 'looker', 'tableau', 'power bi',
    }

    _SECTION_PATTERNS = {
        'required': [r'(?:requirements?|qualifications?|must\s+have|what\s+you.*?(?:bring|need))'],
        'preferred': [r'(?:preferred|nice\s+to\s+have|bonus|plus|ideally)'],
    }

    def _regex_fallback(self, jd: JobDescription, raw_text: str) -> None:
        text_lower = raw_text.lower()
        found = [s for s in self._TECH_KEYWORDS if re.search(r'\b' + re.escape(s) + r'\b', text_lower)]

        req_section = self._extract_section(raw_text, 'required')
        if req_section:
            req_lower = req_section.lower()
            jd.required_skills = [s for s in found if s in req_lower]
            jd.preferred_skills = [s for s in found if s not in req_lower]
        else:
            jd.required_skills = found
            jd.preferred_skills = []

        jd.key_phrases = self._extract_key_phrases(raw_text)

    def _extract_section(self, text: str, section_type: str) -> Optional[str]:
        for pattern in self._SECTION_PATTERNS.get(section_type, []):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                start = m.end()
                nxt = re.search(
                    r'\n\s*(?:about|responsibilities|what\s+we|benefits|perks|'
                    r'requirements|preferred|qualifications)',
                    text[start:], re.IGNORECASE,
                )
                end = start + nxt.start() if nxt else len(text)
                return text[start:end]
        return None

    @staticmethod
    def _extract_key_phrases(text: str) -> list[str]:
        phrases = re.findall(r'(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', text)
        phrases += re.findall(r'"([^"]+)"', text)
        seen: set[str] = set()
        result = []
        for p in phrases:
            key = p.lower().strip()
            if key not in seen and len(key) > 3:
                seen.add(key)
                result.append(p)
        return result[:15]
