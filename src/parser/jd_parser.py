"""
Lightweight job description parser.
Extracts skills, key phrases, and section structure using regex heuristics.
No NER models — fast, zero dependencies beyond stdlib.
"""

import re
from typing import Optional
from src.data_models.jd_model import JobDescription


class JDParser:

    TECH_KEYWORDS = {
        # Languages
        'python', 'java', 'c++', 'javascript', 'typescript', 'go', 'rust', 'scala', 'r',
        # Databases
        'sql', 'nosql', 'mongodb', 'postgresql', 'mysql', 'redis', 'elasticsearch',
        # ML frameworks
        'pytorch', 'tensorflow', 'keras', 'scikit-learn', 'sklearn', 'xgboost', 'lightgbm',
        # Data engineering
        'spark', 'pyspark', 'hadoop', 'airflow', 'kafka', 'flink',
        # Cloud & infra
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'k8s', 'terraform',
        # MLOps
        'mlflow', 'wandb', 'dvc', 'mlops', 'ci/cd', 'github actions',
        # Python ecosystem
        'pandas', 'numpy', 'scipy', 'matplotlib',
        # Web frameworks
        'fastapi', 'flask', 'django', 'react', 'node.js',
        # NLP / LLM
        'bert', 'gpt', 'transformers', 'llm', 'rag', 'embeddings', 'vector database',
        'pinecone', 'weaviate', 'chromadb', 'faiss',
        # ML domains
        'a/b testing', 'recommendation systems', 'nlp', 'computer vision',
        'deep learning', 'machine learning', 'neural networks', 'reinforcement learning',
        'feature engineering', 'feature store', 'model serving', 'model monitoring',
        # Analytics
        'databricks', 'snowflake', 'dbt', 'looker', 'tableau', 'power bi',
    }

    SECTION_PATTERNS = {
        'required': [
            r'(?:requirements?|qualifications?|must\s+have|what\s+you.*?(?:bring|need))',
        ],
        'preferred': [
            r'(?:preferred|nice\s+to\s+have|bonus|plus|ideally)',
        ],
    }

    YEARS_RE = re.compile(
        r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience)?',
        re.IGNORECASE,
    )

    def parse(self, company: str, title: str, raw_text: str) -> JobDescription:
        jd = JobDescription(company=company, title=title, raw_text=raw_text)
        text_lower = raw_text.lower()

        # Match skills from our keyword bank
        found_skills = [
            skill for skill in self.TECH_KEYWORDS
            if re.search(r'\b' + re.escape(skill) + r'\b', text_lower)
        ]

        # Try to split required vs preferred
        req_section = self._extract_section(raw_text, 'required')
        if req_section:
            req_lower = req_section.lower()
            jd.required_skills = [s for s in found_skills if s in req_lower]
            jd.preferred_skills = [s for s in found_skills if s not in req_lower]
        else:
            jd.required_skills = found_skills
            jd.preferred_skills = []

        jd.key_phrases = self._extract_key_phrases(raw_text)
        return jd

    # ── Private helpers ──

    def _extract_section(self, text: str, section_type: str) -> Optional[str]:
        for pattern in self.SECTION_PATTERNS.get(section_type, []):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                start = m.end()
                nxt = re.search(
                    r'\n\s*(?:about|responsibilities|what\s+we|benefits|perks|'
                    r'requirements|preferred|qualifications)',
                    text[start:],
                    re.IGNORECASE,
                )
                end = start + nxt.start() if nxt else len(text)
                return text[start:end]
        return None

    def _extract_key_phrases(self, text: str) -> list[str]:
        phrases = re.findall(r'(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', text)
        phrases += re.findall(r'"([^"]+)"', text)
        seen = set()
        result = []
        for p in phrases:
            key = p.lower().strip()
            if key not in seen and len(key) > 3:
                seen.add(key)
                result.append(p)
        return result[:15]