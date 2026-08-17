"""多语言完整性测试：key 集合一致、占位符一致、系统语言映射。"""

from gui import i18n
from launcher import i18n as ci18n


def test_all_languages_have_complete_keys() -> None:
    """每种语言的 key 集合必须与英文完全一致（防漏翻）。"""
    codes = [code for code, _name in i18n.UI_LANGUAGES]
    base = set(i18n.TRANSLATIONS["en_us"])
    for code in codes:
        assert set(i18n.TRANSLATIONS[code]) == base, f"gui {code} key mismatch"
    cbase = set(ci18n.CORE_TRANSLATIONS["en_us"])
    for code in codes:
        assert set(ci18n.CORE_TRANSLATIONS[code]) == cbase, f"core {code} key mismatch"


def test_placeholder_counts_match_zh() -> None:
    """译文中的 {} 占位符数量必须与简中一致。"""
    codes = [code for code, _name in i18n.UI_LANGUAGES]
    zh = i18n.TRANSLATIONS["zh_cn"]
    for code in codes:
        table = i18n.TRANSLATIONS[code]
        for key, value in table.items():
            assert value.count("{}") == zh[key].count("{}"), f"{code} {key}: {value}"


def test_detect_system_language_mapping() -> None:
    assert i18n.detect_system_language("zh_CN") == "zh_cn"
    assert i18n.detect_system_language("zh_TW") == "zh_tw"
    assert i18n.detect_system_language("zh-HK") == "zh_tw"  # 香港繁体也映射繁中
    assert i18n.detect_system_language("en_GB") == "en_us"
    assert i18n.detect_system_language("en-US") == "en_us"
    assert i18n.detect_system_language("ja_JP") == "ja_jp"
    assert i18n.detect_system_language("ko_KR") == "ko_kr"
    assert i18n.detect_system_language("ru_RU") == "ru_ru"
    assert i18n.detect_system_language("fr_FR") == "fr_fr"
    assert i18n.detect_system_language("es_MX") == "es_es"
    assert i18n.detect_system_language("de_DE") == "de_de"
    assert i18n.detect_system_language("pl_PL") == "zh_cn"  # 不支持的语言回退简中
    assert i18n.detect_system_language("C") == "zh_cn"
    assert i18n.detect_system_language("") == "zh_cn"
