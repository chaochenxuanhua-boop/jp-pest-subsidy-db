# Venture 06: 全国市区町村「スズメバチ・シロアリ・害獣」役所補助金＆防護服貸出ルール横断DB ＋ 相続空き家10年損益計算機

全国の市区町村ごとにバラバラに公開されている**「スズメバチ駆除補助金（事前申請要件・上限額）」「防護服無料貸出」「市指定業者・区委託ルール」「害獣箱わな相談窓口」**と、**「老朽危険空き家の除却補助金 vs 更地解体後の固定資産税約4.2倍（最大6倍）増税 vs 現況訳あり買取」**をワンストップで横断検索・損益計算できる高信頼ポータルです。

---

## 1. ビジネス優位性とマネタイズ構造（特商法表記不要・即日運用モデル）

1. **公的ルール構造化による圧倒的な信頼性（悪質おとり広告へのカウンターポジション）**
   - 「ハチ駆除 500円〜」といった誇大広告による高額請求トラブルが多発する中、**「事前申請しないと補助金が0円になる自治体」「民間業者を呼ぶ前に区役所へ電話すべき指定・委託自治体」**を正直に最優先で警告します。
   - ユーザー利益を最優先する誠実な設計により、自己手配が必要なケースや夜間・高所案件において上場企業運営の明朗会計駆けつけサービスへの成約率（CVR）が飛躍的に高まります。
2. **「実家の蜂・シロアリ・ハクビシン被害」から「空き家現況買取（高単価CPA）」への二段階導線**
   - 夏〜秋に急増する「放置していた実家・空き家にスズメバチの巣ができた／シロアリ・ハクビシンが入った」という検索層に対し、単なる駆除見積もり（CPA 6,000〜18,000円）だけでなく、**『安易に更地解体すると住宅用地特例（1/6）が外れて固定資産税が約4.2倍に跳ね上がる罠』**を10年キャッシュフローで可視化し、現況訳あり買取査定（CPA 15,000〜35,000円）へ自然に接続します。
3. **特商法リスクゼロ（自社決済なし・ASP送客完結）**
   - A8.net / レントラックス等で提携可能な東証グロース上場企業系プログラム（ハチ110番・シロアリ110番・害獣110番・訳あり物件買取プロ等）の計測URLを `site/data/affiliate_config.json` に設定するだけで収益化が完結します。

---

## 2. ディレクトリ構成

```text
06_pest_subsidy_db/
├── .github/workflows/
│   └── deploy.yml                    # データ検証（Harvester不変条件チェック）＋ GitHub Pages自動デプロイ
├── pipeline/
│   └── municipality_harvester.py     # 自治体HTML/PDFテキスト多段パーサー＆ハルシネーション防止バリデータ
├── site/
│   ├── index.html                    # Page 1: 全国自治体「蜂・シロアリ・害獣」補助金＆実質負担チェッカー
│   ├── akiya.html                    # Page 2: 相続空き家「解体4倍増税 vs 解体補助金 vs 現況買取」10年計算機
│   ├── app.js                        # Page 1 検索・かな正規化・補助金控除＆適正相場計算ロジック
│   ├── akiya.js                      # Page 2 地方税法特例・改正空家法・10年累計収支SVGチャート計算エンジン
│   ├── style.css                     # 官公庁・生活防衛ポータル調レスポンシブUIスタイル
│   └── data/
│       ├── municipalities.json       # 全国6地方・主要81市区町村の構造化検証済データセット
│       └── affiliate_config.json     # ASP計測URL一括管理設定ファイル
└── README.md
```

---

## 3. ローカル動作確認＆データ検証コマンド

### ローカルブラウザで今すぐプレビューする
リポジトリルートから共通ランチャーを使うか、`site/` ディレクトリでローカルHTTPサーバーを起動します。

```powershell
# 方法A：ポートフォリオ共通ランチャーから起動
.\ventures\deploy_venture.ps1 -Venture 06 -LocalPreview

# 方法B：単体でHTTPサーバーを起動（http://localhost:8090）
python -m http.server 8090 --directory ventures/06_pest_subsidy_db/site
```

### Pythonハーベスター＆バリデータの実行
```powershell
# 構文チェック
python -m py_compile ventures/06_pest_subsidy_db/pipeline/municipality_harvester.py

# 収録データセット（81市区町村）の不変条件検証＋4類型パーサー単体テスト実行
python ventures/06_pest_subsidy_db/pipeline/municipality_harvester.py --validate

# シードデータの再生成
python ventures/06_pest_subsidy_db/pipeline/municipality_harvester.py --build-seed

# 新規自治体の環境課HTML/テキストから構造化レコードを抽出・原典数値照合（全国1,741自治体拡張用）
python ventures/06_pest_subsidy_db/pipeline/municipality_harvester.py `
  --parse-file ./raw_page.html --code 08201 --pref 茨城県 --city 水戸市 --kana みとし
```

---

## 4. ASPアフィリエイトリンクの差し替え手順

`site/data/affiliate_config.json` 内の `programs.<案件キー>.target_url` を、A8.net やレントラックスの管理画面で取得した提携リンクに書き換えてコミットするだけで全ページのCTAボタンに即時反映されます。

- `hachi_110`: スズメバチ・アシナガバチ駆除無料見積もり枠
- `shiroari_110`: シロアリ床下無料点検・駆除枠
- `gaiju_110`: ハクビシン・アライグマ・ネズミ駆除枠
- `akiya_kaitori`: 訳あり物件・相続空き家の現況買取査定枠
- `akiya_kaitai`: 自治体補助金併用時の解体工事一括見積もり枠
