# RLMResearchPlanner

`RLMResearchPlanner` は、『ロードモバイル』の研究状況、前提研究、研究時間、必要資源を確認するための非公式Windowsデスクトップツールです。

本ツールはIGGおよびゲーム運営とは関係ありません。ゲーム名、商標、その他の権利は各権利者に帰属します。

## バージョン

- Windows版: `v0.0.6`
- モバイルPWA版: `v0.0.3`

## 主な機能

- 16分野・399項目の研究ツリーを文字ベースで表示
- 現在レベル、現在効果、次レベル効果をカード内に表示
- 現在レベルを数値入力、スライダー、左右の1段階変更ボタンから設定
- 目標研究までの未達前提を遡り、必要時間・資源・パワーを集計
- 研究計画を完了として反映すると、目標研究と未達の前提研究を必要レベルへ一括更新
- 複数の研究計画をタスクとして保存し、残り時間と必要資源を比較
- 計画内の各研究を1件ずつ完了として反映
- 資源数を通常表記またはK/M/B/Tの短縮表記で表示
- 前提研究とアカデミー条件を含めて判定する「即時終了のみ」フィルター
- 現在開始できる次レベルを所要時間の短い順に表示し、研究名からツリーへ移動
- `Lords Mobile PC` の表示ウィンドウを単発キャプチャし、研究レベルをOCR入力
- 課金パック内の通常・研究・訓練スピードアップと付属ジェムをOCR／手動入力で換算
- 日本語・英語UI
- GitHub Releasesを利用した更新確認と、SHA-256検証付き自動更新
- プレイヤー設定のローカル保存とJSONバックアップ／復元

## ダウンロード

[Releases](https://github.com/rrryutaro/RLMResearchPlanner/releases) から `RLMResearchPlanner.exe` をダウンロードしてください。設定とプレイヤーデータはexeと同じフォルダへ保存されます。

WindowsのSmartScreenが未署名アプリとして警告する場合があります。公開されたSHA-256ファイルとダウンロードしたexeのハッシュを照合できます。

## モバイル版（PWA）

[RLM Research Planner PWA](https://rrryutaro.github.io/RLMResearchPlanner/) は、スマートフォンやタブレットのブラウザーから利用できます。ブラウザーのホーム画面への追加機能を使うと、通常のアプリに近い形で起動できます。

下記の公開URLまたはQRコードからアクセスしてください。

**公開URL:** https://rrryutaro.github.io/RLMResearchPlanner/

<p align="center">
  <img src="tools/RLMResearchPlannerPWA/docs/qr.png" alt="QR code to RLM Research Planner PWA" width="200" />
</p>

モバイル版はOCRやゲーム画面の取得を行わず、研究レベル、VIPレベル、研究速度などを手動で入力します。入力内容は端末のブラウザー内に保存されるため、必要に応じてプレイヤータブからバックアップしてください。

モバイルPWA版v0.0.3では、使用する資源だけの表示、資源数の通常／短縮表記、複数の研究計画を比較できる登録タスク、研究ごとの完了反映に対応しました。

## OCRと安全性

- 画面取得はユーザーがボタンを押した時だけ実行します。
- ゲームプロセスへのアタッチ、メモリ読み取り、DLL注入、メモリ走査は行いません。
- ゲーム操作を自動化しません。
- キャプチャ画像を自動保存・外部送信しません。
- OCRにはWindows標準OCRを優先して使用し、利用可能な場合だけTesseractをフォールバックとして使用します。
- OCRは誤認識する可能性があるため、反映内容を確認してください。

## ソースからの実行

Python 3.11以降が必要です。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -B main.py
```

exeを作成する場合は、開発依存関係を追加します。

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
.\build_exe.bat
```

## データとプライバシー

- 設定は `settings.json`、プレイヤーデータは `user_data/player.sqlite3` に保存します。
- これらのファイルはGit管理対象外です。
- 研究データには各項目の参照元URL、確認日、確認範囲を保持しています。
- ゲーム画像、ゲーム内フォント、音声、クライアントから抽出した素材は同梱していません。

## ライセンス

アプリケーションのソースコードは [MIT License](LICENSE) で公開しています。研究データの出典、Qt/PySide6、PyInstallerなど配布物の第三者ライセンスは [THIRD_PARTY_NOTICES.md](licenses/THIRD_PARTY_NOTICES.md) を参照してください。
