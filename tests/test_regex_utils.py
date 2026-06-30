from utils.RegexUtils import array_to_lines, strip_html


def test_strip_html_removes_tags() -> None:
    assert strip_html("<p>Hello</p>") == "Hello"


def test_strip_html_removes_nested_tags() -> None:
    assert strip_html("<b><i>text</i></b>") == "text"


def test_strip_html_trims_whitespace() -> None:
    assert strip_html("  <b>text</b>  ") == "text"


def test_strip_html_plain_text_unchanged() -> None:
    assert strip_html("no tags here") == "no tags here"


def test_array_to_lines_joins_all() -> None:
    assert array_to_lines(["a", "b", "c"]) == "a\nb\nc"


def test_array_to_lines_with_limit() -> None:
    assert array_to_lines(["a", "b", "c"], paragraphs=2) == "a\nb"


def test_array_to_lines_empty() -> None:
    assert array_to_lines([]) == ""


def test_array_to_lines_limit_zero() -> None:
    assert array_to_lines(["a", "b", "c"], paragraphs=0) == ""
