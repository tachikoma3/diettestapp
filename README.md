# Personal Activity Analyzer

Google Maps Timelineなどからユーザー自身がエクスポートしたJSONを、PythonとStreamlitで解析するMVPです。

## 画面

- **HOME**: アプリの概要とプライバシーに関する案内
- **ACTIVITY ANALYZER**: Timeline JSONのアップロード、KPI、移動軌跡、CSV出力
- **ABOUT**: 推定値とデータ取り扱いに関する説明

## 機能

- Timeline JSONのアップロードとベンダー固有形式に依存しない探索的解析
- GPSデータのDataFrame化、時刻順ソート、欠損・重複・異常座標・GPSジャンプ・異常速度の検出
- Haversine距離、徒歩距離からの推定歩数、METベースの推定消費カロリー
- 区間速度、総距離/総時間の平均速度、観測速度の単純平均
- Timelineに記録された移動手段の正規化
- 日付・表示期間・移動手段フィルター、PyDeckのPathLayer/ScatterplotLayer地図
- KPI、詳細DataFrame、UTF-8 CSVダウンロード
- pytestとGitHub Actionsによる自動テスト

## ローカル環境構築と起動

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

サイドバーの **ACTIVITY ANALYZER** を選択すると、サンプルデータまたは自分のTimeline JSONを解析できます。

## Streamlit Community Cloud

Streamlit Community Cloudでは、リポジトリの`main`ブランチと`app.py`をエントリーポイントに指定してデプロイできます。GitHub Pagesから埋め込む場合は、デプロイ後に発行されたURLへ`?embed=true`を付けてiframeの`src`に指定してください。

このMVPはSecretsを使いません。実際のTimeline、`secrets.toml`、OAuth情報、APIキーは作成・保存・commitしないでください。

## テスト

```powershell
python -m pytest -q
```

## 個人情報保護

- TimelineはGitHubへ保存せず、サンプル以外の`data/*.json`は`.gitignore`対象です。
- アップロード内容はアプリのメモリ内で処理し、外部API・DBへ送信しません。
- 実データをIssue、PR、スクリーンショット、テストfixtureへ貼り付けないでください。
- 公開前にアクセス制御、HTTPS、アップロードサイズ、保持期限を確認してください。

歩数・カロリー・速度はGPSと一般的な仮定からの推定値です。医療・労務・運動指導の判断には使用しないでください。
