# -*- coding: utf-8 -*-
"""
将 Claude 生成的翻译文件合并回 database-info.json。

工作方式：
  1. 读取 .translate-progress.json 获取当前批次 offset（首次运行自动创建）；
  2. 提取该批次记录的 4 个待翻字段，写到 stdout（由 Claude 翻译）；
  3. Claude 把译文写成 translations-batch.json 后，用 --merge 合并并推进 offset。

用法：
  python translate_cn.py --extract          # 输出当前批次待翻译内容（JSON 到 stdout）
  python translate_cn.py --merge <文件>      # 合并 Claude 译文并回写 database-info.json
  python translate_cn.py --status           # 查看进度
"""

import argparse
import json
import sys
from pathlib import Path

DB_FILE = "database-info.json"
PROGRESS_FILE = ".translate-progress.json"
BATCH_SIZE = 20

# ---------- 枚举映射（database_model / license） ----------
MODEL_CN = {
    "Relational DBMS": "关系型数据库",
    "Document store": "文档型数据库",
    "Key-value store": "键值数据库",
    "Graph DBMS": "图数据库",
    "Vector DBMS": "向量数据库",
    "Spatial DBMS": "空间数据库",
    "Time Series DBMS": "时序数据库",
    "Search engine": "搜索引擎",
    "Wide column store": "宽列数据库",
    "RDF store": "RDF 存储",
    "Native XML DBMS": "原生 XML 数据库",
    "Object oriented DBMS": "面向对象数据库",
    "Multivalue DBMS": "多值数据库",
    "Content store": "内容存储",
    "Navigational DBMS": "导航式数据库",
    "Event store": "事件存储",
    "NoSQL DBMS": "NoSQL 数据库",
    "Columnar DBMS": "列式数据库",
}
LICENSE_CN = {
    "commercial": "商业许可",
    "Open Source": "开源",
}


def translate_model(model_str: str) -> str:
    """按 ', ' 拆分枚举翻译；遇到未知项保留原文。"""
    if not model_str:
        return ""
    parts = [p.strip() for p in model_str.split(",")]
    return "，".join(MODEL_CN.get(p, p) for p in parts)


def translate_license(lic: str) -> str:
    return LICENSE_CN.get(lic, lic)


def load_db():
    with open(DB_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_progress():
    p = Path(PROGRESS_FILE)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"offset": 0}


def save_progress(prog):
    Path(PROGRESS_FILE).write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_extract():
    data = load_db()
    prog = load_progress()
    recs = data["databases"]
    start = prog["offset"]
    batch = recs[start:start + BATCH_SIZE]
    if not batch:
        print(json.dumps({"done": True, "total": len(recs)}, ensure_ascii=False))
        return
    out = {
        "done": False,
        "offset": start,
        "batch_size": len(batch),
        "total": len(recs),
        "items": [
            {
                "rank": r["rank"],
                "dbms": r["dbms"],
                "database_model": r["database_model"],
                "description": r["description"],
                "developer": r["developer"],
                "license": r["license"],
            }
            for r in batch
        ],
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()


def cmd_merge(path):
    with open(path, encoding="utf-8") as f:
        trans = json.load(f)
    data = load_db()
    prog = load_progress()
    recs = data["databases"]
    items = trans["items"]
    start = prog["offset"]
    for i, t in enumerate(items):
        r = recs[start + i]
        # 枚举字段：优先用 Claude 译文，缺失时本地查表兜底
        r["database_model_cn"] = t.get("database_model_cn") or translate_model(r["database_model"])
        r["description_cn"] = t.get("description_cn", "")
        r["developer_cn"] = t.get("developer_cn", "")
        r["license_cn"] = t.get("license_cn") or translate_license(r["license"])
    prog["offset"] = start + len(items)
    save_db(data)
    save_progress(prog)
    print(f"已合并 {len(items)} 条，进度 {prog['offset']}/{len(recs)}")


def cmd_status():
    data = load_db()
    prog = load_progress()
    total = len(data["databases"])
    done = prog["offset"]
    filled = sum(1 for r in data["databases"] if r["description_cn"] or r["database_model_cn"])
    print(f"进度 offset: {done}/{total}（剩余 {total - done}），已含中文字段的记录: {filled}")


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--merge", metavar="FILE")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.extract:
        cmd_extract()
    elif args.merge:
        cmd_merge(args.merge)
    elif args.status:
        cmd_status()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
