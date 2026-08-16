from launcher.mods.models import ModInfo


def test_mod_info_defaults():
    m = ModInfo(slug="sodium", title="Sodium")
    assert m.depends == []
    assert m.optional_depends == []


def test_mod_info_with_deps():
    m = ModInfo(
        slug="iris",
        title="Iris",
        depends=["sodium"],
        optional_depends=["indium"],
    )
    assert m.depends == ["sodium"]
    assert m.optional_depends == ["indium"]
