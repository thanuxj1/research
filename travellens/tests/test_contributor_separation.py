"""Contributor corrections and stories must never reach the figures.

Two new channels take content from anonymous visitors, and each is kept out of
the published numbers for its own reason.

Corrections are LABELS. This project has a documented near-miss where labels of
the wrong provenance were about to be reported as inter-annotator agreement
(src/travellens/agreement.py). A drive-by correction has no guideline behind
it, no second reader, and nobody to ask what they meant, so it is stored with
labelled_by='contributor' -- a value agreement.py refuses. These tests hold
that refusal in place.

Stories are MEDIA, and inherit the rule the news and video storyboard already
follows (tests/test_media_separation.py): displayed, never counted.
"""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from travellens import agreement  # noqa: E402


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """An API bound to a throwaway SQLite file, never the configured store."""
    os.environ["SUBMISSIONS_DATABASE_URL"] = ""
    from travellens import submissions_db
    submissions_db.SUBMISSIONS_DB = tmp_path_factory.mktemp("db") / "sep.db"
    from fastapi.testclient import TestClient
    from travellens.api import app
    return TestClient(app)


@pytest.fixture(scope="module")
def submitted(client):
    r = client.post("/analyse", json={
        "text": "The toilets were locked and the road was full of potholes.",
        "destination": "Separation Test", "district": "Kandy"})
    assert r.status_code == 200
    return r.json()


# ------------------------------------------------------------- corrections
def test_corrections_carry_a_provenance_agreement_refuses(client, submitted, tmp_path):
    client.post("/corrections", json={
        "review_id": submitted["review_id"], "seg_index": 0,
        "aspect": "facilities", "human_verdict": "praise"})
    listed = client.get("/corrections").json()
    assert listed["provenance"] == "contributor"

    # The real guard: write those labels out in the shape a labels file takes
    # and confirm agreement.py will not compute kappa from them.
    sheet = tmp_path / "contributor_labels.csv"
    pd.DataFrame([{"segment_id": c["correction_id"],
                   "facilities": c["human_verdict"],
                   "labelled_by": listed["provenance"]}
                  for c in listed["corrections"]]).to_csv(sheet, index=False)
    with pytest.raises(agreement.MachineLabelsRefused):
        agreement.load_labels(sheet)


def test_a_correction_does_not_move_any_published_figure(client, submitted):
    before = client.get("/stats").json()
    for verdict in ("praise", "factual", "not_about_this"):
        r = client.post("/corrections", json={
            "review_id": submitted["review_id"], "seg_index": 0,
            "aspect": "roads_access", "human_verdict": verdict})
        assert r.status_code == 201
    after = client.get("/stats").json()
    assert after["per_aspect"] == before["per_aspect"], (
        "a correction changed a complaint rate -- corrections are a queue, "
        "not an edit")
    assert after["total_reviews"] == before["total_reviews"]


def test_a_correction_records_what_the_machine_said(client, submitted):
    r = client.post("/corrections", json={
        "review_id": submitted["review_id"], "seg_index": 0,
        "aspect": "scenery", "human_verdict": "not_about_this"})
    # Stored as a PAIR. A bare human opinion with no machine verdict beside it
    # cannot be read later as agreement or disagreement.
    assert r.json()["machine_verdict"] == "not_tagged"
    assert r.json()["human_verdict"] == "not_about_this"


def test_correction_rejects_an_unknown_aspect_or_verdict(client, submitted):
    bad_aspect = client.post("/corrections", json={
        "review_id": submitted["review_id"], "seg_index": 0,
        "aspect": "vibes", "human_verdict": "praise"})
    assert bad_aspect.status_code == 422
    bad_verdict = client.post("/corrections", json={
        "review_id": submitted["review_id"], "seg_index": 0,
        "aspect": "safety", "human_verdict": "meh"})
    assert bad_verdict.status_code == 422


def test_correction_on_a_segment_that_does_not_exist_is_404(client, submitted):
    r = client.post("/corrections", json={
        "review_id": submitted["review_id"], "seg_index": 99,
        "aspect": "safety", "human_verdict": "praise"})
    assert r.status_code == 404


# ----------------------------------------------------------------- stories
def test_a_story_is_never_segmented_tagged_or_counted(client):
    before = client.get("/stats").json()
    r = client.post("/stories", json={
        "title": "Two days walking around Ella",
        "body": "The road up was rough and the toilets at the top were locked. "
                "Beautiful all the same. " * 3,
        "destination": "Ella", "district": "Badulla"})
    assert r.status_code == 201
    after = client.get("/stats").json()
    # The body contains language that WOULD tag roads, facilities and scenery
    # if it ever reached the analyser. Nothing moved.
    assert after == before, "a story reached the counts"


def test_story_urls_must_be_http(client):
    for bad in ("javascript:alert(1)", "data:text/html,<script>"):
        r = client.post("/stories", json={
            "title": "bad link", "body": "x" * 40, "url": bad})
        assert r.status_code == 422, "{} was accepted".format(bad)


def test_story_ids_cannot_collide_with_review_or_media_ids(client):
    r = client.post("/stories", json={"title": "prefix check", "body": "x" * 40})
    story_id = r.json()["story_id"]
    assert story_id.startswith("sty_")
    # usr_ is a submitted review, m_ is a collected media item.
    assert not story_id.startswith(("usr_", "m_"))


def test_aggregate_never_reads_the_contributor_tables():
    """The separation is structural, not a convention."""
    src = (ROOT / "src" / "travellens" / "aggregate.py").read_text(encoding="utf-8")
    for table in ("user_stories", "user_corrections"):
        assert table not in src, "aggregate.py references {}".format(table)


def test_stats_counts_no_contributor_table():
    api_src = (ROOT / "src" / "travellens" / "api.py").read_text(encoding="utf-8")
    stats = api_src.split("def submission_stats(")[1].split("\n@app.")[0]
    for table in ("user_stories", "user_corrections"):
        assert table not in stats, "/stats reads {}".format(table)
