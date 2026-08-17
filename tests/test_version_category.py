from launcher.meta.manifest import APRIL_FOOLS_IDS, version_category


def test_april_fools_ids_known() -> None:
    for vid in ("2.0", "15w14a", "1.RV-Pre1", "3D Shareware v1.34", "20w14infinite",
                "22w13oneblockatatime", "23w13a_or_b", "24w14potato", "25w14craftmine",
                "26w14a"):
        assert vid in APRIL_FOOLS_IDS


def test_version_category_release_snapshot() -> None:
    assert version_category("1.21.8", "release") == "release"
    assert version_category("25w14a", "snapshot") == "snapshot"


def test_version_category_april_fools_overrides_type() -> None:
    # april-fools versions are categorized by id, ignoring the release/snapshot type in the manifest
    assert version_category("24w14potato", "snapshot") == "april_fools"
    assert version_category("2.0", "release") == "april_fools"
    assert version_category("26w14a", "snapshot") == "april_fools"
    assert version_category("20w14infinite", "snapshot") == "april_fools"
    assert version_category("22w13oneblockatatime", "snapshot") == "april_fools"


def test_version_category_legacy() -> None:
    assert version_category("b1.7.3", "old_beta") == "old_beta"
    assert version_category("a1.0.4", "old_alpha") == "old_alpha"
