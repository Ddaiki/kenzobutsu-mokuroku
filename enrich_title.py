"""
タイトルベースのデジタルURL補完スクリプト。

enrich_ndl.py（NCID照合）でカバーできなかったレコードを対象に、
書名キーワード＋発行年で NDL SRU を検索してデジタルURLを取得する。

誤マッチを防ぐため以下の条件でのみ採用:
  - キーワードが5文字以上
  - ヒット総数が20件以下（汎用キーワード排除）
  - または年フィルター適用後のヒット数が10件以下

実行: python3 enrich_title.py
     python3 enrich_title.py --pref 京都府  # 特定県のみ
"""
import json
import re
import time
import argparse
import urllib.request
import urllib.parse

NDL_SRU = "https://ndlsearch.ndl.go.jp/api/sru"
DL_PATTERN = re.compile(r'dl\.ndl\.go\.jp/pid/(\d+)')

NOISE = re.compile(
    r"(国宝建造物|重要文化財|国指定|都道府県指定|市指定|町指定|[国都県市町村]?指定|"
    r"史跡|名勝|天然記念物|旧|重文|"
    r"保存修理工事報告書?|修理工事報告書?|調査報告書?|保存整備事業報告書?|"
    r"工事報告|工事精算報告書?|復原工事|復元工事|復旧工事|"
    r"整備事業報告書?|保存活用計画|基本調査|緊急調査報告書?|"
    r"ほか\S{0,3}棟|他\S{0,3}棟|"
    r"第\S+冊?|附図?|上巻?|下巻?|別冊|\s)"
)
MAX_HITS = 20          # これ以上ヒットするキーワードはスキップ
MIN_KW_LEN = 5        # 最低キーワード長（文字数）


def extract_keyword(title: str) -> str:
    """書名から建物固有名を抽出（サブタイトルは不使用）。"""
    cleaned = NOISE.sub("", title).strip()
    kw = cleaned[:10].strip()
    if len(kw) < MIN_KW_LEN:
        kw = re.sub(r"[\s　]", "", title)[:8]
    return kw


def search_ndl(keyword: str, year: str, max_records: int = 10) -> tuple:
    """
    NDL SRU を検索し (total_hits, [digital_urls]) を返す。
    total_hits が MAX_HITS 超のときは呼び出し元でスキップ判定。
    """
    def _fetch(q):
        params = urllib.parse.urlencode({
            "operation": "searchRetrieve",
            "query": q,
            "maximumRecords": max_records,
            "recordSchema": "dcndl",
        })
        req = urllib.request.Request(
            f"{NDL_SRU}?{params}",
            headers={"User-Agent": "kenzobutsu-db/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")

    try:
        q = f'title any "{keyword}"'
        if year and year.isdigit() and len(year) == 4:
            y = int(year)
            q_year = q + f" and from = {y-2} and until = {y+2}"
            body = _fetch(q_year)
            if "illegal" in body or "diagnostic" in body:
                body = _fetch(q)   # 年フィルター失敗 → 年なし
        else:
            body = _fetch(q)

        hits_m = re.search(r"numberOfRecords>(\d+)<", body)
        total = int(hits_m.group(1)) if hits_m else 0
        pids = DL_PATTERN.findall(body)
        dl_urls = [f"https://dl.ndl.go.jp/pid/{p}" for p in pids]
        return total, dl_urls

    except Exception as e:
        print(f"    ERROR [{keyword}]: {e}")
        return 0, []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pref", default="", help="特定都道府県のみ処理")
    args = parser.parse_args()

    with open("data.json", encoding="utf-8") as f:
        records = json.load(f)

    target = [
        r for r in records
        if r.get("status") != "digital"
        and r.get("title")
        and (not args.pref or r.get("pref") == args.pref)
    ]
    print(f"対象: {len(target)}件 / 全体: {len(records)}件")

    found = 0
    skipped_generic = 0
    checked = 0

    for rec in target:
        title = rec["title"]
        year = rec.get("pub_date", "")[:4]
        kw = extract_keyword(title)

        if len(kw) < MIN_KW_LEN:
            continue

        total, dl_urls = search_ndl(kw, year)
        checked += 1

        if total > MAX_HITS:
            skipped_generic += 1
        elif dl_urls:
            rec["digital_url"] = dl_urls[0]
            rec["status"] = "digital"
            found += 1
            print(f"  [{rec['no']}] {title[:35]}")
            print(f"    kw={kw!r} hits={total} → {dl_urls[0]}")

        if checked % 100 == 0:
            print(f"  --- 進捗: {checked}件 / 新規: {found}件 / 汎用スキップ: {skipped_generic}件 ---")
            with open("data.json", "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, separators=(",", ":"))

        time.sleep(0.5)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n完了: {checked}件確認 / 新規デジタル: {found}件 / 汎用スキップ: {skipped_generic}件")


if __name__ == "__main__":
    main()
