[English](README.md) | [简体中文](README_zh.md) | [繁體中文](README_zh_TW.md) | [日本語](README_ja.md) | [한국어](README_ko.md) | [Русский](README_ru.md) | [Français](README_fr.md) | [Español](README_es.md) | [Deutsch](README_de.md)

# MinePick Launcher — UI Trial

Python + PySide6 で作られたポータブルな Minecraft ランチャー：Microsoft アカウントとオフラインアカウント、バージョンの
インストール、Modrinth と CurseForge のリソース、Fabric/Forge/NeoForge/Quilt ローダー、分離された
インスタンス — 単一のポータブル EXE としてパッケージ化されています。

**このリポジトリはインターフェースのトライアルライン（バージョン 0.1.2）です。** 本体プロジェクトと同じ
ランチャー機能に、以下で説明するインターフェースの刷新を加えたもので、**GUI ビルドのみ**を提供します —
ここに CLI 実行ファイルはありません。

> 本体のランチャー: [xltxdocs/MinePick_Launcher](https://github.com/xltxdocs/MinePick_Launcher)

## スクリーンショット

<table>
  <tr>
    <td><img src="docs/screenshots/launch_en.png" width="480" alt="起動ページ"/></td>
    <td><img src="docs/screenshots/versions_en.png" width="480" alt="バージョンページ"/></td>
  </tr>
  <tr>
    <td align="center"><sub>起動</sub></td>
    <td align="center"><sub>バージョン</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/instances_mods_en.png" width="480" alt="インスタンスとローカル Mod 管理"/></td>
    <td><img src="docs/screenshots/settings_en.png" width="480" alt="設定"/></td>
  </tr>
  <tr>
    <td align="center"><sub>インスタンスとローカル Mod 管理</sub></td>
    <td align="center"><sub>設定（インターフェースのカスタマイズ）</sub></td>
  </tr>
</table>

## インターフェース（このラインでの変更点）

- **初回起動ウィザード（ウィンドウ内）** — ウェルカムフローは別ダイアログではなくメインウィンドウ内の
  オーバーレイ（左にステップレール、右にコンテンツ、下にアクションバー）で表示され、完了すると
  フェードアウトして消えます
- **カスタムウィンドウフレーム** — タイトルバーはランチャー自身が描画するため、装飾がテーマと
  一致します。ウィンドウアイコンはどの場面でも、どのサイズでもピッケルのデザインです
- **カスタマイズ可能な外観** — アクセントカラー（任意の 16 進数値、8 種類のプリセット、またはシステムの
  カラーピッカー）、UI フォント（インストール済みのすべてのファミリー、よく使うものを固定表示、入力で絞り込み）、
  角の丸み（コンパクト / 標準 / 丸め）、テーマ（ダーク / ライト / システムに合わせる）
- **より分かりやすいレイアウト** — すべてのページに 1 行の説明付きページヘッダー、サイドバー上部の
  ブランドブロック、全ページで統一された余白スケール、検索フィールドの虫めがねアイコン
- **落ち着いた操作感** — スクロールバーはポインターがリスト内にあるときだけ表示され、フォーカス枠は
  キーボード操作時のみ表示、ページ切り替え時の短いフェード、テーブルの列幅を記憶、
  ヘッダーをクリックすると並び替え
- **読み取りやすい状態表示** — ボタンに優先度（プライマリ / セカンダリ / 枠線付きの危険操作）、ステータス
  メッセージは重要度に応じて色分け、空のリストには次に行う操作を説明
- **既定でアクセシブル** — すべてのテキストと背景の組み合わせが WCAG AA のコントラストを満たし
  （アクセント上の白文字は自動的に暗くされます）、インターフェースは 9 言語で利用できます

## ランチャーの機能

### アカウント
- デバイスコードフローによる Microsoft ログイン（認証ページが自動で開き、コードはクリップボードに
  コピーされます）、ポーリング状況のリアルタイム表示
- オフラインモード、ワンクリックで切り替えられる複数アカウント一覧、スキンアバター、トークンの自動更新
- 任意のトークン暗号化（cryptography Fernet + パスワード、`MCLAUNCHER_TOKEN_PASSWORD` に対応）

### バージョンと Java
- カテゴリタブ付きの公式バージョン一覧（リリース版 / スナップショット / エイプリルフール版 / レガシー）、
  「最新リリース」と「最新スナップショット」のカード、名前検索、ワンクリックでのインストールとアンインストール、バージョン詳細
- バージョン分離：各バージョンが独自のセーブデータ / Mod / 設定を保持
- Java 要件のマッピング（1.16.5→8、1.17–1.20.4→17、1.20.5–1.21.11→21、26.1+→25）、Adoptium の
  自動ダウンロードとランタイムマネージャー

### 起動とインスタンス
- Mod 数と空きメモリに基づくメモリ提案、カスタム JVM 引数、サーバーへの直接接続、ゲームの言語、
  ログのリアルタイム表示、「ゲーム起動後」の動作、ワーキングセットの解放
- メモ、名前変更、インポート/エクスポートを備えた分離インスタンスと、インスタンスごとのローカル Mod
  管理（Fabric / Quilt / NeoForge / Forge / mcmod.info の jar メタデータを読み取り、有効/無効の切り替え、検索と絞り込み、ドラッグ＆ドロップ）

### リソース
- **Modrinth** と **CurseForge** の Mod、リソースパック、シェーダー、モッドパック、タブごとの人気
  Top 30、キーワード検索（中国語コミュニティ名を含む）、ワンクリックインストール、`.mrpack` モッドパックのインストール

## ダウンロードと使い方

Releases ページから `MinePick_UI_Trial.exe` を入手してダブルクリックするだけです — インストーラーもコンソール
ウィンドウもありません。初回起動時には EXE の隣に `config/` フォルダーが作成されるため、設定・アカウント・
インスタンスは 1 つのフォルダー内に収まります。

すべての設定はアプリ内で行います：**設定は即時反映され、保存ボタンはありません。**

> このビルドは自己署名証明書（WDNDXLTX）で署名されているため、他のマシンでは SmartScreen が
> 不明な発行元として警告を表示することがあります — 「詳細情報 → 実行」を選択してください。

## 開発

```powershell
pip install -r requirements-dev.txt
python -m gui                # run the GUI
pytest -q                    # tests (240+)
ruff check launcher gui tests
```

ビルドと署名: `pyinstaller build_exe.spec` → `scripts/sign_exe.ps1`（`docs/code_signing.md` を参照）。
この spec は単一の GUI EXE を生成します（ビルドの前提条件は `docs/github_release.md` に記載されています）。

コマンド 1 つでインターフェースをチェック（テスト + lint + コントラスト/オーバーフロー/高 DPI + 角の検査 + スクリーンショット）:

```powershell
python tools/ui_regression.py            # add --quick to skip the screenshots
```

テーマの内部構造（プレースホルダー、カスタマイズ用フック、新しいオプションの追加方法）: `docs/theming.md`。

## ライセンス

GPL-3.0-only — [LICENSE](LICENSE) を参照してください。各リリースに同梱されるソースパッケージ（`Source_code.zip`）が
GPL のソース配布要件を満たします。

## 関連プロジェクト

- [MinePick Launcher](https://github.com/xltxdocs/MinePick_Launcher) — 本体のランチャー（GUI + CLI）
- [MinePick Launcher Revision](https://github.com/TheDarkLord234/MinePick_Launcher_Revision) — コミュニティメンバーによる改訂版
