# 主题机制（MinePick Launcher）

本文说明界面主题是怎么组织的、有哪些可调项、以及**怎么再加一个可调项**。

## 一、三层结构

```
gui/resources/style.qss          深色样式表（含 __占位符__）
gui/resources/style_light.qss    浅色样式表
gui/theme.py                     读取样式表 → 替换占位符 → 应用到 QApplication
launcher/config.py               用户选择（theme / accent_color / ui_font / ui_radius）
gui/pages/settings_page.py       设置页控件（改动即保存，无保存按钮）
```

样式表本身**不含最终颜色**：颜色、字体、圆角都是占位符，由 `theme.apply_theme()` 在运行时代入。

## 二、占位符一览

| 占位符 | 含义 | 由谁决定 |
|---|---|---|
| `__ACCENT__` | 强调色本体（描边、胶囊底、进度条等**不承载白字**的地方） | `accent_color`（留空=主题默认） |
| `__ACCENT_BUTTON__` | 承载白字的填充色：由强调色**自动加深到 WCAG AA 4.5:1** | 同上，`theme.readable_fill()` 推导 |
| `__ACCENT_BUTTON_HOVER__` / `__ACCENT_BUTTON_PRESS__` | 上述填充色的悬停/按下档 | 同上 |
| `__ACCENT_HOVER__` / `__ACCENT_PRESS__` | 强调色本体的悬停/按下档 | 同上 |
| `__ACCENT_SEL__` / `__ACCENT_SEL_TEXT__` | 列表/表格选中底色与其文字色 | 同上 |
| `__ACCENT_SOFT__` | 侧边栏选中胶囊底色 | 同上 |
| `__ACCENT_TINT__` | 浅色主题下的淡绿悬停底 | 同上 |
| `__FONT__` | 界面字体族（含 Segoe UI / 微软雅黑兜底） | `ui_font`（留空=微软雅黑 UI） |
| `__RADIUS_XS__` / `__RADIUS_SM__` / `__RADIUS_LG__` | 小/中/大圆角 | `ui_radius`（compact / default / round） |
| `__DOWN_ARROW__` / `__CHECK__` | 下拉箭头、复选框对勾 PNG 的绝对路径（QSS 的 `url()` 在打包后解析不了相对路径） | 固定资源 |

## 三、可以调什么

| 设置项 | 取值 | 说明 |
|---|---|---|
| 界面主题 | `system` / `dark` / `light` | `system` 在 Windows 读注册表 `AppsUseLightTheme`，其它平台回退深色 |
| 强调色 | 任意 `#rrggbb`，或留空 | 留空用主题默认（深色 `#35a06a` / 浅色 `#2f9e6f`）；设置页有 8 个预设色块和系统取色器 |
| 界面字体 | 任意已安装字体族，或留空 | 留空=微软雅黑 UI；下拉里常用字体置顶，输入即过滤 |
| 界面圆角 | `compact` / `default` / `round` | 对应 (3,4,6) / (4,6,8) / (6,9,12) 像素 |

## 四、再加一个可调项怎么做

1. **配置**：在 `launcher/config.py` 的 `LauncherConfig` 加字段（例如 `ui_density`）；
2. **样式表**：把要随它变化的值写成新占位符，例如 `padding: __DENSITY_PAD__;`；
3. **主题模块**：在 `gui/theme.py` 增加"取值 → 数值"的映射函数（参考 `radius_scale()`），并在 `apply_theme()` 里做替换；
4. **设置页**：在 `gui/pages/settings_page.py` 加控件（参考「界面圆角」那一行），注意：
   - 新控件要加进 `_connect_autosave()`，设置页是**改完即存**，没有保存按钮；
   - 文案走 i18n（`gui/i18n.py` + `gui/i18n_langs.py`，9 种语言 key 集合必须一致，有测试兜底）；
5. **验证**：跑 `python tools/ui_regression.py`（测试 + lint + 对比度/溢出/高 DPI + 角部审计 + 出图）。

## 五、几条硬规矩

- **不要**在样式表里写死颜色/字体/圆角——一律用占位符，否则换主题/换色会漏掉一处；
- 承载白字的填充色必须走 `readable_fill()`，保证对比度 ≥ 4.5:1（`tools/audit_ui_quality.py` 会检查）；
- 滚动条**平时透明、鼠标移入才显示**（`attach_hover_scrollbar`），不要在 QSS 里给它固定尺寸，否则会把滚动区域的最小高度撑大（曾经因此让窗口从 600 变成 618）；
- 边框宽度不一致 + 圆角会溢出（Qt 特性）：需要"左边一条粗线"时，把左角设为直角，如 `QListWidget#sidebar::item`。
