# -*- coding: utf-8 -*-
"""
生成 database-info.json 的变更 diff 报告。

供 scrape_db_engines.py（全量抓取）和 incremental_update.py（增量更新）在写回数据后调用，
输出统一格式的文本报告到 diffs/refresh-diff-YYYY-MM-DD.txt。
"""

import json
import sys
from datetime import date
from pathlib import Path

DIFF_DIR = Path("diffs")


def reconfigure_streams():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def diff_records(old_records, new_records):
    """
    按 detail_url 对比两组记录。

    返回 dict:
      - added: 新增记录列表
      - removed: 移除记录列表
      - renamed: [(旧名, 新名, detail_url), ...]
      - rank_changed: [{dbms, old_rank, new_rank, detail_url}, ...]
      - model_changed: [{dbms, old_model, new_model, detail_url}, ...]
      - kept: 完全未变化的记录列表
    """
    old_by_url = {r["detail_url"]: r for r in old_records}
    new_by_url = {r["detail_url"]: r for r in new_records}

    added = [new_by_url[url] for url in new_by_url if url not in old_by_url]
    removed = [old_by_url[url] for url in old_by_url if url not in new_by_url]
    kept_urls = set(old_by_url) & set(new_by_url)

    renamed = []
    rank_changed = []
    model_changed = []
    kept = []

    for url in kept_urls:
        old = old_by_url[url]
        new = new_by_url[url]

        changed = False
        if old["dbms"] != new["dbms"]:
            renamed.append((old["dbms"], new["dbms"], url))
            changed = True
        if old["rank"] != new["rank"]:
            rank_changed.append({
                "dbms": new["dbms"],
                "old_rank": old["rank"],
                "new_rank": new["rank"],
                "detail_url": url,
            })
            changed = True
        if old.get("database_model") != new.get("database_model"):
            model_changed.append({
                "dbms": new["dbms"],
                "old_model": old.get("database_model", ""),
                "new_model": new.get("database_model", ""),
                "detail_url": url,
            })
            changed = True

        if not changed:
            kept.append(new)

    return {
        "added": added,
        "removed": removed,
        "renamed": renamed,
        "rank_changed": rank_changed,
        "model_changed": model_changed,
        "kept": kept,
    }


def format_diff_report(old_data, new_data):
    """生成可读的 diff 报告文本。"""
    lines = []
    old_month = old_data.get("ranking_month", "?") if old_data else "无"
    new_month = new_data.get("ranking_month", "?")
    old_count = len(old_data["databases"]) if old_data else 0
    new_count = len(new_data["databases"])

    lines.append("=" * 60)
    lines.append("DB-Engines 数据变更报告")
    lines.append("=" * 60)
    lines.append(f"生成时间: {date.today().isoformat()}")
    lines.append(f"旧数据月份: {old_month}")
    lines.append(f"新数据月份: {new_month}")
    lines.append(f"旧记录数: {old_count}")
    lines.append(f"新记录数: {new_count}")
    lines.append(f"净变化: {new_count - old_count:+d}")
    lines.append("")

    if old_data is None:
        lines.append("本次为首次抓取，所有记录均为新增。")
        lines.append(f"新增系统: {new_count} 条")
        lines.append("")
        for r in sorted(new_data["databases"], key=lambda x: x["rank"])[:20]:
            lines.append(f"  + #{r['rank']} {r['dbms']} ({r['database_model']})")
        if new_count > 20:
            lines.append(f"  ... 共 {new_count} 条，仅展示前 20 条")
        lines.append("")
        lines.append("=" * 60)
        lines.append("报告结束")
        lines.append("=" * 60)
        return "\n".join(lines)

    result = diff_records(old_data["databases"], new_data["databases"])

    # 新增
    if result["added"]:
        lines.append(f"【新增系统】{len(result['added'])} 条")
        for r in sorted(result["added"], key=lambda x: x["rank"]):
            lines.append(f"  + #{r['rank']} {r['dbms']} ({r['database_model']})")
        lines.append("")

    # 移除
    if result["removed"]:
        lines.append(f"【移除系统】{len(result['removed'])} 条")
        for r in sorted(result["removed"], key=lambda x: x["rank"]):
            lines.append(f"  - #{r['rank']} {r['dbms']} ({r['database_model']})")
        lines.append("")

    # 改名
    if result["renamed"]:
        lines.append(f"【显示名变更】{len(result['renamed'])} 条")
        for old_name, new_name, _url in result["renamed"]:
            lines.append(f"  ~ {old_name} -> {new_name}")
        lines.append("")

    # 排名变化
    if result["rank_changed"]:
        lines.append(f"【排名变化】{len(result['rank_changed'])} 条")
        sorted_changes = sorted(
            result["rank_changed"],
            key=lambda x: abs(x["old_rank"] - x["new_rank"]),
            reverse=True,
        )
        for item in sorted_changes[:30]:
            delta = item["new_rank"] - item["old_rank"]
            sign = "+" if delta > 0 else ""
            lines.append(
                f"  {item['dbms']}: #{item['old_rank']} -> #{item['new_rank']} ({sign}{delta})"
            )
        if len(sorted_changes) > 30:
            lines.append(f"  ... 共 {len(sorted_changes)} 条，仅展示变化最大的 30 条")
        lines.append("")

    # 模型变化
    if result["model_changed"]:
        lines.append(f"【数据库模型变更】{len(result['model_changed'])} 条")
        for item in result["model_changed"]:
            lines.append(
                f"  {item['dbms']}: {item['old_model'] or '(空)'} -> {item['new_model'] or '(空)'}"
            )
        lines.append("")

    # 无变化摘要
    kept_count = len(result["kept"])
    lines.append(f"【未变化】{kept_count} 条（仅列出计数）")
    lines.append("")
    lines.append("=" * 60)
    lines.append("报告结束")
    lines.append("=" * 60)

    return "\n".join(lines)


def write_diff_report(new_data, old_data=None):
    """
    写入 diff 报告到 diffs/refresh-diff-YYYY-MM-DD.txt。
    如果文件已存在则追加数字后缀。
    """
    DIFF_DIR.mkdir(parents=True, exist_ok=True)
    base = DIFF_DIR / f"refresh-diff-{date.today().isoformat()}.txt"
    path = base
    counter = 1
    while path.exists():
        path = DIFF_DIR / f"refresh-diff-{date.today().isoformat()}-{counter}.txt"
        counter += 1

    report = format_diff_report(old_data, new_data)
    save_text(path, report)
    reconfigure_streams()
    print(f"\n[diff] 变更报告已保存: {path}")
    return path


def generate_diff_from_files(new_path, old_path=None):
    """
    从文件路径生成 diff 报告。
    如果未指定 old_path，则自动查找 new_path 所在目录的旧数据（默认与 new_path 同名）。
    """
    new_path = Path(new_path)
    if old_path is None:
        old_path = new_path
    else:
        old_path = Path(old_path)

    old_data = load_json(old_path) if old_path.exists() else None
    new_data = load_json(new_path)
    return write_diff_report(new_data, old_data)
