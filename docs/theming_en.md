[简体中文](theming.md) | English

# Theme internals (MinePick Launcher)

> This document is also available in [Simplified Chinese](theming.md).

This document explains how the interface theme is organised, what can be customised, and **how to add a new customisation option**.

## 1. Three-layer structure

```
gui/resources/style.qss          dark stylesheet (contains __placeholders__)
gui/resources/style_light.qss    light stylesheet
gui/theme.py                     read the stylesheet → substitute placeholders → apply to QApplication
launcher/config.py               user choices (theme / accent_color / ui_font / ui_radius)
gui/pages/settings_page.py       settings-page controls (changes are saved immediately, no Save button)
```

The stylesheet itself **contains no final colours**: colours, fonts and corner radii are all placeholders, substituted at runtime by `theme.apply_theme()`.

## 2. Placeholder reference

| Placeholder | Meaning | Decided by |
|---|---|---|
| `__ACCENT__` | the accent colour itself (outlines, pill backgrounds, progress bars — any place that **does not carry white text**) | `accent_color` (empty = theme default) |
| `__ACCENT_BUTTON__` | the fill colour that carries white text: the accent colour is **automatically darkened to WCAG AA 4.5:1** | as above, derived by `theme.readable_fill()` |
| `__ACCENT_BUTTON_HOVER__` / `__ACCENT_BUTTON_PRESS__` | hover / pressed steps of that fill colour | as above |
| `__ACCENT_HOVER__` / `__ACCENT_PRESS__` | hover / pressed steps of the accent colour itself | as above |
| `__ACCENT_SEL__` / `__ACCENT_SEL_TEXT__` | selection background and its text colour in lists / tables | as above |
| `__ACCENT_SOFT__` | background of the selected pill in the sidebar | as above |
| `__ACCENT_TINT__` | pale green hover background in the light theme | as above |
| `__FONT__` | interface font family (with Segoe UI / Microsoft YaHei fallbacks) | `ui_font` (empty = Microsoft YaHei UI) |
| `__RADIUS_XS__` / `__RADIUS_SM__` / `__RADIUS_LG__` | small / medium / large corner radius | `ui_radius` (compact / default / round) |
| `__DOWN_ARROW__` / `__CHECK__` | absolute paths to the dropdown-arrow and checkbox-tick PNGs (QSS `url()` cannot resolve relative paths once packaged) | fixed resources |

## 3. What you can customise

| Setting | Values | Notes |
|---|---|---|
| Theme | `system` / `dark` / `light` | on Windows, `system` reads the `AppsUseLightTheme` registry value; other platforms fall back to dark |
| Accent colour | any `#rrggbb`, or empty | empty uses the theme default (dark `#35a06a` / light `#2f9e6f`); the settings page has 8 preset swatches and the system colour picker |
| Interface font | any installed font family, or empty | empty = Microsoft YaHei UI; common fonts are pinned to the top of the dropdown, and typing filters the list as you go |
| Corner radius | `compact` / `default` / `round` | corresponding to (3,4,6) / (4,6,8) / (6,9,12) pixels |

## 4. How to add a new customisation option

1. **Configuration**: add a field to `LauncherConfig` in `launcher/config.py` (for example `ui_density`);
2. **Stylesheet**: write the values that should change with it as new placeholders, for example `padding: __DENSITY_PAD__;`;
3. **Theme module**: add a "value → number" mapping function in `gui/theme.py` (see `radius_scale()`), and perform the substitution in `apply_theme()`;
4. **Settings page**: add the control in `gui/pages/settings_page.py` (see the "Corner radius" row), and note that:
   - the new control must be added to `_connect_autosave()`; the settings page **saves as soon as you change something**, and there is no Save button;
   - the wording goes through i18n (`gui/i18n.py` + `gui/i18n_langs.py`; the key set of all 9 languages must be identical, and a test enforces this);
5. **Verification**: run `python tools/ui_regression.py` (tests + lint + contrast/overflow/high-DPI + corner audit + screenshots).

## 5. A few hard rules

- **Do not** hard-code colours/fonts/corner radii in the stylesheet — always use placeholders, otherwise switching theme or accent colour will miss a spot;
- a fill colour that carries white text must go through `readable_fill()`, which guarantees a contrast of ≥ 4.5:1 (`tools/audit_ui_quality.py` checks this);
- hover scrollbars are **transparent normally and appear only when the pointer moves in** (`attach_hover_scrollbar`); do not give them a fixed size in the QSS, otherwise it inflates the minimum height of the scroll area (this once turned a 600 px window into 618 px);
- unequal border widths plus a corner radius overflow (a Qt quirk): when you need "a thick line on the left", make the left corners square, as in `QListWidget#sidebar::item`.
