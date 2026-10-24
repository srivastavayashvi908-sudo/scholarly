"""Auth, papers, highlights, notes, comments, collections, sharing."""


def test_register_login_and_auth_required(client, make_user):
    alice = make_user("alice")
    r = client.post("/api/auth/login", json={"email": alice.email, "password": "secret123"})
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"email": alice.email, "password": "nope"}).status_code == 401
    assert client.get("/api/papers").status_code == 401
    assert client.post("/api/auth/register",
                       json={"email": alice.email, "name": "x", "password": "secret123"}).status_code == 409


def test_paper_crud_and_reading_state(make_user):
    a = make_user("a")
    p = a.post("/papers", json={"title": "Attention Is All You Need", "year": 2017, "doi": "10.5555/ATTN"})
    assert p["status"] == "to_read" and p["role"] == "owner" and p["doi"] == "10.5555/attn"
    a.post("/papers", json={"title": "dup", "doi": "10.5555/attn"}, expect=409)

    p = a.patch(f"/papers/{p['id']}", json={"venue": "NeurIPS"})
    assert p["venue"] == "NeurIPS"
    p = a.put(f"/papers/{p['id']}/state", json={"status": "done"})
    assert p["status"] == "done" and p["finished_at"] is not None          # set by trigger
    p = a.put(f"/papers/{p['id']}/state", json={"status": "reading"})
    assert p["finished_at"] is None

    assert len(a.get("/papers?status=reading")) == 1
    a.delete(f"/papers/{p['id']}")
    a.get(f"/papers/{p['id']}", expect=404)


def test_other_users_cannot_see_my_paper(make_user):
    a, b = make_user("a"), make_user("b")
    p = a.post("/papers", json={"title": "Private"})
    b.get(f"/papers/{p['id']}", expect=404)
    assert b.get("/papers") == []


def test_highlights_notes_and_threaded_comments(make_user):
    a = make_user("a")
    p = a.post("/papers", json={"title": "P"})
    h = a.post(f"/papers/{p['id']}/highlights", json={
        "quote": "We use dropout of 0.1", "tag": "methodology", "page": 3,
        "position": {"rects": [{"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.02}]},
    })
    assert h["position"]["rects"][0]["w"] == 0.5
    a.post(f"/papers/{p['id']}/highlights", json={"quote": "x", "tag": "not-a-tag"}, expect=422)
    a.post(f"/papers/{p['id']}/highlights", json={"quote": "x", "color": "red"}, expect=422)
    assert a.patch(f"/highlights/{h['id']}", json={"color": "#ff8800"})["color"] == "#ff8800"

    n = a.post(f"/papers/{p['id']}/notes", json={"content": "check the ablation"})
    assert a.patch(f"/notes/{n['id']}", json={"content": "edited"})["content"] == "edited"

    top = a.post(f"/highlights/{h['id']}/comments", json={"body": "why 0.1?"})
    reply = a.post(f"/highlights/{h['id']}/comments", json={"body": "standard choice", "parent_id": top["id"]})
    a.post(f"/highlights/{h['id']}/comments", json={"body": "reply to reply", "parent_id": reply["id"]})
    a.post(f"/highlights/{h['id']}/comments", json={"body": "second thread"})
    thread = a.get(f"/highlights/{h['id']}/comments")
    assert [c["body"] for c in thread] == ["why 0.1?", "standard choice", "reply to reply", "second thread"]
    assert [c["depth"] for c in thread] == [0, 1, 2, 0]

    a.delete(f"/comments/{top['id']}")      # cascades to its replies
    assert [c["body"] for c in a.get(f"/highlights/{h['id']}/comments")] == ["second thread"]


def test_collections_comparison_table(make_user):
    a = make_user("a")
    c = a.post("/collections", json={"name": "Vision"})
    p1 = a.post("/papers", json={"title": "ResNet", "year": 2015})
    p2 = a.post("/papers", json={"title": "ViT", "year": 2020})
    for p in (p1, p2):
        a.post(f"/collections/{c['id']}/papers/{p['id']}")
    a.put(f"/papers/{p1['id']}/attributes", json={"attr_name": "Dataset", "attr_value": "ImageNet"})
    a.put(f"/papers/{p1['id']}/attributes", json={"attr_name": "metric", "attr_value": "top-1 76%"})
    a.put(f"/papers/{p2['id']}/attributes", json={"attr_name": "dataset", "attr_value": "JFT-300M"})
    a.put(f"/papers/{p2['id']}/attributes", json={"attr_name": "dataset", "attr_value": "ImageNet-21k"})  # upsert

    table = a.get(f"/collections/{c['id']}/comparison")
    assert table["columns"] == ["dataset", "metric"]
    rows = {r["title"]: r["attributes"] for r in table["rows"]}
    assert rows == {"ResNet": {"dataset": "ImageNet", "metric": "top-1 76%"}, "ViT": {"dataset": "ImageNet-21k"}}


def test_highlight_collections_virtual_document(make_user):
    a = make_user("a")
    c = a.post("/collections", json={"name": "All limitations"})
    for title in ("P1", "P2"):
        p = a.post("/papers", json={"title": title})
        h = a.post(f"/papers/{p['id']}/highlights", json={"quote": f"{title} is slow", "tag": "limitation"})
        a.post(f"/collections/{c['id']}/highlights/{h['id']}")
    doc = a.get(f"/collections/{c['id']}/highlights")
    assert sorted(h["paper_title"] for h in doc) == ["P1", "P2"]


def test_sharing_roles(make_user):
    owner, viewer, editor, stranger = make_user("o"), make_user("v"), make_user("e"), make_user("s")
    c = owner.post("/collections", json={"name": "Shared"})
    p = owner.post("/papers", json={"title": "Shared paper"})
    owner.post(f"/collections/{c['id']}/papers/{p['id']}")
    owner.put(f"/collections/{c['id']}/members", json={"email": viewer.email, "role": "viewer"})
    owner.put(f"/collections/{c['id']}/members", json={"email": editor.email, "role": "editor"})

    # viewer can read + highlight, but not edit the paper or the collection
    assert viewer.get(f"/papers/{p['id']}")["role"] == "viewer"
    viewer.post(f"/papers/{p['id']}/highlights", json={"quote": "viewer highlight"})
    viewer.patch(f"/papers/{p['id']}", json={"title": "hacked"}, expect=403)
    viewer.post(f"/collections/{c['id']}/papers/{p['id']}", expect=403)
    viewer.put(f"/collections/{c['id']}/members", json={"email": stranger.email, "role": "viewer"}, expect=403)

    # editor can edit the paper but not delete it
    assert editor.patch(f"/papers/{p['id']}", json={"venue": "ICML"})["venue"] == "ICML"
    editor.delete(f"/papers/{p['id']}", expect=403)

    # owner sees the viewer's highlight; the owner can't delete it (it's the viewer's)
    hs = owner.get(f"/papers/{p['id']}/highlights")
    assert hs[0]["user_name"] == "v"
    owner.delete(f"/highlights/{hs[0]['id']}", expect=403)

    # strangers see nothing; removing a member revokes access
    stranger.get(f"/papers/{p['id']}", expect=404)
    owner.delete(f"/collections/{c['id']}/members/{viewer.user['id']}")
    viewer.get(f"/papers/{p['id']}", expect=404)
