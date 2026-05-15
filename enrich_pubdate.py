"""
発行年補完スクリプト

1. NCID あり → CiNii Research JSON API (https://ci.nii.ac.jp/ncid/{ncid}.json)
2. NCID なし → NDL SRU タイトル検索（厳格マッチ: hits≤10 かつタイトル一致）
3. 取得できない場合 → pub_date = "" のまま（UI で "—" 表示）

"197-" 形式の近似年は pub_year = 1970 に変換。

実行: python3 enrich_pubdate.py [--dry-run]
"""

import json
import re
import time
import argparse
import urllib.request
import urllib.parse
import html as html_mod

CINII_API  = "https://ci.nii.ac.jp/ncid/{ncid}.json"
NDL_SRU    = "https://ndlsearch.ndl.go.jp/api/sru"
DELAY      = 0.5          # 秒/リクエスト
MAX_HITS   = 10           # これを超えたら NDL タイトル検索を信用しない

# タイトル正規化用ノイズ
TITLE_NOISE = re.compile(
    r"[　 　\s（）()「」『』【】〔〕\[\]・ー‐―—〜～]"
    r"|史跡|重要文化財|国宝|旧|重文"
)

# 近似年パターン "197-" → 1970
APPROX_PAT = re.compile(r"^\[?(\d{3})-[\-?\]]*$")

# 明確な年パターン
CLEAR_PAT  = re.compile(r"(\d{4})")


def parse_year(date_str):
    """(pub_year: int|None, display_date: str) を返す。"""
    if not date_str:
        return None, ""

    s = date_str.strip(" []?")

    # 近似: "197-" → 1970
    m = APPROX_PAT.match(s)
    if m:
        decade_start = int(m.group(1)) * 10
        return decade_start, f"{decade_start}頃"

    # 明確な4桁年
    m = CLEAR_PAT.search(s)
    if m:
        y = int(m.group(1))
        if 1800 <= y <= 2100:
            return y, s[:7]  # YYYY or YYYY-MM

    return None, ""


def normalize_title(title):
    return TITLE_NOISE.sub("", title).strip()


def fetch_cinii(ncid):
    """CiNii Research JSON API から dc:date を返す。失敗時は ""。"""
    url = CINII_API.format(ncid=ncid)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "kenzobutsu-db/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        graph = data.get("@graph", [])
        if graph:
            date = graph[0].get("dc:date", "")
            if date:
                return str(date)
    except Exception as e:
        print(f"    CiNii ERROR {ncid}: {e}")
    return ""


def fetch_ndl_by_title(title):
    """NDL SRU タイトル検索。厳格マッチ時のみ dcterms:issued を返す。"""
    kw = re.sub(
        r"(保存修理工事報告書?|修理工事報告書?|調査報告書?|整備事業報告書?|"
        r"復原工事|復元工事|工事報告|計画書|保存整備|保存活用|基本設計|"
        r"保存修理|修理報告|発掘調査|\s)",
        "",
        title,
    )[:12].strip()

    if len(kw) < 4:
        return ""

    params = urllib.parse.urlencode(
        {
            "operation": "searchRetrieve",
            "query": f"title={kw}",
            "maximumRecords": MAX_HITS,
            "recordSchema": "dcndl",
        }
    )
    try:
        req = urllib.request.Request(
            f"{NDL_SRU}?{params}",
            headers={"User-Agent": "kenzobutsu-db/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = html_mod.unescape(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"    NDL ERROR [{kw}]: {e}")
        return ""

    m = re.search(r"<numberOfRecords>(\d+)", body)
    hits = int(m.group(1)) if m else 0
    if hits == 0 or hits > MAX_HITS:
        return ""

    ndl_titles  = re.findall(r"<dcterms:title>([^<]+)<", body)
    ndl_issued  = re.findall(r"<dcterms:issued[^>]*>([^<]+)<", body)

    norm_query = normalize_title(title)
    for i, ndl_t in enumerate(ndl_titles):
        norm_ndl = normalize_title(ndl_t)
        if norm_query in norm_ndl or norm_ndl in norm_query:
            if i < len(ndl_issued):
                return ndl_issued[i]
            elif ndl_issued:
                return ndl_issued[0]

    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="data.json を変更しない")
    args = parser.parse_args()

    with open("data.json", encoding="utf-8") as f:
        records = json.load(f)

    # 全レコードに pub_year を付与（既存 pub_date から）
    for rec in records:
        if "pub_year" not in rec:
            py, _ = parse_year(rec.get("pub_date", ""))
            rec["pub_year"] = py

    no_date = [r for r in records if not r.get("pub_date", "")]
    print(f"発行年なし: {len(no_date)} 件")

    found = 0
    approx = 0
    still_unknown = 0

    for i, rec in enumerate(no_date):
        no   = rec["no"]
        ncid = rec.get("ncid", "")

        raw_date = ""
        source   = ""

        if ncid:
            raw_date = fetch_cinii(ncid)
            source = f"CiNii({ncid})"
            time.sleep(DELAY)
        else:
            raw_date = fetch_ndl_by_title(rec.get("title", ""))
            source = "NDL-title"
            time.sleep(DELAY)

        if raw_date:
            py, display = parse_year(raw_date)
            rec["pub_date"] = display if display else raw_date
            rec["pub_year"] = py
            flag = "〜" if (py and display and "頃" in display) else ""
            print(f"  [{i+1}/{len(no_date)}] No.{no}: {raw_date!r} → {display!r} (year={py}) [{source}] {flag}")
            found += 1
            if display and "頃" in display:
                approx += 1
        else:
            rec["pub_year"] = None
            still_unknown += 1
            print(f"  [{i+1}/{len(no_date)}] No.{no}: 不明 [{source}]")

    print(f"\n=== 結果 ===")
    print(f"  取得成功: {found} 件（うち近似年: {approx} 件）")
    print(f"  引き続き不明: {still_unknown} 件")

    if not args.dry_run:
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, separators=(",", ":"))
        print("data.json を更新しました。")
    else:
        print("--dry-run: ファイルは変更しませんでした。")


if __name__ == "__main__":
    main()
