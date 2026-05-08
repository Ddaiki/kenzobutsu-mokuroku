"""
kenzobutsu_mokuroku.csv を data.json に変換する。
ステータスは初期値のみ設定（enrich_ndl.py で更新する）。
"""
import csv
import json


def clean_date(raw):
    d = raw.strip()
    if len(d) == 8 and d.isdigit():
        year = d[:4]
        month = d[4:6]
        if month == "00":
            return year
        return f"{year}-{month}"
    return d


def main():
    records = []
    with open("kenzobutsu_mokuroku.csv", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ncid = row.get("NCID", "").strip()
            jp_no = row.get("JP番号", "").strip()

            if ncid:
                ndl_url = f"https://ndlsearch.ndl.go.jp/search?q={ncid}"
            elif jp_no:
                ndl_url = f"https://ndlsearch.ndl.go.jp/search?q={jp_no}"
            else:
                ndl_url = ""

            # 初期ステータス（enrich_ndl.py で "digital" に更新される）
            if ncid or jp_no:
                status = "ndl_catalog"
            else:
                status = "unknown"

            records.append({
                "no": int(row.get("No.", 0) or 0),
                "pref": row.get("都道府県", "").strip(),
                "org": row.get("データ管理機関名称", "").strip(),
                "title": row.get("書名", "").strip(),
                "subtitle": row.get("副書名", "").strip(),
                "vol": row.get("巻次", "").strip(),
                "series": row.get("シリーズ名", "").strip(),
                "series_no": row.get("シリーズ番号", "").strip(),
                "author": row.get("編著者名", "").strip(),
                "editor": row.get("編集機関", "").strip(),
                "publisher": row.get("発行機関", "").strip(),
                "pub_date": clean_date(row.get("発行年月日", "")),
                "ncid": ncid,
                "jp_no": jp_no,
                "soram_id": row.get("総覧ID", "").strip(),
                "note": row.get("備考", "").strip(),
                "ndl_url": ndl_url,
                "digital_url": "",
                "status": status,
            })

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, separators=(",", ":"))

    stats = {
        "total": len(records),
        "ndl_catalog": sum(1 for r in records if r["status"] == "ndl_catalog"),
        "unknown": sum(1 for r in records if r["status"] == "unknown"),
    }
    print(f"変換完了: {stats}")


if __name__ == "__main__":
    main()
