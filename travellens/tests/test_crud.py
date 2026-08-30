"""Everything a contributor creates is persisted, readable, and theirs alone.

Three things are being held here.

**It reaches disk.** A submission that lives only in the response is lost on
the next request, and the portal's result panel looked exactly the same either
way. Every create is followed by a read through a separate connection.

**Only the author can change it.** There are no accounts -- the portal asks for
no name and no email -- so editing rights ride on a token issued once at
creation and stored only as a hash. An open PATCH/DELETE keyed on the id would
let anybody who can read a listing rewrite every row in it.

**A withdrawn review stops counting.** Withdrawal is a timestamp rather than a
DELETE, so the row survives; the thing that must not survive is its effect on
the published figures. A review hidden from listings while its segments still
drove every complaint rate would be the worst of both.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["SUBMISSIONS_DATABASE_URL"] = ""
    from travellens import submissions_db
    submissions_db.SUBMISSIONS_DB = tmp_path_factory.mktemp("crud") / "crud.db"
    from fastapi.testclient import TestClient
    from travellens.api import app
    return TestClient(app)


def _review(client, dest="CRUD Test Place"):
    return client.post("/analyse", json={
        "text": "The steps are broken and there is no handrail at all.",
        "destination": dest, "district": "Kandy"}).json()


def _story(client, title="A story"):
    return client.post("/stories", json={
        "title": title, "body": "z" * 60, "author": "tester"}).json()


# ------------------------------------------------------------------ create
def test_a_review_is_written_and_readable_afterwards(client):
    r = _review(client)
    assert r["stored"] is True
    back = client.get("/reviews/" + r["review_id"])
    assert back.status_code == 200
    assert back.json()["review_id"] == r["review_id"]
    assert back.json()["segments"], "segments did not persist"


def test_a_story_is_written_and_readable_afterwards(client):
    s = _story(client, "Persisted story")
    listed = client.get("/stories").json()["stories"]
    assert any(x["story_id"] == s["story_id"] for x in listed)


def test_a_correction_is_written_and_readable_afterwards(client):
    r = _review(client)
    c = client.post("/corrections", json={
        "review_id": r["review_id"], "seg_index": 0,
        "aspect": "safety", "human_verdict": "complaint"})
    assert c.status_code == 201
    listed = client.get("/corrections").json()["corrections"]
    assert any(x["correction_id"] == c.json()["correction_id"] for x in listed)


# ------------------------------------------------------------- the token
def test_creating_returns_a_token_and_never_stores_it_in_the_clear(client):
    from travellens import submissions_db
    s = _story(client, "Token check")
    token = s["manage_token"]
    assert token and len(token) > 20
    with submissions_db.connection() as con:
        row = con.execute(
            "SELECT manage_token_hash FROM user_stories WHERE story_id = ?",
            (s["story_id"],)).fetchone()
    assert row["manage_token_hash"] != token, "the token is stored in the clear"
    assert len(row["manage_token_hash"]) == 64, "expected a sha-256 hex digest"


def test_a_story_cannot_be_edited_or_deleted_by_anyone_else(client):
    s = _story(client, "Not yours")
    sid = s["story_id"]
    assert client.patch("/stories/" + sid, json={"title": "Hijacked"}).status_code == 403
    assert client.patch("/stories/" + sid, json={"title": "Hijacked"},
                        headers={"X-Manage-Token": "wrong"}).status_code == 403
    assert client.delete("/stories/" + sid).status_code == 403
    # And it really is untouched.
    listed = client.get("/stories").json()["stories"]
    assert any(x["story_id"] == sid and x["title"] == "Not yours" for x in listed)


def test_a_review_cannot_be_withdrawn_by_anyone_else(client):
    r = _review(client)
    rid = r["review_id"]
    assert client.post("/reviews/{}/withdraw".format(rid)).status_code == 403
    assert client.post("/reviews/{}/withdraw".format(rid),
                       headers={"X-Manage-Token": "wrong"}).status_code == 403
    assert client.get("/reviews/" + rid).status_code == 200


# ------------------------------------------------------------ update/delete
def test_a_partial_update_leaves_the_other_fields_alone(client):
    s = _story(client, "Before")
    up = client.patch("/stories/" + s["story_id"], json={"title": "After"},
                      headers={"X-Manage-Token": s["manage_token"]})
    assert up.status_code == 200
    story = up.json()["story"]
    assert story["title"] == "After"
    assert story["body"].startswith("z"), "body was cleared by a title edit"
    assert story["author"] == "tester"
    assert story["updated_at"], "updated_at was not stamped"


def test_an_empty_update_is_rejected_rather_than_silently_accepted(client):
    s = _story(client, "Empty update")
    r = client.patch("/stories/" + s["story_id"], json={},
                     headers={"X-Manage-Token": s["manage_token"]})
    assert r.status_code == 400


def test_deleting_a_story_really_removes_it(client):
    s = _story(client, "To delete")
    assert client.delete("/stories/" + s["story_id"],
                         headers={"X-Manage-Token": s["manage_token"]}
                         ).status_code == 200
    listed = client.get("/stories").json()["stories"]
    assert not any(x["story_id"] == s["story_id"] for x in listed)


def test_updating_or_deleting_something_that_is_gone_is_404(client):
    assert client.delete("/stories/sty_nope",
                         headers={"X-Manage-Token": "x"}).status_code == 404
    assert client.post("/reviews/usr_nope/withdraw",
                       headers={"X-Manage-Token": "x"}).status_code == 404


# --------------------------------------------------------------- withdrawal
def test_a_withdrawn_review_leaves_every_read_and_every_count(client):
    before = client.get("/stats").json()
    r = _review(client, "Withdrawal Test Place")
    rid, token = r["review_id"], r["manage_token"]
    during = client.get("/stats").json()
    assert during["total_reviews"] == before["total_reviews"] + 1

    assert client.post("/reviews/{}/withdraw".format(rid),
                       headers={"X-Manage-Token": token}).status_code == 200

    after = client.get("/stats").json()
    assert after["total_reviews"] == before["total_reviews"]
    assert after["total_segments"] == before["total_segments"], (
        "the review left the listings but its segments still count")
    assert client.get("/reviews/" + rid).status_code == 404
    listed = client.get("/reviews").json()
    assert not any(x["review_id"] == rid for x in listed["reviews"])


def test_the_listing_total_agrees_with_the_rows_it_returns(client):
    """A total that counts rows the page omits is worse than either number."""
    listed = client.get("/reviews?limit=500").json()
    assert listed["total"] == len(listed["reviews"])


def test_withdrawal_keeps_the_row_rather_than_deleting_it(client):
    from travellens import submissions_db
    r = _review(client, "Kept On Disk")
    client.post("/reviews/{}/withdraw".format(r["review_id"]),
                headers={"X-Manage-Token": r["manage_token"]})
    with submissions_db.connection() as con:
        row = con.execute(
            "SELECT withdrawn_at FROM user_reviews WHERE review_id = ?",
            (r["review_id"],)).fetchone()
        segs = con.execute(
            "SELECT COUNT(*) FROM user_segments WHERE review_id = ?",
            (r["review_id"],)).fetchone()[0]
    assert row is not None, "the row was deleted, not withdrawn"
    assert row["withdrawn_at"], "no withdrawal timestamp"
    assert segs > 0, "segments were orphaned or removed"


def test_withdrawing_twice_is_not_an_error(client):
    r = _review(client, "Twice")
    h = {"X-Manage-Token": r["manage_token"]}
    first = client.post("/reviews/{}/withdraw".format(r["review_id"]), headers=h)
    second = client.post("/reviews/{}/withdraw".format(r["review_id"]), headers=h)
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["withdrawn"] is True
