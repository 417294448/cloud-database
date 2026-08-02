---
alwaysApply: false
description: 从 DB-Engines (db-engines.com) 抓取数据库排名及各系统详情，生成中英双语 JSON 数据集（database-info.json）和可离线打开的多维分析静态页（index.html）。当用户提到抓取/更新 DB-Engines 排名、数据库排行榜、database-info.json、数据库多语言数据集、数据库分析页面/看板，或要求"重新抓取全部数据库信息"、"补充/更新 _cn 中文字段"、"生成数据库分析网页"、"检查/同步最新排名"、"增量更新数据库列表"时使用本 skill。涵盖完整流水线（抓取 -> 补抓 -> 清洗 -> 翻译 -> 生成静态分析页）和日常增量更新（diff -> 只抓新增 -> 合并）两条路径。
---

# DB-Engines 排名抓取、翻译与可视化

把 https://db-engines.com/en/ranking 的完整排名（434 个系统，单页无分页）及各系统内页 "Editorial information provided by DB-Engines" 表格，固化为带中英双语字段的 `database-info.json`，并生成单文件离线分析页 `index.html`。

## 脚本绝对路径（项目根目录）

| 脚本 | 绝对路径 | 作用 |
|---|---|---|
| build_html | `D:\github-code\cloud-database\build_html.py` | 把 JSON 注入 index.template.html → index.html |
| fix_data | `D:\github-code\cloud-database\fix_data.py` | 修名字尾巴、规范化 model、枚举预填 model_cn/license_cn |
| incremental_update | `D:\github-code\cloud-database\incremental_update.py` | 排名月度更新：diff 预览 → apply → merge 译文 |
| retry_failed | `D:\github-code\cloud-database\retry_failed.py` | 重抓 description + website 双空的记录 |
| scrape_db_engines | `D:\github-code\cloud-database\scrape_db_engines.py` | 抓排名页 + 434 个内页 → database-info.json |
| translate_cn | `D:\github-code\cloud-database\translate_cn.py` | 20 条/批顺序推进，进度存 .translate-progress.json |
| translate_range | `D:\github-code\cloud-database\translate_range.py` | 按 [start,end) 区间输出待翻译清单 / 合并译文 |

数据 / 模板文件：
- `D:\github-code\cloud-database\database-info.json` — 核心数据集（434 条，14 字段/条）
- `D:\github-code\cloud-database\index.template.html` — 页面模板（含 `__DATA_PLACEHOLDER__`）
- `D:\github-code\cloud-database\index.html` — 最终产物（单文件、零依赖、离线可开）


## 运行环境

- 依赖：Python 3.9+，`requests`、`beautifulsoup4`、`lxml`。缺依赖时 `pip install requests beautifulsoup4 lxml`。
- 纯静态页面，**不需要** Selenium/Playwright。
- 站点 robots.txt 对普通 UA 放行；脚本已带浏览器 UA、1.5s 请求间隔、3 次重试。
- 企业代理下若出现 `SSL: CERTIFICATE_VERIFY_FAILED`，脚本会自动降级为关闭证书校验并打印提示，属预期行为。

## 标准流水线（五步，按顺序执行）

```bash
# 1. 全量抓取（约 11~15 分钟，放后台运行）
python scrape_db_engines.py -o database-info.json

# 2. 补抓失败记录（代理抖动会导致个别内页字段为空；幂等，可多跑几遍）
python retry_failed.py database-info.json

# 3. 数据清洗 + 规范化 + model/license 枚举预翻译
python fix_data.py database-info.json

# 4. 翻译 description_cn / developer_cn（见下方"翻译流程"）
python translate_range.py --start 0 --end 75 --merge batch-0-75.json

# 5. 生成静态分析页（模板在项目根目录下，单文件离线可用）
python build_html.py -d database-info.json -t index.template.html -o index.html
```

脚本路径以项目根目录为基准；若用户工作目录有同名脚本副本，优先用副本以保持行为一致。

## 日常更新（已有 database-info.json 时优先用这个，不要走全量流水线）

DB-Engines 排名每月变化，但**大多数系统本身不变**——434 次内页请求里，99% 都是在重新下载没变过的内容。已有 `database-info.json` 时，用 `incremental_update.py` 做增量更新：只对新增系统抓内页，已有系统直接复用旧的 description/website/developer/license/`*_cn` 字段，只刷新排名页本身就能拿到的 `rank`（每次都变）和 `database_model`（偶尔变）。

**不要**用"总数变没变"来判断要不要更新——排名可能同时一增一减导致总数不变，但集合确实变了；也不要用总数判断"不用更新"就跳过整个流程。正确做法是**每次都重新抓一次排名页**（只有 1 次请求，很轻），然后按 `detail_url` 逐条 diff 出新增 / 移除 / 保留，而不是先看数量再决定。

```bash
# 1. 预览变化（不写文件，看清楚有哪些新增/移除/改名再决定要不要继续）
python incremental_update.py --diff

# 2. 执行更新：复用旧数据，只对新增系统抓内页；若有新增会输出 pending-translations.json
python incremental_update.py --apply

# 3a. 若第 2 步提示"无新增系统，无需翻译"，直接收尾：
python fix_data.py database-info.json
python build_html.py -d database-info.json -t index.template.html -o index.html

# 3b. 若有新增系统，先翻译 pending-translations.json 里列出的 description/developer
#     （规则同下方"翻译流程"），写成同结构文件后合并，再收尾：
python incremental_update.py --merge-translations pending-translations.json
python fix_data.py database-info.json
python build_html.py -d database-info.json -t index.template.html -o index.html
```

**关键设计点（为什么这样做是对的）：**

- diff 主键用 `detail_url` 而不是 `dbms` 名字——系统改名（如 Arango → ArangoDB）不会被误判成"移除一个+新增一个"，能正确识别为"改名"并只更新显示名；
- `database_model` 比较前必须先过一遍 `fix_data.py` 的 `clean_model_str()` 规范化，再和旧记录比。排名页解析出的原始值可能是简称（`RDF`），旧记录里是规范化后的全称（`RDF store`）——如果直接比较原始值和规范化值，**几乎所有单模型系统都会被误判为"模型变了"**，导致英文字段被错误地退化回简称。这个坑真实踩过：一次未加规范化的测试跑，把 182 条记录的 `database_model` 污染回了简称，靠事后 `fix_data.py` 兜底修复的；
- 已有系统的内页字段（尤其 `current_release`、`license`）**不会**因为增量更新而自动刷新，因为压根没有重新请求内页。DB-Engines 内页信息本身更新不频繁，如果用户明确要求"确认现有系统的版本号是否有更新"，必须走全量流水线（步骤 1）而非增量更新。

## 输出结构

顶层：`source`、`ranking_month`（如 "July 2026"）、`top_n`（全量为 `"all"`）、`count`、`databases[]`。

`databases[]` 每条 14 个字段。抓取阶段（步骤 1~2）`*_cn` 为空；步骤 3 预填 `database_model_cn` 和 `license_cn`；步骤 4 填充 `description_cn` 和 `developer_cn`：

```json
{
  "rank": 1,
  "dbms": "Oracle",
  "database_model": "Relational DBMS, Document store, Graph DBMS, RDF store, Spatial DBMS, Vector DBMS",
  "database_model_cn": "关系型数据库，文档型数据库，图数据库，RDF 存储，空间数据库，向量数据库",
  "detail_url": "https://db-engines.com/en/system/Oracle",
  "description": "Widely used RDBMS",
  "description_cn": "广泛使用的关系型数据库",
  "website": "https://www.oracle.com/database/",
  "developer": "Oracle",
  "developer_cn": "甲骨文（Oracle）",
  "initial_release": "1980",
  "current_release": "26ai",
  "license": "commercial",
  "license_cn": "商业许可"
}
```

## 字段提取规则（排查数据问题时参考）

- **rank**：排名页当月列（Jul 2026）的序号。站点对并列排名统一给同一名次（末段大量 `#387`），不是解析错误。
- **dbms**：取 `<a>` 文本时**必须剔除 `span.info` 悬浮框**——厂商会塞 `Detailed vendor-provided information available` 标记，否则名字带尾巴（7 条历史数据曾中招：TimescaleDB/CockroachDB/TiDB/Arango/VictoriaMetrics/GridDB/VictoriaLogs）。当前脚本已修复，旧数据用 `fix_data.py` 兜底。
- **database_model**：含 "Multi-model" 时展开 infobox 细分列表（`, ` 连接，主模型在前）；单一模型保持原文但 `Relational` 规范为 `Relational DBMS`。**infobox 可能混入厂商营销文案**（CockroachDB 案例：整段英文描述被塞进去），标准模型名 ≤30 字符，超长的要过滤——`fix_data.py` 已处理。
- **website**：取内页链接的 `href`（显示文本含软连字符 `&shy;` 断行，不可用）。
- **内页字段缺失是正常的**：部分系统内页没有 License 行或整个 Editorial 表格不全（如 Project Voldemort 无 Description），留空即可，不要当作解析失败去重试。判定抓取失败用 `description + website` 双空。
- **infobox 悬浮注释一律剔除**：字段值里 `<span class=info>` 内是补充说明，不属于正文。

## 翻译流程（步骤 4）

`database_model_cn` 和 `license_cn` 由 `fix_data.py` 用枚举表预填，**不需要翻译接口**。只有 `description_cn` 和 `developer_cn` 需要逐条翻译。

434 条数据建议**分区间并行**处理（每区间 75 条，6 个子代理）。如果不需要并行，也可以用 `translate_cn.py` 按 20 条/批顺序推进（进度保存在 `.translate-progress.json`），作为 `translate_range.py` 的替代方案：

```bash
python translate_cn.py --extract     # 输出当前批次待翻译内容
# 翻译后写入 translations-batch.json
python translate_cn.py --merge translations-batch.json
```

分区间并行方案（推荐）：

```bash
# 每个子代理执行（以区间 [0,75) 为例）：
python translate_range.py --start 0 --end 75            # 输出待翻译清单 JSON
# -> 人工/Claude 翻译后写 batch-0-75.json，格式：
#    {"items": [{"index": 0, "description_cn": "...", "developer_cn": "..."}, ...]}
python translate_range.py --start 0 --end 75 --merge batch-0-75.json
```

区间划分（JSON 索引，非 rank）：`[0,75)` `[75,150)` `[150,225)` `[225,300)` `[300,375)` `[375,434)`，每个子代理只写自己区间，互不冲突。

**翻译规则：**

- `description`：通顺意译，保留产品名/技术名词原文（Hadoop、ACID、RDBMS、BigTable 等）；英文为空则留空 `""`。
- `developer`：公司/机构用通行中文名（Microsoft→微软、Google→谷歌、Amazon→亚马逊、Oracle→甲骨文、IBM/SAP→IBM/SAP、Apache Software Foundation→Apache 软件基金会、MongoDB, Inc→MongoDB 公司）；**个人姓名保留原文**（Dwayne Richard Hipp、Salvatore Sanfilippo 等）；多个主体用顿号"、"连接；**英文为空则按语境补**——知名开源项目填"开源社区"，能确定归属的填公司中文名（CloudKit→苹果、Infinispan→Red Hat、gStore→北京大学），无法确定填"开源社区"。
- `license` 有 13 条非标准值（不是 `Open Source`/`commercial`），如 ArangoDB 的 BSL 1.1 转换条款、SpacetimeDB 的 4 年转 AGPL，需要人工精译，不能枚举查表。

## 静态分析页（步骤 5）

`build_html.py` 把 `database-info.json` 内嵌进模板生成**单文件、零外部依赖、可离线双击打开**的 `index.html`（约 300 KB）。已内置的功能：

- 多维筛选：数据库模型（19 种主模型）/ 许可证 / 首次发布年代 / 排名区间，可叠加
- 搜索：同时索引中英文字段（搜"甲骨文"和"Oracle"等价）
- 可视化：统计卡、模型 Top10 条形图、许可证环形图（SVG 手绘，无图表库），随筛选联动
- 表格：6 列排序、Top10 高亮、点击行名弹详情卡（含官网/DB-Engines 链接）、分页
- 中英文一键切换（界面文案 + 数据字段同步），暗色主题，localStorage 持久化偏好
- 顶栏右侧固定返回主站链接（https://www.cloudproduct.top/，`target="_blank"` 新标签打开，i18n 词条 `home`）
- 导出当前筛选结果为 CSV（带 BOM，Excel 不乱码）

**注意：**

- 数据更新后只需重跑步骤 5 即可刷新页面，模板 `index.template.html` 不变；
- 模板里的数据占位符是 `__DATA_PLACEHOLDER__`，`build_html.py` 幂等——对已经注入过数据的 HTML 也能重新替换数据块；
- 若用户想改页面样式/功能，改的是**模板文件**，不是生成的 index.html（否则下次构建会被覆盖）；
- 页面验证：有 node 时用 `node --check` 校验提取出的 JS，无 node 就检查数据块能被 json.loads 解析、无 `http(s)://` 外部资源引用。

## 验收清单（全部完成后向用户汇报前必做）

1. `count` 等于排名页声明的系统数（当前 434）；
2. `description + website` 均空的记录为 0 或个位数（多则重跑 `retry_failed.py`）；
3. `database_model_cn` 无未翻译英文（注意 "RDF 存储"/"XML"/"NoSQL"/"SQL" 是合法译文，验证时加入白名单）；
4. `license_cn`：英文非空的记录全部有中文（`fix_data.py` + 13 条非标准值人工补）；
5. `developer_cn`：434 条全非空；
6. 抽查 Top 10、末位几条、以及曾出问题的 CockroachDB（#69）/Arango（#81）；
7. 若生成了 index.html：数据块可 `json.loads` 解析、无外部资源引用、JS 括号平衡（有 node 则 `node --check` 通过）；
8. 若走的是增量更新：抽查若干条**未变化**的系统，确认其内页字段（description/website/developer/license）与更新前完全一致，不应有变化——若有变化说明 diff 逻辑退化，需要排查。

## 已知特例

- `searchxml`（并列 387 段）内页长期返回异常/无 Editorial 表格，字段留空属预期，反复重试无意义。
- 排名页"单模型简称"有 18 种（`Key-value`/`Time Series`/`Document`/`Graph` 等），与 Multi-model 悬浮框里的全称不一致——`fix_data.py` 的 `MODEL_NORMALIZE` 负责统一，枚举表 `MODEL_CN` 同时覆盖简称与全称，新增模型类型时两处都要加。

## 维护本规则（变更后必须同步）

本规则由 SKILL.md 同步生成，是 DB-Engines 流水线的**唯一主要来源**。任何流程、规则、脚本或验收清单的变更都应先改这里，然后**立即执行同步**，确保 `.trae/rules/db-engines-pipeline.md` 和项目根目录脚本与 skill 保持一致。不同步会导致 Trae 读取的 rule 和实际脚本行为不一致。

```bash
python sync_skill_to_rule.py
```

该脚本会：
1. 将 `scripts/` 下的 Python 脚本复制到项目根目录，保持根目录与 skill 内脚本一致；
2. 将 SKILL.md 转换为 rule 格式（路径适配为根目录、追加绝对路径表）并写入 `.trae/rules/db-engines-pipeline.md`。

**建议**：提交 skill 变更前，把 `python sync_skill_to_rule.py` 作为必经步骤；如果希望完全自动化，可在本地仓库配置 `pre-commit` 或 CI 流程，在提交前自动运行该脚本。
