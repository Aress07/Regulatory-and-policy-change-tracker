from regtracker.common.text import normalize_text, sha256_text


def test_normalize_collapses_whitespace_and_quotes() -> None:
    raw = "  The\u00a0controller\u2019s   \u201cduty\u201d\n applies. "
    assert normalize_text(raw) == 'The controller\'s "duty" applies.'


def test_hash_ignores_cosmetic_differences() -> None:
    a = "Article  5\u00a0applies."
    b = "Article 5 applies."
    assert sha256_text(a) == sha256_text(b)


def test_hash_detects_real_changes() -> None:
    assert sha256_text("fine of 10 million") != sha256_text("fine of 20 million")
