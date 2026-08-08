from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from scripts.webp_usfm_html_candidate_equivalence import (
    VisibleTextParser,
    count_subsequence,
    find_member_by_basename,
)

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_PATH = (
    ROOT / "registry" / "experiments" / "webp-usfm-html-candidate-equivalence-20260808.json"
)


def test_visible_text_parser_excludes_script_and_style_content() -> None:
    parser = VisibleTextParser()
    parser.feed(
        "<html><style>hidden style words</style><body>Alpha <b>beta</b>"
        "<script>hidden script words</script> gamma</body></html>"
    )
    parser.close()

    assert parser.normalized_tokens() == ("alpha", "beta", "gamma")


def test_count_subsequence_counts_exact_normalized_sequence_occurrences() -> None:
    haystack = ["zero", "alpha", "beta", "one", "alpha", "beta", "two"]

    assert count_subsequence(haystack, ["alpha", "beta"]) == 2
    assert count_subsequence(haystack, ["beta", "alpha"]) == 0
    assert count_subsequence(haystack, []) == 0


def test_find_member_by_basename_is_path_and_case_tolerant() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("engwebp/MIC03.HTM", "fixture")
        archive.writestr("engwebp/index.htm", "index")
    buffer.seek(0)

    with zipfile.ZipFile(buffer) as archive:
        member = find_member_by_basename(archive, "MIC03.htm")

    assert member.filename == "engwebp/MIC03.HTM"


def test_registered_equivalence_result_preserves_scope_and_boundaries() -> None:
    experiment = json.loads(EXPERIMENT_PATH.read_text(encoding="utf-8"))

    assert experiment["summary"]["candidate_count"] == 4
    assert experiment["summary"]["exact_normalized_sequence_match_count"] == 4
    assert experiment["summary"]["all_candidates_exact_normalized_sequence_match"] is True
    assert all(
        item["exact_normalized_sequence_found"]
        and item["exact_usfm_sequence_occurrences_in_html_page"] == 1
        for item in experiment["candidate_results"]
    )
    assert experiment["interpretation"][
        "current_downloadable_html_agrees_with_current_usfm_at_all_candidate_loci_under_normalization"
    ] is True
    assert experiment["interpretation"]["whole_corpus_textual_equivalence_claimed"] is False
    assert experiment["interpretation"]["semantic_equivalence_claimed"] is False
    assert experiment["interpretation"]["meaning_change_claimed"] is False
    assert experiment["scripture_text_reported"] is False
    assert experiment["token_lists_reported"] is False
    assert experiment["corpus_bytes_retained"] is False
    assert experiment["publication_eligible"] is False
