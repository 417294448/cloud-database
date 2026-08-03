# -*- coding: utf-8 -*-
"""
基于已有 database-info.json 做增量更新，不重新抓取全部系统的内页。

设计依据：
- 排名页本身很轻（1 次请求即含全部系统），每次都重新抓取，不需要先"检查数量"再决定要不要抓；
  数量不变不代表系统集合没变（可能同时一增一减），必须按系统逐条 diff，不能只看总数。
- 真正昂贵的是内页抓取（434 次请求）。已存在的系统（用 detail_url 精确匹配）直接复用旧记录的
  内页字段（description / website / developer / license / *_cn），只更新排名页本身就能拿到的
  字段（rank、dbms 名字、database_model，模型变了才重算 database_model_cn）；
  只有新增系统才需要抓内页 + 走翻译流程。
- 已存在系统的内页信息（尤其 current_release、license）不会随增量更新自动刷新——DB-Engines
  内页本身更新不频繁，如需强制刷新所有系统的内页，用完整流程（scrape_db_engines.py 全量重抓）。

用法（三步）：
    python incremental_update.py --diff
        预览会有哪些新增/移除/排名变化，不写任何文件，用于确认后再执行。

    python incremental_update.py --apply
        执行更新：复用已有系统的内页数据，只对新增系统抓内页，写回 database-info.json；
        若有新增系统，同时输出待翻译清单 pending-translations.json。

    python incremental_update.py --merge-translations pending-translations.json
        翻译完新增系统的 description/developer 后，合并回填 database-info.json。
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrape_db_engines import RANKING_URL, fetch, parse_ranking, parse_detail, TARGET_FIELDS  # noqa: E402
from translate_range import translate_model, LICENSE_CN  # noqa: E402
from fix_data import clean_model_str  # noqa: E402
from diff_utils import write_diff_report  # noqa: E402

DB_FILE = "database-info.json"
PENDING_FILE = "pending-translations.json"


def load_db(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_db(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def diff(old_data, new_entries):
    """
    按 detail_url 做主键 diff（比 dbms 名字更稳，改名不影响匹配）。
    返回 (kept, added, removed, renamed)：
      kept    - 已存在系统，复用旧内页字段，rank/dbms/database_model 更新为最新值
      added   - 新增系统（排名页有，旧 json 没有），需要抓内页
      removed - 消失的系统（旧 json 有，排名页没有了），直接从结果中剔除
      renamed - [(旧名, 新名), ...]，同一 detail_url 但显示名变化，仅供日志提示
    """
    old_by_url = {r["detail_url"]: r for r in old_data["databases"]}
    new_urls = {e["detail_url"] for e in new_entries}

    kept, added, renamed = [], [], []
    for entry in new_entries:
        old = old_by_url.get(entry["detail_url"])
        if old is None:
            added.append(entry)
            continue
        merged = dict(old)
        merged["rank"] = entry["rank"]
        if entry["dbms"] != old["dbms"]:
            renamed.append((old["dbms"], entry["dbms"]))
            merged["dbms"] = entry["dbms"]
        # 排名页解析出的 database_model 可能是简称（如 "RDF"），而已有记录经 fix_data.py
        # 规范化为全称（"RDF store"）；必须用同样的规范化函数处理后再比较，
        # 否则 434 条单模型系统会被误判为"模型变了"，englishmodel 被错误退化回简称。
        new_model = clean_model_str(entry["database_model"])
        if new_model != old.get("database_model"):
            merged["database_model"] = new_model
            merged["database_model_cn"] = translate_model(new_model)
        kept.append(merged)

    removed = [r for url, r in old_by_url.items() if url not in new_urls]
    return kept, added, removed, renamed


def fetch_ranking():
    print(f"下载排名页: {RANKING_URL}")
    html = fetch(RANKING_URL)
    return parse_ranking(html, None)


def cmd_diff():
    old_data = load_db(DB_FILE)
    month, entries = fetch_ranking()
    kept, added, removed, renamed = diff(old_data, entries)

    print(f"\n旧数据: {len(old_data['databases'])} 条（{old_data.get('ranking_month', '?')}）")
    print(f"新排名: {len(entries)} 条（{month}）")

    print(f"\n新增 {len(added)} 条:")
    for e in added:
        print(f"  + #{e['rank']} {e['dbms']}")

    print(f"\n移除 {len(removed)} 条:")
    for r in removed:
        print(f"  - #{r['rank']} {r['dbms']}")

    if renamed:
        print(f"\n显示名变化 {len(renamed)} 条:")
        for old_name, new_name in renamed:
            print(f"  ~ {old_name}  ->  {new_name}")

    print(f"\n保留（复用内页数据，更新排名）: {len(kept)} 条")
    print("\n此为预览，未写入任何文件。确认无误后运行 --apply 执行更新。")


def cmd_apply(delay):
    old_data = load_db(DB_FILE)
    month, entries = fetch_ranking()
    kept, added, removed, renamed = diff(old_data, entries)

    print(f"新增 {len(added)} 条（需抓内页），移除 {len(removed)} 条，保留 {len(kept)} 条")
    for r in removed:
        print(f"  [移除] #{r['rank']} {r['dbms']}")
    for old_name, new_name in renamed:
        print(f"  [改名] {old_name} -> {new_name}")

    new_records = []
    for i, entry in enumerate(added, 1):
        print(f"  [{i}/{len(added)}] 抓取新增系统内页: #{entry['rank']} {entry['dbms']}")
        try:
            detail_html = fetch(entry["detail_url"])
            info = parse_detail(detail_html)
        except Exception as e:
            print(f"    [错误] 抓取失败: {e}", file=sys.stderr)
            info = {k: "" for k in TARGET_FIELDS.values()}
        model = clean_model_str(entry["database_model"])
        new_records.append({
            "rank": entry["rank"],
            "dbms": entry["dbms"],
            "database_model": model,
            "database_model_cn": translate_model(model),
            "detail_url": entry["detail_url"],
            "description": info["description"],
            "description_cn": "",
            "website": info["website"],
            "developer": info["developer"],
            "developer_cn": "",
            "initial_release": info["initial_release"],
            "current_release": info["current_release"],
            "license": info["license"],
            "license_cn": LICENSE_CN.get(info["license"], info["license"]) if info["license"] else "",
        })
        if i < len(added):
            time.sleep(delay)

    all_records = kept + new_records
    all_records.sort(key=lambda r: r["rank"])

    output = {
        "source": RANKING_URL,
        "ranking_month": month,
        "top_n": "all",
        "count": len(all_records),
        "databases": all_records,
    }
    save_db(DB_FILE, output)
    print(f"\n已更新 {DB_FILE}：{len(all_records)} 条（新增 {len(new_records)}，移除 {len(removed)}）")
    write_diff_report(output, old_data)

    if new_records:
        new_urls = {r["detail_url"] for r in new_records}
        pending_items = [
            {"index": i, "rank": r["rank"], "dbms": r["dbms"], "description": r["description"], "developer": r["developer"]}
            for i, r in enumerate(all_records) if r["detail_url"] in new_urls
        ]
        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            json.dump({"items": pending_items}, f, ensure_ascii=False, indent=2)
        print(f"新增系统的 description/developer 待翻译，已写入 {PENDING_FILE}（{len(pending_items)} 条）")
        print(f"翻译格式: {{\"items\": [{{\"index\": <上面清单里的 index>, \"description_cn\": \"...\", \"developer_cn\": \"...\"}}]}}")
        print(f"翻译完成后运行: python incremental_update.py --merge-translations {PENDING_FILE}")
    else:
        print("无新增系统，无需翻译。运行 python fix_data.py 兜底规范化后即可 build_html.py 重新生成页面。")


def cmd_merge(path):
    data = load_db(DB_FILE)
    with open(path, encoding="utf-8") as f:
        trans = json.load(f)
    recs = data["databases"]
    for item in trans["items"]:
        idx = item["index"]
        recs[idx]["description_cn"] = item.get("description_cn", "")
        recs[idx]["developer_cn"] = item.get("developer_cn", "")
    save_db(DB_FILE, data)
    print(f"已合并 {len(trans['items'])} 条译文到 {DB_FILE}")
    print("接下来运行: python fix_data.py && python build_html.py")


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="DB-Engines 增量更新（不重抓已有系统内页）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--diff", action="store_true", help="预览变化，不写文件")
    g.add_argument("--apply", action="store_true", help="执行增量更新")
    g.add_argument("--merge-translations", metavar="FILE", help="合并新增系统的翻译结果")
    ap.add_argument("--delay", type=float, default=1.5, help="新增系统内页请求间隔秒数（默认 1.5）")
    args = ap.parse_args()

    if args.diff:
        cmd_diff()
    elif args.apply:
        cmd_apply(args.delay)
    elif args.merge_translations:
        cmd_merge(args.merge_translations)


if __name__ == "__main__":
    main()
