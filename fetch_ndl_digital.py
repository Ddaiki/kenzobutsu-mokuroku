"""
NDL デジタルコレクションから建造物関連報告書を一括取得し、
data.json を更新するスクリプト。

動作:
  1. NDL SRU API で「建造物」「修理工事報告」等のキーワードを含む
     デジタル公開レコードを全件収集（ページネーション）
  2. 旧字体→新字体に正規化してタイトル類似度で data.json の既存レコードと照合
  3. 既存レコード → digital_url / status を更新
  4. 未収録レコード → 新規エントリとして追加（source="NDL Digital"）

実行: python3 fetch_ndl_digital.py
     python3 fetch_ndl_digital.py --dry-run  # 保存せず集計のみ
"""
import json
import re
import time
import argparse
import unicodedata
import urllib.request
import urllib.parse

NDL_SRU = "https://ndlsearch.ndl.go.jp/api/sru"
DL_PATTERN = re.compile(r'dl\.ndl\.go\.jp/pid/(\d+)')
TITLE_PATTERN = re.compile(r'dcterms:title&gt;([^&<]+)')
DATE_PATTERN  = re.compile(r'dcterms:issued[^&]*&gt;(\d{4})')
ABOUT_PATTERN = re.compile(r'rdf:about="(https://ndlsearch\.ndl\.go\.jp/books/[^"#]+)')

# 旧字体 → 新字体 変換テーブル
KYUJI_TABLE = str.maketrans(
    '國寳寶臺壽廣覽會體佛號圓藏濱橫淺鐵彌醫齊黑澤靜廳歷傳殘證燈獸濕禮蠶覺讓齒齡',
    '国宝宝台寿広覧会体仏号円蔵浜横浅鉄弥医斉黒沢静庁歴伝残証灯獣湿礼蚕覚譲歯齢'
)

# 建造物関連の検索キーワード群（ANDで組み合わせず、1件ずつ全件取得）
SEARCH_QUERIES = [
    '修理工事報告書',
    '保存修理工事報告',
    '建造物調査報告',
    '国宝建造物',
    '重要文化財保存修理',
]


def normalize(s: str) -> str:
    """旧字体→新字体変換 + 全角空白・カナ正規化"""
    s = s.translate(KYUJI_TABLE)
    s = unicodedata.normalize("NFKC", s)
    return s


def title_similarity(a: str, b: str) -> float:
    """正規化後のタイトル類似度（0〜1）。単純な共通文字比率。"""
    na, nb = set(normalize(a)), set(normalize(b))
    if not na or not nb:
        return 0.0
    return len(na & nb) / len(na | nb)


def fetch_digital_records(query: str, max_pages: int = 200) -> list:
    """
    NDL SRU で query を全件取得し、dl.ndl.go.jp リンク付きのものだけ返す。
    戻り値: [{"title": ..., "year": ..., "digital_url": ...}, ...]
    """
    results = []
    start = 1
    per_page = 50

    while start <= max_pages * per_page:
        params = urllib.parse.urlencode({
            "operation": "searchRetrieve",
            "query": f'title any "{query}"',
            "startRecord": start,
            "maximumRecords": per_page,
            "recordSchema": "dcndl",
        })
        url = f"{NDL_SRU}?{params}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kenzobutsu-db/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8")
        except Exception as e:
            print(f"    ERROR: {e}")
            break

        hits_m = re.search(r"numberOfRecords>(\d+)<", body)
        total = int(hits_m.group(1)) if hits_m else 0
        if total == 0:
            break

        # 各レコードをパース
        records_xml = re.split(r'<record>', body)[1:]
        for rec_xml in records_xml:
            pids = DL_PATTERN.findall(rec_xml)
            if not pids:
                continue  # デジタル公開なし → スキップ

            # タイトル
            t = TITLE_PATTERN.search(rec_xml)
            title = t.group(1).strip() if t else ""
            # 発行年
            y = DATE_PATTERN.search(rec_xml)
            year = y.group(1) if y else ""
            # about URL
            about = ABOUT_PATTERN.search(rec_xml)
            ndl_url = about.group(1) if about else ""

            results.append({
                "title": title,
                "year": year,
                "ndl_url": ndl_url,
                "digital_url": f"https://dl.ndl.go.jp/pid/{pids[0]}",
                "pid": pids[0],
            })

        start += per_page
        if start > total:
            break
        time.sleep(0.4)

    return results


def find_best_match(ndl_rec: dict, existing: list) -> tuple:
    """
    NDL レコードと最も近い既存レコードを返す。
    戻り値: (record_or_None, similarity_score)
    """
    ntitle = normalize(ndl_rec["title"])
    nyear  = ndl_rec["year"]
    best_rec, best_sim = None, 0.0

    for r in existing:
        sim = title_similarity(ntitle, normalize(r["title"]))
        if sim < 0.5:
            continue
        # 年が一致すればボーナス
        rec_year = r.get("pub_date", "")[:4]
        if nyear and rec_year and nyear == rec_year:
            sim = min(sim + 0.15, 1.0)
        if sim > best_sim:
            best_sim = sim
            best_rec = r

    return best_rec, best_sim


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="data.json を更新しない")
    args = parser.parse_args()

    with open("data.json", encoding="utf-8") as f:
        existing = json.load(f)

    existing_pids = set(
        r.get("digital_url", "").split("/pid/")[-1]
        for r in existing if r.get("digital_url")
    )
    not_digital = [r for r in existing if r.get("status") != "digital"]

    # 全クエリで NDL Digital レコードを収集
    all_ndl = {}  # pid → record（重複排除）
    for q in SEARCH_QUERIES:
        print(f"\n検索: '{q}'")
        recs = fetch_digital_records(q)
        for nr in recs:
            all_ndl[nr["pid"]] = nr
        print(f"  取得: {len(recs)}件 / 累計ユニーク: {len(all_ndl)}件")
        time.sleep(1)

    print(f"\n合計 {len(all_ndl)} 件のデジタル公開レコードを取得")

    updated = 0
    added   = 0
    max_no  = max(r["no"] for r in existing)

    for pid, nr in all_ndl.items():
        if pid in existing_pids:
            continue  # 既にデジタル登録済み

        best_rec, sim = find_best_match(nr, not_digital)
        if best_rec and sim >= 0.6:
            # 既存レコードを更新
            best_rec["digital_url"] = nr["digital_url"]
            best_rec["status"]      = "digital"
            if nr["ndl_url"] and "/R" in nr["ndl_url"]:
                best_rec["ndl_url"] = nr["ndl_url"]
            updated += 1
            existing_pids.add(pid)
            print(f"  更新 (sim={sim:.2f}): [{best_rec['no']}] {best_rec['title'][:35]}")
            print(f"    NDL: {nr['title'][:35]} → {nr['digital_url']}")
        elif nr["title"] and len(nr["title"]) >= 4:
            # 未収録 → 新規追加
            max_no += 1
            new_rec = {
                "no":          max_no,
                "pref":        "",
                "org":         "",
                "title":       nr["title"],
                "subtitle":    "",
                "vol":         "",
                "series":      "",
                "series_no":   "",
                "author":      "",
                "editor":      "",
                "publisher":   "",
                "pub_date":    nr["year"],
                "ncid":        "",
                "jp_no":       "",
                "soram_id":    "",
                "note":        "",
                "ndl_url":     nr["ndl_url"],
                "digital_url": nr["digital_url"],
                "nabunken_url": "",
                "status":      "digital",
                "source":      "NDL Digital",
            }
            existing.append(new_rec)
            existing_pids.add(pid)
            added += 1
            print(f"  新規追加: {nr['title'][:40]} ({nr['year']})")

    print(f"\n結果: 既存更新={updated}件 / 新規追加={added}件")

    if not args.dry_run:
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, separators=(",", ":"))
        print("data.json を保存しました")


if __name__ == "__main__":
    main()
