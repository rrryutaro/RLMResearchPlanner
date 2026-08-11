# セキュリティポリシー

## 対応するバージョン

原則として、GitHub Releasesで公開している最新バージョンを対象に修正します。古いバージョンで問題を確認した場合は、最新版でも再現するか確認してください。

## 非公開で報告する問題

次のような、第三者に悪用される可能性がある問題は公開Issueへ書かないでください。

- 任意のコードやファイルを実行できる問題
- 更新ファイルやダウンロード検証を回避できる問題
- 利用者の設定、バックアップ、画面内容などが意図せず外部へ送信される問題
- 配布物や公開手順の改ざんにつながる問題

[GitHubの非公開脆弱性報告](https://github.com/rrryutaro/RLMResearchPlanner/security/advisories/new)から、再現手順、影響、確認したバージョンを送ってください。アカウント名、チャット、ゲーム画面などの個人情報は、再現に必要な部分以外を隠してください。

OCRの誤認識、研究・建設データの誤り、表示崩れ、通常の計算不具合はセキュリティ問題ではありません。これらは[GitHub Issues](https://github.com/rrryutaro/RLMResearchPlanner/issues)へ報告してください。

報告内容を確認し、影響範囲と対応方針が分かり次第連絡します。修正前の内容を公開する時期は、報告者と相談して決めます。

## English summary

Security reports are accepted for the latest release. Do not open a public issue for a potentially exploitable vulnerability. Use [GitHub private vulnerability reporting](https://github.com/rrryutaro/RLMResearchPlanner/security/advisories/new) and include the affected version, impact, and reproduction steps. Redact personal or in-game information that is not required. Ordinary OCR, data, calculation, and display bugs belong in [GitHub Issues](https://github.com/rrryutaro/RLMResearchPlanner/issues).
