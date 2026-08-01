# -*- coding: utf-8 -*-
"""
补抓 database-info.json 中内页字段为空的记录。

主抓取脚本 scrape_db_engines.py 运行期间，若代理/网络出现持续抖动，
会有少量记录的内页 6 个字段全部为空（重试 3 次仍失败）。
本脚本找出这些记录重新抓取并就地回写，可重复运行（幂等）。

用法:
    python retry_failed.py [json文件路径]      # 默认 database-info.json
"""

import json
import sys
import time
from pathlib import Path

# 允许从任意目录运行时仍能 import 同目录的主脚本模块
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrape_db_engines import fetch, parse_detail  # noqa: E402


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    json_file = sys.argv[1] if len(sys.argv) > 1 else "database-info.json"
    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)

    # 判定失败记录：description 与 website 均为空（正常系统的内页至少有 website）
    failed = [r for r in data["databases"] if not r["description"] and not r["website"]]
    print(f"{json_file} 中共 {len(data['databases'])} 条，待补抓 {len(failed)} 条")
    if not failed:
        return

    ok = 0
    still_empty = []
    for i, r in enumerate(failed, 1):
        print(f"  [{i}/{len(failed)}] #{r['rank']} {r['dbms']}")
        try:
            html = fetch(r["detail_url"], retries=4, timeout=40)
            info = parse_detail(html)
            if any(info.values()):
                r.update(info)
                ok += 1
            else:
                # 页面能打开但确无 Editorial 表格（极少数系统的页面本身不完整）
                still_empty.append(r["dbms"])
                print("    [提示] 页面抓取成功但无 Editorial 字段，保留空值")
        except Exception as e:
            still_empty.append(r["dbms"])
            print(f"    [仍失败] {e}")
        time.sleep(2)

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"补抓完成：成功 {ok}/{len(failed)}，已回写 {json_file}")
    if still_empty:
        print(f"仍为空的记录（可再次运行本脚本重试）: {still_empty}")


if __name__ == "__main__":
    main()
