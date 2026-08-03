# -*- coding: utf-8 -*-
"""
把 .claude/skills/db-engines-scraper/SKILL.md 同步到 .trae/rules/db-engines-pipeline.md。
同时把 skill/scripts/*.py 复制到项目根目录，保持脚本版本一致。

设计原则：
- .claude/skills/db-engines-scraper/SKILL.md 是 canonical 来源。
- .trae/rules/db-engines-pipeline.md 是 SKILL.md 的项目根目录适配版本，专供 Trae 读取。
- 后续只要修改 SKILL.md 与本脚本，然后运行本脚本即可一键同步到 rule。

用法：
    python sync_skill_to_rule.py
"""

import re
import shutil
import sys
from pathlib import Path


# 脚本作用说明（与 skill 中保持一致）。同步脚本会在 rule 开头生成绝对路径表。
SCRIPT_ROLES = {
    "build_html.py": "把 JSON 注入 index.template.html → index.html",
    "fix_data.py": "修名字尾巴、规范化 model、枚举预填 model_cn/license_cn",
    "incremental_update.py": "排名月度更新：diff 预览 → apply → merge 译文",
    "retry_failed.py": "重抓 description + website 双空的记录",
    "scrape_db_engines.py": "抓排名页 + 434 个内页 → database-info.json",
    "translate_cn.py": "20 条/批顺序推进，进度存 .translate-progress.json",
    "translate_range.py": "按 [start,end) 区间输出待翻译清单 / 合并译文",
}


def reconfigure_streams():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def sync_scripts(repo: Path, skill_dir: Path):
    """把 skill/scripts/*.py 复制到项目根目录。"""
    src_dir = skill_dir / "scripts"
    copied = []
    for src in sorted(src_dir.glob("*.py")):
        dst = repo / src.name
        shutil.copy2(src, dst)
        copied.append(src.name)
    print(f"[sync] copied {len(copied)} scripts to repo root: {', '.join(copied)}")


def sync_assets(repo: Path, skill_dir: Path):
    """把 skill/assets/index.template.html 复制到项目根目录。"""
    src = skill_dir / "assets" / "index.template.html"
    dst = repo / "index.template.html"
    if src.exists():
        shutil.copy2(src, dst)
        print(f"[sync] copied asset to repo root: {dst.name}")
    else:
        print(f"[sync] warning: asset not found: {src}")


def make_script_table(repo: Path) -> str:
    """生成 rule 专用的脚本绝对路径表。"""
    lines = [
        "## 脚本绝对路径（项目根目录）\n",
        "\n",
        "| 脚本 | 绝对路径 | 作用 |\n",
        "|---|---|---|\n",
    ]
    for name, role in sorted(SCRIPT_ROLES.items()):
        abspath = (repo / name).resolve()
        display_name = name.replace(".py", "")
        lines.append(f"| {display_name} | `{abspath}` | {role} |\n")

    root = repo.resolve()
    lines.extend([
        "\n",
        "数据 / 模板文件：\n",
        f"- `{root / 'database-info.json'}` — 核心数据集（434 条，14 字段/条）\n",
        f"- `{root / 'index.template.html'}` — 页面模板（含 `__DATA_PLACEHOLDER__`）\n",
        f"- `{root / 'index.html'}` — 最终产物（单文件、零依赖、离线可开）\n",
        "\n",
    ])
    return "".join(lines)


def convert_skill_to_rule(skill_text: str, repo: Path) -> str:
    """将 SKILL.md 内容转换为 rule 内容。"""
    # 1. 提取 frontmatter 中的 description
    description = ""
    body = skill_text
    if skill_text.startswith("---"):
        fm_end = skill_text.find("---", 3)
        frontmatter = skill_text[3:fm_end]
        for line in frontmatter.splitlines():
            if line.startswith("description:"):
                description = line[len("description:"):].strip()
                break
        body = skill_text[fm_end + 3:].lstrip("\n")

    # 2. 路径适配：scripts/xxx.py -> xxx.py；assets/index.template.html -> index.template.html
    body = body.replace("assets/index.template.html", "index.template.html")
    body = re.sub(r"\bscripts/([a-z_]+\.py)", r"\1", body)
    # 把 skill 特有的措辞换成 rule/根目录语境
    body = body.replace("模板在 assets/ 下", "模板在项目根目录下")
    body = body.replace("本 SKILL.md 所在目录", "项目根目录")
    body = body.replace("维护本 Skill", "维护本规则")
    body = body.replace("本 SKILL.md 是", "本规则由 SKILL.md 同步生成，是")

    # 3. 在第一个顶级标题段落后插入绝对路径表
    first_heading_end = body.find("\n## ")
    if first_heading_end == -1:
        first_heading_end = len(body)
    intro = body[:first_heading_end]
    rest = body[first_heading_end:]
    body = intro + "\n" + make_script_table(repo) + rest

    # 4. 组装 rule frontmatter
    new_frontmatter = f"---\nalwaysApply: false\ndescription: {description}\n---\n\n"
    return new_frontmatter + body


def main():
    reconfigure_streams()
    repo = Path(__file__).resolve().parent
    skill_dir = repo / ".claude" / "skills" / "db-engines-scraper"
    skill_md = skill_dir / "SKILL.md"
    rule_md = repo / ".trae" / "rules" / "db-engines-pipeline.md"

    if not skill_md.exists():
        raise FileNotFoundError(f"skill md not found: {skill_md}")

    sync_scripts(repo, skill_dir)
    sync_assets(repo, skill_dir)

    skill_text = skill_md.read_text(encoding="utf-8")
    rule_text = convert_skill_to_rule(skill_text, repo)
    rule_md.write_text(rule_text, encoding="utf-8")

    print(f"[sync] {skill_md} -> {rule_md}")


if __name__ == "__main__":
    main()
