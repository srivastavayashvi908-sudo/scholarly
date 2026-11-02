"""AI concept extraction: merging into the graph, cycle skipping, a paper's learning path, "known"."""
import json

from app.services import llm

FAKE_ANSWER = "```json\n" + json.dumps({"concepts": [
    {"name": "Transformer", "description": "Attention-only sequence model.", "difficulty": "advanced",
     "paper_relation": "introduces", "prerequisites": ["Self-attention"]},
    {"name": "Self-attention", "difficulty": "intermediate", "paper_relation": None,
     "prerequisites": ["Attention"]},
    {"name": "Attention", "difficulty": "intermediate", "paper_relation": "assumes",
     "prerequisites": ["Neural network"]},
    {"name": "Neural network", "difficulty": "beginner", "paper_relation": None,
     "prerequisites": ["Linear algebra"]},
    # Linear algebra -> Transformer would close a loop: it must be skipped, not saved.
    {"name": "Linear algebra", "difficulty": "beginner", "paper_relation": None,
     "prerequisites": ["Transformer", "Probability"]},   # Probability isn't listed: still becomes a concept
]}) + "\n```"


def fake_llm(monkeypatch, answer=FAKE_ANSWER):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: answer)


def test_extract_merges_into_graph_and_builds_learning_path(make_user, monkeypatch):
    fake_llm(monkeypatch)
    a = make_user("a")
    mine = a.post("/concepts", json={"name": "Neural Networks"})["id"]   # made by hand earlier
    paper = a.post("/papers", json={"title": "Attention Is All You Need", "abstract": "We propose..."})["id"]

    r = a.post(f"/papers/{paper}/extract-concepts", expect=200)
    assert r["concepts_found"] == 6
    assert r["new_concepts"] == 5            # "Neural network" matched the existing "Neural Networks"
    assert r["cycles_skipped"] == 1
    assert r["links_added"] == 5

    graph = a.get("/concepts/graph")
    names = {n["name"]: n for n in graph["nodes"]}
    assert "Neural network" not in names and names["Neural Networks"]["id"] == mine
    assert names["Transformer"]["source"] == "ai" and names["Neural Networks"]["source"] == "user"

    path = a.get(f"/papers/{paper}/learning-path")
    assert {c["name"]: c["relation"] for c in path["paper_concepts"]} == {"Transformer": "introduces", "Attention": "assumes"}
    order = [c["name"] for c in path["learn_first"]]
    assert "Transformer" not in order                      # you learn that FROM the paper
    for before, after in [("Linear algebra", "Neural Networks"), ("Neural Networks", "Attention"),
                          ("Probability", "Linear algebra")]:
        assert order.index(before) < order.index(after)

    # Running it again changes nothing.
    again = a.post(f"/papers/{paper}/extract-concepts", expect=200)
    assert again["new_concepts"] == 0 and again["links_added"] == 0


def test_known_concepts_count_as_learned(make_user, monkeypatch):
    fake_llm(monkeypatch)
    a = make_user("a")
    source = a.post("/papers", json={"title": "Attention paper", "abstract": "..."})["id"]
    a.post(f"/papers/{source}/extract-concepts", expect=200)
    attention = next(n for n in a.get("/concepts") if n["name"] == "Attention")

    reader = a.post("/papers", json={"title": "Needs attention"})["id"]
    a.put(f"/papers/{reader}/concepts", json={"concept_id": attention["id"], "relation": "assumes"})
    ready = lambda: {p["title"] for p in a.get("/recommendations")["ready"]}
    assert "Needs attention" not in ready()

    assert a.put(f"/concepts/{attention['id']}/known", json={"known": True})["known"] is True
    assert "Needs attention" in ready()
    known = {c["name"]: c["known"] for c in a.get(f"/papers/{source}/learning-path")["learn_first"]}
    assert known["Attention"] is True and known["Linear algebra"] is False


def test_extract_needs_something_to_read(make_user, monkeypatch):
    fake_llm(monkeypatch)
    a = make_user("a")
    paper = a.post("/papers", json={"title": "Only a title"})["id"]
    a.post(f"/papers/{paper}/extract-concepts", expect=400)
    fake_llm(monkeypatch, "sorry, I can't help with that")
    paper = a.post("/papers", json={"title": "T", "abstract": "A"})["id"]
    a.post(f"/papers/{paper}/extract-concepts", expect=502)
