# -*- coding: utf-8 -*-
"""
把 database-info.json 注入 index.template.html，生成可直接离线打开的 index.html。

用法:
    python build_html.py                                  # 默认输入输出
    python build_html.py -d database-info.json -t index.template.html -o index.html
"""

import argparse
import json
import re
import sys


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="生成 DB-Engines 分析静态页")
    ap.add_argument("-d", "--data", default="database-info.json", help="数据 JSON（默认 database-info.json）")
    ap.add_argument("-t", "--template", default="index.template.html", help="HTML 模板（默认 index.template.html）")
    ap.add_argument("-o", "--output", default="index.html", help="输出文件（默认 index.html）")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)
    with open(args.template, encoding="utf-8") as f:
        template = f.read()

    payload = json.dumps(data, ensure_ascii=False)
    # 防止 JSON 内容中出现 "</script>" 提前闭合脚本块
    payload = payload.replace("</", "<\\/")

    if "__DATA_PLACEHOLDER__" in template:
        html = template.replace("__DATA_PLACEHOLDER__", payload)
    else:
        # 模板已被注入过（幂等）：替换现有数据块
        html = re.sub(
            r'(<script id="db-data" type="application/json">).*?(</script>)',
            lambda m: m.group(1) + payload + m.group(2),
            template,
            flags=re.S,
        )

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    n = len(data["databases"])
    size_kb = len(html.encode("utf-8")) / 1024
    print(f"生成完成: {args.output}（{n} 条记录，{size_kb:.0f} KB，月份: {data.get('ranking_month', '?')}）")


if __name__ == "__main__":
    main()
