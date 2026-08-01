# -*- coding: utf-8 -*-
"""补抓 database-info.json 中内页字段为空的记录（代理超时导致的失败项）。"""

import json
import sys
import time

from scrape_db_engines import TARGET_FIELDS, fetch, parse_detail

INPUT_FILE = "database-info.json"


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)

    # 判定失败记录：description 与 website 均为空（正常系统至少有 website）
    failed = [r for r in data["databases"] if not r["description"] and not r["website"]]
    print(f"待补抓 {len(failed)} 条")
    if not failed:
        return

    ok = 0
    for i, r in enumerate(failed, 1):
        print(f"  [{i}/{len(failed)}] #{r['rank']} {r['dbms']}")
        try:
            html = fetch(r["detail_url"], retries=4, timeout=40)
            info = parse_detail(html)
            if any(info.values()):
                r.update(info)
                ok += 1
            else:
                print(f"    [警告] 页面抓取成功但未解析到字段，可能确无 Editorial 表格")
        except Exception as e:
            print(f"    [仍失败] {e}")
        time.sleep(2)

    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"补抓完成：成功 {ok}/{len(failed)}，已回写 {INPUT_FILE}")


if __name__ == "__main__":
    main()
