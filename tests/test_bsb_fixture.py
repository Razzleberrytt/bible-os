from pathlib import Path
import hashlib
import json

from scripts.bsb_fixture import CORPUS_ID, fixture, stable_id

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fixtures" / "bsb" / "bsb-100.fixture.json"


def test_fixture_definition_is_explicitly_non_publishable():
    definition = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert definition["kind"] == "synthetic-relational-loader"
    assert definition["expected_records"] == 100
    assert definition["publication_policy"].startswith("Prohibited")
    assert "no biblical source text" in definition["text_policy"].lower()


def test_fixture_generates_exact_reference_range():
    definition, rows = fixture()
    assert len(rows) == 100
    assert rows[0]["reference"] == definition["first_reference"] == "Genesis 1:1"
    assert rows[-1]["reference"] == definition["last_reference"] == "Genesis 4:20"
    assert [row["sequence"] for row in rows] == list(range(1, 101))


def test_fixture_uses_only_synthetic_text_and_valid_hashes():
    _, rows = fixture()
    for row in rows:
        assert row["text"].startswith("Synthetic fixture text for Gen.")
        assert hashlib.sha256(row["text"].encode("utf-8")).hexdigest() == row["text_sha256"]


def test_fixture_ids_are_deterministic_and_unique():
    _, rows = fixture()
    for key in ["passage_id", "reference_id", "text_unit_id"]:
        values = [row[key] for row in rows]
        assert len(values) == len(set(values))
    assert stable_id("txt", f"text-unit|{CORPUS_ID}|Gen.1.1") == rows[0]["text_unit_id"]
