"""Ask the LLM which concepts a paper uses, and the prerequisite tree underneath them."""
import json
import re

from fastapi import HTTPException

from . import llm

DIFFICULTIES = {"beginner", "intermediate", "advanced"}
RELATIONS = {"introduces", "assumes"}
MAX_CONCEPTS = 45
MAX_PAPER_CONCEPTS = 12   # the AI sometimes tags far more than the 5-10 asked for

SYSTEM = """You build prerequisite graphs that help students prepare to read research papers.

Given a paper, do two things:
1. List the 5-10 key concepts a reader must understand to follow THIS paper. Mark each one
   "introduces" if the paper itself proposes it, otherwise "assumes". Only these key
   concepts get a paper_relation; every other concept has "paper_relation": null.
2. For every concept, list its direct prerequisites: the more basic concepts a student must
   understand first. Add each prerequisite as a concept too, with its own prerequisites,
   and keep going down to fundamentals such as Linear algebra, Probability or Calculus,
   at most 4 levels below the paper's concepts.

Rules:
- A prerequisite is always strictly more basic than the concept that needs it. No cycles.
- Use short, standard, singular names, e.g. "Self-attention", "Gradient descent".
- If a concept matches one in the student's existing list, use that exact existing name.
- Every name used in a "prerequisites" list must also appear as a concept.
- At most 25 concepts in total. Descriptions under 15 words.

Reply with JSON only, no markdown, in exactly this shape:
{"concepts": [{"name": "...", "description": "one short sentence",
  "difficulty": "beginner|intermediate|advanced",
  "paper_relation": "introduces|assumes|null", "prerequisites": ["..."]}]}"""


def concept_key(name: str) -> str:
    """Loose identity for matching names: 'Neural Networks (NN)' == 'neural-network'."""
    s = re.sub(r"\(.*?\)", " ", name.lower())
    s = re.sub(r"[-_/\u2010-\u2015]", " ", s)
    words = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in s.split()]
    return " ".join(words)


def tidy(text, limit: int = 80) -> str:
    """Plain hyphens and spaces, so names typed by hand match the AI's."""
    return re.sub(r"[\u2010-\u2015]", "-", str(text)).replace("\u00a0", " ").strip()[:limit]


def extract(title: str, abstract: str, body: str, existing_names: list[str]) -> list[dict]:
    prompt = (
        f"Paper title: {title}\n\nAbstract:\n{abstract or '(none)'}\n\n"
        f"Text from the paper:\n{body or '(not available)'}\n\n"
        f"The student's existing concepts: {', '.join(existing_names[:150]) or '(none yet)'}"
    )
    # Kept small on purpose: Groq's free tier allows ~8000 tokens per minute (prompt + answer).
    raw = llm.chat(SYSTEM, prompt, max_tokens=4800, reasoning_effort="low")
    return clean(parse_json(raw))


def parse_json(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    try:
        return json.loads(raw[start:end + 1])
    except ValueError:
        raise HTTPException(502, "The AI's answer wasn't valid JSON. Please try again.")


def clean(data: dict) -> list[dict]:
    """Validate the AI's answer and drop anything malformed rather than failing."""
    out, seen = [], {}
    for c in data.get("concepts") or []:
        if not isinstance(c, dict) or not str(c.get("name") or "").strip():
            continue
        name = tidy(c["name"])
        key = concept_key(name)
        if key in seen:
            continue
        seen[key] = name
        out.append({
            "name": name,
            "description": tidy(c.get("description") or "", limit=200) or None,
            "difficulty": c.get("difficulty") if c.get("difficulty") in DIFFICULTIES else None,
            "relation": c.get("paper_relation") if c.get("paper_relation") in RELATIONS else None,
            "prerequisites": [tidy(p) for p in c.get("prerequisites") or [] if str(p).strip()],
        })
    # A prerequisite the AI forgot to list as a concept still becomes one.
    for c in list(out):
        for p in c["prerequisites"]:
            if concept_key(p) not in seen:
                seen[concept_key(p)] = p
                out.append({"name": p, "description": None, "difficulty": None, "relation": None, "prerequisites": []})
    # Keep the paper's own concepts focused: everything it introduces, then the first few it assumes.
    tagged = [c for c in out if c["relation"] == "introduces"] + [c for c in out if c["relation"] == "assumes"]
    for c in tagged[MAX_PAPER_CONCEPTS:]:
        c["relation"] = None
    if not out:
        raise HTTPException(502, "The AI didn't find any concepts. Please try again.")
    return out[:MAX_CONCEPTS]
