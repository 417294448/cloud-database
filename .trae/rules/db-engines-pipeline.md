---
alwaysApply: false
description: DB-Engines 数据库排名抓取与静态分析页生成流水线。当用户提到抓取/更新 DB-Engines 排名、数据库排行榜、database-info.json、数据库中英双语数据集、数据库分析页面/看板，或要求"重新抓取全部数据库信息"、"补充/更新 _cn 中文字段"、"生成数据库分析网页"、"检查/同步最新排名"、"增量更新数据库列表"时激活本规则。
---

# DB-Engines 数据库选型与分析流水线

本规则把项目根目录下的一组 Python 脚本串成完整流水线：**抓取 → 补抓 → 清洗 → 翻译 → 生成单文件离线分析页**。
所有脚本均为项目内既有文件，**绝对路径保持不变**，不要复制、移动或新建同名脚本。

## 脚本绝对路径（项目根目录）

| 脚本 | 绝对路径 | 作用 |
|---|---|---|
| 全量抓取 | `D:\github-code\cloud-database\scrape_db_engines.py` | 抓排名页 + 434 个内页 → `database-info.json` |
| 补抓失败 | `D:\github-code\cloud-database\retry_failed.py` | 重抓 `description + website` 双空的记录 |
| 数据清洗 | `D:\github-code\cloud-database\fix_data.py` | 修名字尾巴、规范化 model、枚举预填 `model_cn`/`license_cn` |
| 区间翻译 | `D:\github-code\cloud-database\translate_range.py` | 按 `[start,end)` 区间输出待翻译清单 / 合并译文 |
| 批次翻译 | `D:\github-code\cloud-database\translate_cn.py` | 20 条/批顺序推进，进度存 `.translate-progress.json` |
| 增量更新 | `D:\github-code\cloud-database\incremental_update.py` | 排名月度更新：diff 预览 → apply → merge 译文 |
| 生成页面 | `D:\github-code\cloud-database\build_html.py` | 把 JSON 注入 `index.template.html` → `index.html` |

数据 / 模板文件：
- `D:\github-code\cloud-database\database-info.json` — 核心数据集（434 条，14 字段/条）
- `D:\github-code\cloud-database\index.template.html` — 页面模板（含 `__DATA_PLACEHOLDER__`）
- `D:\github-code\cloud-database\index.html` — 最终产物（单文件、零依赖、离线可开）

## 环境

- Python 3.10+，依赖 `requests` / `beautifulsoup4` / `lxml`，缺则 `pip install requests beautifulsoup4 lxml`
- 纯 HTTP 抓取，**不需要** Selenium / Playwright
- 企业代理下 SSL 校验失败属预期，脚本会自动降级并打印提示
- Windows 终端默认 GBK，脚本内已统一 `reconfigure(encoding="utf-8")`

## 路径 A：首次全量构建（约 15 分钟）

```bash
cd /d D:\github-code\cloud-database

# 1. 全量抓取（--top 20 可只抓前 20 个，调试用）
python scrape_db_engines.py

# 2. 补抓代理抖动导致的空字段记录（幂等，可多跑）
python retry_failed.py

# 3. 清洗 + 规范化 + 枚举预翻译
python fix_data.py

# 4. 翻译 description_cn / developer_cn（见下方"翻译流程"）
python translate_range.py --start 0 --end 75
# ... 人工/AI 翻译后写 batch-0-75.json ...
python translate_range.py --start 0 --end 75 --merge batch-0-75.json

# 5. 生成静态分析页
python build_html.py
```

## 路径 B：日常增量更新（**优先用这个**，每月跑一次）

DB-Engines 排名每月更新，但 99% 系统本身没变。**不要**用"总数变没变"判断是否更新——排名可能一增一减导致总数不变但集合已变。正确做法是每次都重抓排名页（仅 1 次请求），按 `detail_url` 逐条 diff。

```bash
cd /d D:\github-code\cloud-database

# 1. 预览变化（不写文件）
python incremental_update.py --diff

# 2. 执行更新：复用旧数据，只对新增系统抓内页
python incremental_update.py --apply

# 3a. 若无新增，直接收尾
python fix_data.py && python build_html.py

# 3b. 若有新增，先翻译 pending-translations.json 里的 description/developer，
#     合并后再收尾
python incremental_update.py --merge-translations pending-translations.json
python fix_data.py && python build_html.py
```

**关键设计点：**
- diff 主键用 `detail_url` 而不是 `dbms` 名字——系统改名（Arango → ArangoDB）不会被误判为"移除+新增"
- `database_model` 比较前必须过 `fix_data.clean_model_str()` 规范化——否则单模型系统的英文 model 会从全称退化回简称（曾污染 182 条记录）
- 增量更新**不刷新**已有系统的 `current_release` / `license` 等内页字段；如需全量刷新内页，必须走路径 A

## 翻译流程（步骤 4）

`database_model_cn` 和 `license_cn` 由 `fix_data.py` 用枚举表预填，**不需要 LLM**。只有 `description_cn` 和 `developer_cn` 需要逐条翻译。

434 条建议**分区间并行**（每区间 75 条，6 个并行任务），区间按 JSON 索引而非 rank：
`[0,75)` `[75,150)` `[150,225)` `[225,300)` `[300,375)` `[375,434)`

每个区间：
```bash
python translate_range.py --start 0 --end 75          # 输出待翻译清单 JSON
# 翻译后写 batch-0-75.json，格式：
# {"items": [{"index": 0, "description_cn": "...", "developer_cn": "..."}, ...]}
python translate_range.py --start 0 --end 75 --merge batch-0-75.json
```

**翻译规则：**
- `description`：通顺意译，保留产品名/技术名词原文（Hadoop、ACID、RDBMS、BigTable 等）；英文空则留 `""`
- `developer`：公司用通行中文名（Microsoft→微软、Google→谷歌、Amazon→亚马逊、Oracle→甲骨文、Apache Software Foundation→Apache 软件基金会）；**个人姓名保留原文**（Dwayne Richard Hipp、Salvatore Sanfilippo）；多个主体用顿号"、"；**英文为空则按语境补**——知名开源项目填"开源社区"，能确定归属的填公司中文名（CloudKit→苹果、Infinispan→Red Hat、gStore→北京大学）
- `license` 有 13 条非标准值（如 ArangoDB 的 BSL 1.1 转换条款），需人工精译，不能枚举查表

## 数据结构

顶层：`source`、`ranking_month`（如 "July 2026"）、`top_n`、`count`、`databases[]`。
`databases[]` 每条 14 字段：`rank` / `dbms` / `database_model` / `database_model_cn` / `detail_url` / `description` / `description_cn` / `website` / `developer` / `developer_cn` / `initial_release` / `current_release` / `license` / `license_cn`。

## 静态分析页

`build_html.py` 把 JSON 内嵌进模板，生成**单文件、零外部依赖、可离线双击打开**的 `index.html`（约 300 KB）。已内置：

- 多维筛选：数据库模型（19 种主模型）/ 许可证 / 发布年代 / 排名区间，可叠加
- 搜索：同时索引中英文字段（搜"甲骨文"等价于搜"Oracle"）
- 可视化：统计卡、模型 Top10 条形图、许可证环形图（纯 SVG，无图表库），随筛选联动
- 表格：6 列排序、Top10 高亮、点击行名弹详情卡、分页
- 中英文一键切换（界面 + 数据同步）、暗色主题、localStorage 持久化偏好
- 导出当前筛选为 CSV（带 BOM，Excel 不乱码）

**注意：**
- 数据更新后只需重跑 `build_html.py`，模板不变
- 模板占位符 `__DATA_PLACEHOLDER__`，对已注入的 HTML 重跑是幂等的
- 想改样式/功能 → 改**模板文件**，不是生成的 `index.html`（否则下次构建被覆盖）

## 字段提取规则（排查数据问题时参考）

- `rank`：末段大量并列 `#387` 是站点对并列排名的处理，不是解析错误
- `dbms`：必须剔除 `<span class=info>` 悬浮框（厂商塞的 `Detailed vendor-provided information available`），否则名字带尾巴。当前脚本已修复，旧数据用 `fix_data.py` 兜底
- `database_model`：含 "Multi-model" 时展开 infobox 细分列表；infobox 可能混入厂商营销文案（CockroachDB 案例），按 ≤30 字符过滤
- `website`：取 `<a href>`，显示文本含软连字符 `&shy;` 断行不可用
- **内页字段缺失是正常的**：部分系统没有 License 行或 Editorial 表格不全（如 Project Voldemort 无 Description），留空即可。判定抓取失败用 `description + website` 双空

## 验收清单（汇报前必做）

1. `count` 等于排名页声明数（当前 434）
2. `description + website` 均空的记录为 0 或个位数（多则重跑 `retry_failed.py`）
3. `database_model_cn` 无未翻译英文（"RDF 存储"/"XML"/"NoSQL"/"SQL" 是合法译文，加白名单）
4. `license_cn`：英文非空的记录全有中文
5. `developer_cn`：434 条全非空
6. 抽查 Top 10、末位、CockroachDB（#69）/Arango（#81）
7. `index.html`：数据块可 `json.loads` 解析、无外部资源引用、JS 括号平衡
8. 走增量更新时：抽查未变化系统，确认其内页字段与更新前完全一致——若有变化说明 diff 退化

## 已知特例

- `searchxml`（并列 387 段）内页长期异常/无 Editorial 表格，字段留空属预期，反复重试无意义
- 排名页"单模型简称"有 18 种（`Key-value`/`Time Series`/`Document`/`Graph` 等），与 Multi-model 全称不一致——`fix_data.py` 的 `MODEL_NORMALIZE` 统一处理，枚举表 `MODEL_CN` 同时覆盖简称与全称，**新增模型类型时两处都要加**
