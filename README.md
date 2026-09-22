# Personal Activity Analyzer

Google Maps Timelineなどからユーザー自身がエクスポートしたJSONを、
PythonとStreamlitでローカル解析するMVPです。Timeline APIから個人履歴を
直接取得したり、Google OAuth/APIキーを要求したりしません。

## 機能

- Timeline JSONのアップロードと、ベンダー固有形式に依存しない探索的解析
- GPSデータのDataFrame化、時刻順ソート、欠損・重複・異常座標・GPSジャンプ・異常速度の検出
- Haversine距離、徒歩距離からの推定歩数、METベースの推定消費カロリー
- 区間速度、総距離/総時間の平均速度、観測速度の単純平均
- Timelineに記録された移動手段の正規化（GPS速度だけでの断定はしない）
- 日付・表示期間・移動手段フィルター、PyDeckのPathLayer/ScatterplotLayer地図
- KPI、詳細DataFrame、UTF-8 CSVダウンロード
- pytestとGitHub Actionsによる自動テスト

歩数・カロリー・速度・移動手段はGPSと一般的な仮定からの推定値です。実際の
歩数計、ヘルスデータ、医学的な測定値とは一致しません。

## 技術スタック

Python 3.11、Streamlit、pandas、numpy、PyDeck、pytest。
依存関係はルートの`requirements.txt`に固定しています。

## ローカル環境構築と起動

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

サイドバーの「サンプルデータを使う」で、架空座標のみの
`data/sample_timeline.json`を使えます。

## Timelineデータ準備

スマートフォンまたはGoogle MapsのTimeline画面から、ユーザー自身のデータを
JSONとしてエクスポートし、アプリのファイルアップローダーへ渡してください。
入力に`semanticSegments`、`timelinePath`、`activitySegment`、`visit`などが
含まれる場合も、存在する時刻・座標・activity・distance・durationだけを
抽出します。存在しない値は欠損として扱い、架空のGPS行は生成しません。

## テスト

```powershell
python -m pytest -q
```

GitHubへのpushまたはPull Requestでは、`.github/workflows/tests.yml`がPython
3.11を構築し、依存関係をインストールしてpytestを実行します。

## Streamlit Community Cloud

1. ユーザー自身がGitHubへログインし、このリポジトリを公開またはアクセス可能な
   リポジトリとしてpushする。
2. ユーザー自身がStreamlit Community Cloudへログインし、GitHub連携をOAuthで
   承認する。
3. リポジトリ、`main`ブランチ、エントリーポイント`app.py`を選択して初回Deploy。
4. Python 3.11を指定し、依存関係はルートの`requirements.txt`から解決する。

このMVPはSecretsを使いません。必要になった場合だけCloudのSecrets画面で
設定し、`.streamlit/secrets.toml.example`を参照してください。実際の
`secrets.toml`、OAuth情報、APIキーは作成・保存・commitしないでください。

初回設定後は、次の流れで更新できます。

```text
コード修正 -> python -m pytest -> mainへpush
-> GitHub Actions -> 成功後にStreamlit Cloudが変更を検知して再デプロイ
```

GitHub/Streamlitへのログイン、OAuth承認、Secrets登録は人間が行う操作です。
アプリやこのプロジェクトは認証情報を自動操作しません。

## 個人情報保護

- TimelineはGitHubへ保存せず、サンプル以外の`data/*.json`は`.gitignore`対象です。
- アップロード内容はアプリのメモリ内で処理し、外部API・DBへ送信しません。
- ログやエラーメッセージへ緯度経度を出力しないでください。
- 実データをIssue、PR、スクリーンショット、テストfixtureへ貼り付けないでください。
- 公開前にアクセス制御、HTTPS、アップロードサイズ、保持期限を確認してください。

## GitHub公開前チェック

```powershell
python -m pytest -q
python -m pip install -r requirements.txt
python -m compileall app.py src tests
git status --short
git ls-files .streamlit/secrets.toml
Get-ChildItem -Recurse -File | Where-Object Length -gt 10MB
```

秘密情報・実Timeline・不要な大容量ファイルが一覧に出ないこと、requirementsの
インストールが成功すること、`secrets.toml`がGit管理対象外であることを確認して
からcommit/pushしてください。

## デプロイ前後チェックリスト

### デプロイ前

- [ ] pytestが成功する
- [ ] `app.py`のimportと`streamlit run app.py`が起動する
- [ ] サンプルJSONを解析できる
- [ ] 地図、移動手段フィルター、CSVダウンロードを確認する
- [ ] `.gitignore`、Secrets、Timeline、requirementsを確認する

### デプロイ後

- [ ] トップページが表示される
- [ ] JSONアップロードが動作する
- [ ] 分析対象日と表示期間を変更できる
- [ ] KPI、地図、移動手段フィルターが表示される
- [ ] 詳細データとCSVダウンロードが動作する
- [ ] `main`への変更が自動反映される

## 制限事項

GPS欠損の補間、実測歩数・心拍数、ユーザー認証、永続履歴保存、AI要約、
Google Maps Platform連携はMVPの対象外です。カロリーは活動時間とMETを使う
推定値であり、医療・労務・運動指導の判断には使用しないでください。
