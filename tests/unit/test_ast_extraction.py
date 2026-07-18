from __future__ import annotations

from hermes_semantic_diff_weaver.ast_diff import extract_symbols


def test_extracts_nested_async_decorated_symbols() -> None:
    source = """
class Service:
    @classmethod
    async def fetch(cls, value: int = 3) -> dict[str, int]:
        def normalize(item):
            return item + 1
        if value < 5:
            return {"value": normalize(value)}
        raise ValueError(value)
"""
    symbols = {item.qualified_name: item for item in extract_symbols(source)}
    assert {"Service", "Service.fetch", "Service.fetch.normalize"} <= symbols.keys()
    assert symbols["Service.fetch"].kind == "async_function"
    assert symbols["Service.fetch"].default_map == {"value": "3"}
    assert symbols["Service.fetch"].decorators == ("classmethod",)
    assert symbols["Service.fetch"].features["comparisons"]
    assert symbols["Service.fetch"].features["raises"]


def test_docstrings_and_formatting_do_not_change_fingerprint() -> None:
    first = extract_symbols('def value(x):\n    """old"""\n    return x + 1\n')[0]
    second = extract_symbols('def value( x ):\n    """new docs"""\n    return (x + 1)\n')[0]
    assert first.fingerprint == second.fingerprint


def test_parsing_does_not_execute_source() -> None:
    symbols = extract_symbols('raise RuntimeError("must not execute")\ndef safe():\n    return 1\n')
    assert any(item.qualified_name == "safe" for item in symbols)
