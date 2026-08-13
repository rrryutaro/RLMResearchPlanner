# 翻訳ファイルの作成と読み込み

[English](../en-US/translation-files.md) | 日本語 | [各ファイルの違い](data-files.md)

翻訳ファイルは、RLMResearchPlannerの表示言語を追加・修正するJSONです。PC版とモバイル版で同じファイルを利用でき、プレイヤー設定、研究レベル、資源、タスクは変更しません。

OCRの認識言語は日本語・英語のままです。追加翻訳では、UI、研究分野・研究名、施設、資源、効果、才能、才能プリセットを翻訳できます。

## 1. ひな形を書き出す

- Windows PC版：ヘルプタブ上部の「翻訳ファイル」から「翻訳ひな形を書き出す」を選択します。
- モバイル版：プレイヤータブの「翻訳ファイル」を開き、「翻訳ひな形を書き出す」を押します。

ひな形は英語を翻訳元としたUTF-8のJSONです。

## 2. 基本情報を編集する

```json
{
  "locale": "fr-FR",
  "name": "Français",
  "direction": "ltr",
  "fallback_locale": "en-US",
  "author": "Your name",
  "license": "CC0-1.0"
}
```

- `locale`：BCP 47形式の言語コードです。例：`fr-FR`、`ko-KR`、`ar`。
- `name`：アプリの言語選択欄に表示する名称です。
- `direction`：通常は`ltr`、アラビア語など右から左へ表示する言語は`rtl`です。
- `fallback_locale`：未翻訳部分の表示言語です。内蔵言語または読み込み済み言語を指定できます。通常は`en-US`のままで構いません。
- `author`、`license`：他者へ配布する場合に翻訳者と利用条件を記載します。

`document_type`、`schema_version`、`catalog_dataset_id`は変更しないでください。

## 3. `text`だけを翻訳する

```json
"tree.search_placeholder": {
  "source": "Search by research name",
  "text": "Rechercher une recherche"
}
```

- `source`は英語の原文です。変更する必要はありません。
- 翻訳文を`text`へ入力します。
- キー名やJSONの階層は変更しないでください。
- 翻訳しない`text`は空欄のままで構いません。`fallback_locale`の言語で表示されます。書き出したひな形では通常、英語へ戻ります。
- `<`と`>`を含むHTMLは使用できません。
- JSON文字列内の改行や引用符は、JSONの規則に従ってエスケープしてください。

免責本文は公式の日本語・英語だけを使用するため、翻訳ひな形には含まれません。翻訳ファイルへ`app.disclaimer`を追加しても無視され、追加言語では公式英語文が表示されます。

## 4. 埋め込み項目を維持する

`messages`内の`{name}`、`{level}`、`{count}`などは、実行時に値を入れるための項目です。原文にある項目をすべて翻訳文にも残してください。

```json
"plan.count": {
  "source": "{count} research tasks",
  "text": "Tâches de recherche : {count}"
}
```

名前を変えたり削除したりすると読み込み時にエラーになります。

## 5. セクション

| セクション | 内容 |
|---|---|
| `messages` | ボタン、ラベル、説明、エラーメッセージ |
| `categories` | 研究分野名 |
| `research` | 研究名 |
| `talents` | 才能名 |
| `talent_effects` | 才能効果名 |
| `talent_presets` | 才能プリセット名 |
| `talent_preset_descriptions` | 才能プリセットの説明 |
| `buildings` | 施設名 |
| `effects` | 研究効果名 |
| `effect_labels` | 元データの効果名に対する互換翻訳 |
| `effect_values` | 解放表示、時間など研究効果値の定型表現 |
| `resources` | 資源・特殊資材名 |

## 6. 読み込む

- PC版：「翻訳ファイル」から「翻訳ファイルを読み込む」を選択します。
- モバイル版：「翻訳ファイルを読み込む」を押します。

正常に読み込まれると、その言語へ切り替わります。次回起動時も選択が保存されます。同じ`locale`の修正版を読み込むと更新されます。

同じ`locale`の内蔵言語がある場合、読み込んだ翻訳はその内蔵言語へ重ねて適用されます。未翻訳項目は内蔵言語を維持し、追加翻訳を削除すると内蔵言語へ戻ります。内蔵言語がない場合は`fallback_locale`へ戻ります。プレイヤーデータは削除されません。

## 内蔵言語を追加する開発者向け手順

内蔵言語の一覧はコードではなく`resources/i18n/manifest.json`で管理します。UI、研究、建設、才能、効果、資源を含む完全な言語パックJSONを用意してマニフェストへ登録すると、PC版・モバイル版の言語一覧、自動選択、RTL、オフライン配信へ反映されます。言語ごとの条件分岐をアプリへ追加してはいけません。

`scripts/sync_bundled_language_packs.py`で内蔵言語を再生成し、`scripts/check_language_coverage.py`で画面が参照する翻訳キーの欠落、PC版とモバイル版の言語一覧の不一致、実行時コードへ日本語判定を再導入していないことを検査します。

## RTL言語

`direction`を`rtl`にすると画面の読み方向を右から左へ変更します。研究ツリー内の物理的な配置関係は、ゲーム画面との比較を保つため反転しません。長い文やボタン、数値入力が見切れないか実機で確認してください。

## 配布前の確認

- PC版とモバイル版の両方へ読み込める
- 主要タブ、研究名、才能名、施設名、資源名が表示される
- 長い文字が見切れない
- 埋め込み項目が維持されている
- RTLの場合は入力欄とダイアログも正しく読める

形式の定義は[`language-pack.schema.json`](../../schemas/language-pack.schema.json)を参照してください。
