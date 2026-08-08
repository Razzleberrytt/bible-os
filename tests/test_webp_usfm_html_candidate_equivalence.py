from __future__ import annotations

import io
import zipfile

from scripts.webp_usfm_html_candidate_equivalence import (
    VisibleTextParser,
    count_subsequence,
    find_member_by_basename,
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
