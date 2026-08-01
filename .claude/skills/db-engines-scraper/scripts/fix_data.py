# -*- coding: utf-8 -*-
"""
抓取后的数据清洗与规范化（在 retry_failed.py 之后运行）：

1. 修复 dbms 名字里的厂商悬浮框尾巴（"XXX Detailed vendor-provided information available" -> "XXX"）；
   —— 新版 scrape_db_engines.py 已在源头修复，此步仅作兜底（兼容旧数据）。
2. 过滤 database_model 里 infobox 混入的厂商营销文案（标准模型名 ≤30 字符）。
3. 英文 model 规范化：排名页单模型简称 -> 全称（Relational -> Relational DBMS 等）。
4. 用枚举表重新翻译所有 database_model_cn、兜底 license_cn。

运行: python fix_data.py [json文件路径]      # 默认 database-info.json
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from translate_range import MODEL_CN, LICENSE_CN  # noqa: E402

# 排名页单模型简称 -> 全称（站点对非 Multi-model 系统的缩写显示）
MODEL_NORMALIZE = {
    "Relational": "Relational DBMS",
    "Document": "Document store",
    "Document Stores": "Document store",
    "Key-value": "Key-value store",
    "Graph": "Graph DBMS",
    "Vector": "Vector DBMS",
    "Spatial": "Spatial DBMS",
    "Time Series": "Time Series DBMS",
    "Wide column": "Wide column store",
    "RDF": "RDF store",
    "Native XML": "Native XML DBMS",
    "Object oriented": "Object oriented DBMS",
    "Multivalue": "Multivalue DBMS",
    "Content": "Content store",
    "Navigational": "Navigational DBMS",
    "Event": "Event store",
    "NoSQL": "NoSQL DBMS",
    "Columnar": "Columnar DBMS",
}

VENDOR_SUFFIX = " Detailed vendor-provided information available"
MAX_MODEL_LEN = 30  # 标准模型名最长 "Object oriented DBMS" = 20 字符，留余量


def translate_model(s: str) -> str:
    if not s:
        return ""
    return "，".join(MODEL_CN.get(p.strip(), p.strip()) for p in s.split(","))


def clean_model_str(s: str) -> str:
    """规范化英文 model：过滤超长营销文案、简称转全称、去重保序。"""
    if not s:
        return ""
    parts = [p.strip() for p in s.split(",") if p.strip()]
    parts = [p for p in parts if len(p) <= MAX_MODEL_LEN]
    parts = [MODEL_NORMALIZE.get(p, p) for p in parts]
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return ", ".join(out)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    json_file = sys.argv[1] if len(sys.argv) > 1 else "database-info.json"
    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)

    fixed_names = 0
    fixed_models = 0
    for r in data["databases"]:
        if r["dbms"].endswith(VENDOR_SUFFIX):
            r["dbms"] = r["dbms"][: -len(VENDOR_SUFFIX)]
            fixed_names += 1

        new_model = clean_model_str(r["database_model"])
        if new_model != r["database_model"]:
            r["database_model"] = new_model
            fixed_models += 1

        r["database_model_cn"] = translate_model(r["database_model"])
        if not r["license_cn"] and r["license"]:
            r["license_cn"] = LICENSE_CN.get(r["license"], r["license"])

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"修复 dbms 名字: {fixed_names} 条，规范化 model: {fixed_models} 条")

    # 验证：model_cn 是否还有未翻译的英文（RDF/XML/NoSQL/SQL 等技术缩写除外）
    ALLOWED = {"RDF", "XML", "NoSQL", "SQL"}
    bad = []
    for i, r in enumerate(data["databases"]):
        m = r["database_model_cn"]
        if not m:
            bad.append((i, r["dbms"], "(空)"))
            continue
        tmp = m
        for w in ALLOWED:
            tmp = tmp.replace(w, "")
        if re.search(r"[A-Za-z]{2,}", tmp):
            bad.append((i, r["dbms"], m))
    print(f"model_cn 未翻译项: {len(bad)} 条")
    for i, name, m in bad:
        print(f"  idx={i} {name!r}: {m!r}")


if __name__ == "__main__":
    main()
