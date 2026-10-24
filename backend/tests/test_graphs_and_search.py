"""Recursive CTEs (prerequisites, citations, recommendations), search, similarity, stats."""
from datetime import date, timedelta


def concept(api, name):
    return api.post("/concepts", json={"name": name})["id"]


def test_prerequisite_chain_order_and_cycle_rejection(make_user):
    a = make_user("a")
    calc, linalg, grad, backprop, transformers = (
        concept(a, n) for n in ("Calculus", "Linear algebra", "Gradient descent", "Backprop", "Transformers"))
    # Transformers -> Backprop -> Gradient descent -> Calculus;  Backprop -> Linear algebra -> ...
    a.post(f"/concepts/{transformers}/prerequisites", json={"prerequisite_id": backprop})
    a.post(f"/concepts/{backprop}/prerequisites", json={"prerequisite_id": grad})
    a.post(f"/concepts/{backprop}/prerequisites", json={"prerequisite_id": linalg})
    a.post(f"/concepts/{grad}/prerequisites", json={"prerequisite_id": calc})
    a.post(f"/concepts/{transformers}/prerequisites", json={"prerequisite_id": calc})  # shortcut edge

    chain = a.get(f"/concepts/{transformers}/prerequisites")["learning_order"]
    order = [c["name"] for c in chain]
    assert set(order) == {"Calculus", "Linear algebra", "Gradient descent", "Backprop"}
    # every prerequisite comes before the thing that needs it
    assert order.index("Calculus") < order.index("Gradient descent") < order.index("Backprop")
    assert order.index("Linear algebra") < order.index("Backprop")
    assert {c["name"]: c["depth"] for c in chain}["Calculus"] == 3   # longest route wins

    # Calculus -> Transformers would close the loop
    r = a.call("POST", f"/concepts/{calc}/prerequisites", json={"prerequisite_id": transformers})
    assert r.status_code == 409
    assert "cycle" in r.json()["detail"] and "Transformers" in r.json()["detail"]
    a.post(f"/concepts/{calc}/prerequisites", json={"prerequisite_id": calc}, expect=409)


def test_citation_lineage(make_user):
    a = make_user("a")
    ids = {t: a.post("/papers", json={"title": t})["id"] for t in "ABCDE"}
    for citing, cited in [("A", "B"), ("B", "C"), ("C", "D"), ("A", "C"), ("D", "B")]:  # D->B makes a loop
        a.post(f"/papers/{ids[citing]}/citations", json={"cited_paper_id": ids[cited]})
    lineage = {r["title"]: r["depth"] for r in a.get(f"/papers/{ids['A']}/citation-lineage")}
    assert lineage == {"B": 1, "C": 1, "D": 2}            # shortest route, E not included, no infinite loop
    assert sorted(p["title"] for p in a.get(f"/papers/{ids['B']}/citations")["cited_by"]) == ["A", "D"]


def test_recommendations(make_user):
    a = make_user("a")
    basics, attention, rl = concept(a, "Basics"), concept(a, "Attention"), concept(a, "RL")
    a.post(f"/concepts/{attention}/prerequisites", json={"prerequisite_id": basics})

    intro = a.post("/papers", json={"title": "Intro to Attention"})["id"]
    advanced = a.post("/papers", json={"title": "Advanced Attention"})["id"]
    rlhf = a.post("/papers", json={"title": "RLHF"})["id"]
    a.put(f"/papers/{intro}/concepts", json={"concept_id": attention, "relation": "introduces"})
    a.put(f"/papers/{advanced}/concepts", json={"concept_id": basics, "relation": "assumes"})
    a.put(f"/papers/{advanced}/concepts", json={"concept_id": attention, "relation": "assumes"})
    a.put(f"/papers/{rlhf}/concepts", json={"concept_id": rl, "relation": "assumes"})

    rec = a.get("/recommendations")
    blocked = {r["title"]: r for r in rec["blocked"]}
    assert "Advanced Attention" in blocked
    missing = {m["name"]: m for m in blocked["Advanced Attention"]["missing"]}
    assert set(missing) == {"Basics", "Attention"}
    assert missing["Attention"]["read_first"][0]["title"] == "Intro to Attention"

    a.put(f"/papers/{intro}/state", json={"status": "done"})
    rec = a.get("/recommendations")
    # Attention learned, and Basics too because it's a prerequisite of Attention
    assert "Advanced Attention" in [r["title"] for r in rec["ready"]]
    assert [r["title"] for r in rec["blocked"]] == ["RLHF"]


def test_full_text_search_and_similarity(make_user):
    a = make_user("a")
    p1 = a.post("/papers", json={"title": "Convolutional networks for image classification",
                                 "abstract": "We train deep convolutional neural networks on ImageNet."})
    p2 = a.post("/papers", json={"title": "Image recognition with residual learning",
                                 "abstract": "Residual connections let very deep CNNs train on ImageNet."})
    a.post("/papers", json={"title": "A history of medieval farming",
                            "abstract": "Crop rotation in 12th century Europe."})
    a.post(f"/papers/{p1['id']}/highlights", json={"quote": "accuracy drops when networks get deeper"})
    a.post(f"/papers/{p1['id']}/notes", json={"content": "compare against residual nets"})

    results = a.get("/search", params={"q": "residual"})
    kinds = {r["kind"] for r in results}
    assert kinds == {"paper", "note"}
    assert results[0]["paper_id"] == p2["id"]               # title match (weight A) ranks first
    assert "⟦" in results[0]["snippet"]
    assert a.get("/search", params={"q": "deeper networks", "kind": "highlight"})[0]["kind"] == "highlight"

    similar = a.get(f"/papers/{p1['id']}/similar")
    assert similar[0]["id"] == p2["id"]                      # CNN paper closer than farming
    assert similar[0]["similarity"] > similar[-1]["similarity"]

    # another user's search must not see these
    assert make_user("b").get("/search", params={"q": "residual"}) == []


def test_reading_sessions_stats_and_streak(make_user, db):
    a = make_user("a")
    p = a.post("/papers", json={"title": "P"})
    s = a.post(f"/papers/{p['id']}/sessions", json={"page": 1})
    assert a.get(f"/papers/{p['id']}")["status"] == "reading"
    a.post(f"/sessions/{s['id']}/heartbeat", json={"page": 4}, expect=200)
    assert a.get(f"/papers/{p['id']}")["current_page"] == 4

    # Fake history: read 10 min on each of the last 3 days (incl. today) and on 3 days a week ago.
    today = date.today()
    for d in [today, today - timedelta(1), today - timedelta(2),
              today - timedelta(7), today - timedelta(8), today - timedelta(9), today - timedelta(10)]:
        db.execute(
            """INSERT INTO reading_sessions (user_id, paper_id, started_at, ended_at)
               VALUES (%s, %s, %s::date + time '12:00', %s::date + time '12:10')""",
            (a.user["id"], p["id"], d, d),
        )
    streak = a.get("/stats/streak", params={"tz": "UTC"})
    assert streak["current"] == 3 and streak["longest"] == 4 and streak["active_today"]

    stats = a.get("/stats/overview", params={"tz": "UTC"})
    assert stats["totals"]["reading"] == 1
    assert stats["daily_minutes"][-1]["minutes"] >= 10
    assert len(a.get("/stats/calendar", params={"tz": "UTC"})) == 371
    a.get("/stats/streak", params={"tz": "Not/AZone"}, expect=400)
