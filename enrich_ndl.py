"""
data.json の各レコードを NDL サーチ API（ndlsearch.ndl.go.jp）で照合し、
- ndl_url: NDLサーチの書誌ページに更新
- digital_url / status: NDLデジタルコレクション公開済みのものを "digital" に更新

実行前に convert_csv.py で data.json を生成しておくこと。
API 制限のため 0.5 秒/リクエストで実行（全件で約 45 分）。
--resume オプションで途中再開可。
"""
import json
import re
import time
import argparse
import urllib.request
import urllib.parse

NDL_SRU_API = "https://ndlsearch.ndl.go.jp/api/sru"
DL_PATTERN = re.compile(r'https?://dl\.ndl\.go\.jp/pid/\d+')
ABOUT_PATTERN = re.compile(r'rdf:about="(https://ndlsearch\.ndl\.go\.jp/books/[^"#]+)')


def check_ndl(ncid: str) -> tuple:
    """
    NDLサーチAPIでNCIDを検索し (ndl_url, digital_url) を返す。
    所蔵なし or エラーは ("", "") を返す。
    """
    params = urllib.parse.urlencode({
        "operation": "searchRetrieve",
        "query": f"anywhere={ncid}",
        "maximumRecords": 1,
        "recordSchema": "dcndl",
    })
    url = f"{NDL_SRU_API}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "kenzobutsu-db/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")

        # ヒット0件
        if re.search(r'numberOfRecords>0<', body):
            return "", ""

        # NDLサーチのページURL
        m = ABOUT_PATTERN.search(body)
        ndl_url = m.group(1) if m else f"https://ndlsearch.ndl.go.jp/search?q={ncid}"

        # NDLデジタルコレクションURL（公開されている場合のみ存在）
        dl_matches = DL_PATTERN.findall(body)
        digital_url = dl_matches[0] if dl_matches else ""

        return ndl_url, digital_url

    except Exception as e:
        print(f"  ERROR {ncid}: {e}")
        return "", ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true",
                        help="digital 確定済みのものをスキップして途中から再開")
    args = parser.parse_args()

    with open("data.json", encoding="utf-8") as f:
        records = json.load(f)

    digital_count = 0
    updated_ndl = 0
    checked = 0

    for i, rec in enumerate(records):
        ncid = rec.get("ncid", "")
        if not ncid:
            continue
        if args.resume and rec.get("status") == "digital":
            digital_count += 1
            continue

        ndl_url, digital_url = check_ndl(ncid)
        checked += 1

        if ndl_url:
            rec["ndl_url"] = ndl_url
            updated_ndl += 1
        if digital_url:
            rec["digital_url"] = digital_url
            rec["status"] = "digital"
            digital_count += 1
            print(f"[{i+1}] デジタル公開: {rec['title'][:30]}")

        if checked % 100 == 0:
            print(f"  進捗: {checked} 件 / NDL確認={updated_ndl} / デジタル={digital_count}")
            with open("data.json", "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, separators=(",", ":"))

        time.sleep(0.5)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n完了: 確認={checked} 件, NDL所蔵確認={updated_ndl}, デジタル公開={digital_count}")


if __name__ == "__main__":
    main()
