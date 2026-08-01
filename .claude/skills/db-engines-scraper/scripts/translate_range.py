# -*- coding: utf-8 -*-
"""
按区间翻译 database-info.json 的 *_cn 字段（供并行子代理使用，互不冲突）。

工作方式（对每条记录独立、就地回写，区间外不动）：
  python translate_range.py --start 20 --end 100

流程：脚本先为区间内记录用枚举表预填 database_model_cn / license_cn 并保存，
再输出需要人工（Claude）翻译的 description/developer 清单 JSON；
Claude 将译文写入 batch-<start>-<end>.json 后，运行：
  python translate_range.py --start 20 --end 100 --merge batch-20-100.json
"""

import argparse
import json
import sys

DB_FILE = "database-info.json"

MODEL_CN = {
    # 全称（Multi-model 悬浮框内的标准写法）
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
    "Multi-Model DBMS": "多模型数据库",
    # 排名页单模型简称（站点对非 Multi-model 系统的缩写显示）
    "Relational": "关系型数据库",
    "Document": "文档型数据库",
    "Document Stores": "文档型数据库",
    "Key-value": "键值数据库",
    "Graph": "图数据库",
    "Vector": "向量数据库",
    "Spatial": "空间数据库",
    "Time Series": "时序数据库",
    "Wide column": "宽列数据库",
    "RDF": "RDF 存储",
    "Native XML": "原生 XML 数据库",
    "Object oriented": "面向对象数据库",
    "Multivalue": "多值数据库",
    "Content": "内容存储",
    "Navigational": "导航式数据库",
    "Event": "事件存储",
    "Event Store": "事件存储",
    "NoSQL": "NoSQL 数据库",
    "Columnar": "列式数据库",
    "Observability": "可观测性平台",
}
LICENSE_CN = {"commercial": "商业许可", "Open Source": "开源"}


def translate_model(s):
    if not s:
        return ""
    return "，".join(MODEL_CN.get(p.strip(), p.strip()) for p in s.split(","))


def load():
    with open(DB_FILE, encoding="utf-8") as f:
        return json.load(f)


def save(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--merge", metavar="FILE")
    args = ap.parse_args()

    data = load()
    recs = data["databases"]

    if args.merge:
        with open(args.merge, encoding="utf-8") as f:
            trans = json.load(f)
        for item in trans["items"]:
            idx = item["index"]
            recs[idx]["description_cn"] = item.get("description_cn", "")
            recs[idx]["developer_cn"] = item.get("developer_cn", "")
        save(data)
        print(f"已合并 {len(trans['items'])} 条译文到区间 [{args.start}, {args.end})")
        return

    # 阶段1：预填枚举字段
    for i in range(args.start, min(args.end, len(recs))):
        recs[i]["database_model_cn"] = translate_model(recs[i]["database_model"])
        recs[i]["license_cn"] = LICENSE_CN.get(recs[i]["license"], recs[i]["license"])
    save(data)

    # 阶段2：输出待翻译清单
    out = []
    for i in range(args.start, min(args.end, len(recs))):
        r = recs[i]
        out.append({
            "index": i,
            "rank": r["rank"],
            "dbms": r["dbms"],
            "description": r["description"],
            "developer": r["developer"],
        })
    json.dump({"start": args.start, "end": args.end, "items": out}, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
