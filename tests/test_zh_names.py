"""Unit tests for launcher/mods/zh_names.py: Chinese name table loading, CJK detection, local search."""

from launcher.mods.zh_names import has_cjk, search_local, zh_name, zh_names


def test_zh_names_loads_dict() -> None:
    table = zh_names()
    assert isinstance(table, dict)
    assert all(k and v for k, v in table.items())


def test_has_cjk() -> None:
    assert has_cjk("钠") is True
    assert has_cjk("优化 钠") is True
    assert has_cjk("sodium") is False
    assert has_cjk("") is False


def test_search_local_roundtrip() -> None:
    """Any entry in the table: it can find itself by both its Chinese name and slug."""
    assert search_local("") == []
    for slug, name in list(zh_names().items())[:20]:
        assert slug in search_local(slug), slug
        assert slug in search_local(name), name


def test_zh_name_unknown_returns_empty() -> None:
    assert zh_name("__definitely_not_a_mod__") == ""

