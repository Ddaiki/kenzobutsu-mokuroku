"""
data.json の各レコードを NDL デジタルコレクション API で照合し、
電子化されているものの digital_url と status を更新する。

実行前に convert_csv.py で data.json を生成しておくこと。
API 制限のため 0.5 秒/リクエストで実行（約 45 分）。
--resume オプションで途中再開可。
"""
import json
import time
import argparse
import urllib.request
import urllib.parse


NDL_DIGITAL_API = "https://dl.ndl.go.jp/api/search"


def check_digital(ncid: str) -> str:
    """NCID で NDL デジタルコレクションを検索し、pid URL を返す。なければ空文字。"""
    params = urllib.parse.urlencode({"catno": ncid, "cnt": 1})
    url = f"{NDL_DIGITAL_API}?{params}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("list", [])
            if items:
                pid = items[0].get("id", "")
                if pid:
                    return f"https://dl.ndl.go.jp/pid/{pid}"
    except Exception as e:
        print(f"  ERROR {ncid}: {e}")
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="既に digital になっているものをスキップ")
    args = parser.parse_args()

    with open("data.json", encoding="utf-8") as f:
        records = json.load(f)

    digital_count = 0
    checked = 0

    for i, rec in enumerate(records):
        ncid = rec.get("ncid", "")
        if not ncid:
            continue
        if args.resume and rec.get("status") == "digital":
            digital_count += 1
            continue

        digital_url = check_digital(ncid)
        checked += 1

        if digital_url:
            rec["digital_url"] = digital_url
            rec["status"] = "digital"
            digital_count += 1
            print(f"[{i+1}] デジタル公開: {rec['title'][:30]} → {digital_url}")

        if checked % 50 == 0:
            print(f"  進捗: {checked} 件確認済み / デジタル: {digital_count} 件")
            # 途中保存
            with open("data.json", "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, separators=(",", ":"))

        time.sleep(0.5)

    # 最終保存
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, separators=(",", ":"))

    total_ndl = sum(1 for r in records if r["status"] in ("digital", "ndl_catalog"))
    print(f"\n完了: デジタル公開={digital_count}, NDL所蔵合計={total_ndl}")


if __name__ == "__main__":
    main()
