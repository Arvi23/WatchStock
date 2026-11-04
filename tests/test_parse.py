import pytest

from watchstock.analysis import parse_llm_json


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        'Here you go:\n{"a": 1}\nHope that helps',
    ],
)
def test_parse_llm_json_tolerates_wrappers(text):
    assert parse_llm_json(text) == {"a": 1}


@pytest.mark.parametrize("text", ["", "no json", "[1, 2]"])
def test_parse_llm_json_rejects_non_objects(text):
    with pytest.raises(ValueError):
        parse_llm_json(text)
