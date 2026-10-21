# tax-analysis-cli

在终端里完成一次税务问题分析：先判断题目在问什么、题面还缺哪些前提，再检索
现行有效的法规、读回原文、核对文号与时效，最后把材料按主依据、其他法定依据、
执行口径与实务认定、待核对线索分层整理成一份底稿。账套巡检、稽查模拟、合同
受理、条款对账和内控制度生成也在同一套命令里。

它不写最终答复，也不调用任何模型。每一步都可以单独运行；结果默认打印成人读
文本，加 `--json` 则输出完整结构，交给脚本或自建界面。

## 它解决什么问题

拿到一个税务问题，通常要依次弄清：

1. 这是政策查询、优惠资格判定、税负测算、办理流程，还是方案比较；
2. 回答它需要哪些依据，题面还缺哪些事实；
3. 现行有效的文件是哪一份，文号、时效和位阶是什么；
4. 账上或合同里的数字、条款能不能对上。

本工具把这些步骤做成命令行入口：前 3 步对应 `classify`、`coverage`、`analyze
plan`、`search`、`law`；第 4 步对应 `check` 下的六个检查命令。另有算式、类案、
模板和税种词表命令，共 24 个，全部列在下面的表里。判型、覆盖率、算式、检查和
模板都不联网；只有检索、读法规、找类案和整题分析会访问外部站点。

适合税务顾问、企业财税人员和需要把分析过程留档的团队。每次判型、检索、
定级和缺口都会留在输出里，方便复核，而不是只得到一段结论。

## 快速开始

```bash
cd tax-analysis-cli
python -m pip install -e .
tax-analysis health
tax-analysis classify "研发费用加计扣除比例是多少"
```

`health` 输出引擎位置与规模：

```text
引擎：<已安装包>/runtime
税种/专题：33 条｜算式骨架：6 条｜输出模板：11 个
检查时间：<运行时时间>
```

这里的「引擎」是包内自带的 `runtime/`，包含取数脚本、判据注册表和输出模板，
不是外部目录，也不需要另外安装一个项目。

`classify` 的实际输出（节选）：

```text
题型：政策查询（lookup，把握 0.85）
判型依据：命中 2 个该类信号词
题面未交代：time、entity、place、scale
建议先问：
  · 时点：这笔业务发生在什么时间？涉及哪个纳税年度？
这类题要答到位，需要：对应的现行有效法条或文件
结论应包含：结论 + 效力位阶 + 文号 + 生效时点
```

`classify` 的可选题型包括政策查询、优惠资格判定、税负测算、办理流程与时限、
合规风险判断、交易与事项定性、方案比较、术语填空和选项正确性判断。它只做
离线判断，不检索。

`tax-analysis` 不在 `PATH` 时，用 `python -m tax_engine_cli ...` 运行；未安装
时在仓库根目录先设 `PYTHONPATH=src`（PowerShell：`$env:PYTHONPATH='src'`）。

Windows 的 Git Bash 等终端若中文显示乱码，设 `PYTHONUTF8=1` 再运行
（PowerShell：`$env:PYTHONUTF8='1'`）；`--json` 输出同样受此影响。

## 能做什么

| 你想做的事 | 命令 | 命令返回什么 | 联网 |
|---|---|---|---|
| 确认安装是否可用 | `health` | 引擎根、税种与专题数、算式骨架数、模板数与检查时间 | 否 |
| 判断题型和题面缺口 | `classify "问题"` | 题型与把握度、判型依据、未交代的前提、建议追问、应覆盖的依据类型、结论要件 | 否 |
| 检查手里材料够不够 | `coverage 题型 --question "问题" --evidence @依据.json` | 必备依据逐项状态（已满足、缺、不适用、待核）、覆盖率、补问与下一步 | 否 |
| 先看该查什么 | `analyze plan "问题"` | 判型结果，加上每轮检索的目标、数据源和调用方式 | 否 |
| 六个来源一起搜 | `search "关键词"` | 标题、日期、时效状态、发布机关、链接或法规 ID；各源条数与失败原因 | 是 |
| 只搜税务总局或法规库 | `search-gov "关键词" --source chinatax` 或 `--source fgk` | 同上，并可按成文日期、时效、税种、文种、年份、文号、效力等级收窄 | 是 |
| 读一部法规 | `law info <id>`、`law text <id>` | 元数据（标题、文号、时效等）；正文段落数组 | 是 |
| 找官方解读 | `law interpretations "法规标题"` | 只来自 `.gov.cn` 的官方解读 | 是 |
| 找实务线索 | `law related <id>` | 税屋、微信公众号与 360 全网的相关网页，合并去重 | 是 |
| 一次跑完整题分析 | `analyze gather`、`analyze answer` | 逐轮证据与缺口；分层底稿（主依据、其他法定依据、执行口径与实务认定、待核对线索） | 是 |
| 展开算式 | `calc list`、`calc run` | 六条算式骨架；代入步骤与结果，缺参数和多余参数都会报错 | 否 |
| 找类案 | `cases "主题词"` | 税务总局查处通报与曝光典型的候选、过滤和去重台账 | 是 |
| 巡检账套 | `check ledger 账套.json` | 八要素风险条目、判不动清单、参数缺口与数据缺口 | 否 |
| 模拟稽查问询 | `check inspect` | 逐问生成六字段问询单元，并列出三类缺口 | 否 |
| 受理多份合同 | `check intake-blank`、`check intake 合同.json` | 空白受理表；九维度覆盖、待核抽取、没交的要素 | 否 |
| 条款与履行记录对账 | `check reconcile 合同.json` | 差异条目、无法确认条目和证据缺口 | 否 |
| 生成内控制度 | `check control` | 九要素制度文本；没有诊断时按通用模板生成并列出假设 | 否 |
| 看词表和模板 | `tax-types`、`templates list`、`templates show <key>` | 33 个税种或专题；11 个输出模板的标题与原文 | 否 |

`search` 的六个来源是：

| 源 | 覆盖的层 |
|---|---|
| `npc` | 全国人大法规库：法律、行政法规、司法解释 |
| `chinatax` | 国家税务总局：总局公告、部门规章、官方解读 |
| `so360` | 360 站内搜索：地方口径 |
| `shui5` | 税屋：实务解读 |
| `wechat` | 微信公众号：实务解读 |
| `ctax` | 中国税网：报刊转载与税案 |

`search` 默认查现行有效文件（`--status 3`）。状态值为 `1` 已废止、`2` 已修改、
`3` 现行有效、`4` 尚未生效。部分源取数失败时，失败原因写在 `meta.errors`，
不会被当成「该源没有内容」。

## 怎么用

### 1. 只判断这题该怎么答（离线）

```bash
tax-analysis classify "我们公司招用退役士兵，能扣减哪些税？" --json

tax-analysis coverage entitlement \
  --question "我们公司招用退役士兵，能扣减哪些税？" \
  --evidence @evidence.json --json

tax-analysis analyze plan "我们公司招用退役士兵，能扣减哪些税？"
```

`coverage` 的第一个参数是 `classify` 返回的题型代号（如 `lookup`、
`entitlement`、`liability`）。`--evidence` 传依据清单：不传表示「还没检」，
传 `[]` 表示「检了，没有找到」。这两种情况在结果里是不同状态，不会混成
一个「0%」。

### 2. 查法规并读原文

```bash
# 先拿到法规 ID：NPC 单源结果里会打印 id=<bbbs 编号>
tax-analysis search "中华人民共和国增值税暂行条例" --source npc --exact --size 3

tax-analysis law info <bbbs_id>
tax-analysis law text <bbbs_id>
tax-analysis law interpretations "中华人民共和国增值税暂行条例" --keyword 增值税
tax-analysis law related <bbbs_id> --keyword 税率
```

`law info` 和 `law text` 接收 NPC 法规库的 bbbs 编号；这个编号来自 `search`
的 NPC 结果或 `law info` 的返回。`law text` 的 `available=false` 只表示这次
下载或解析没成功，不等于该法规没有正文。

税务总局站内和税务法规库用另一条命令：

```bash
# 税务总局站内，可按文种、年份、文号等收窄
tax-analysis search-gov "研发费用加计扣除" --source chinatax \
  --doc-type 财政部税务总局公告 --size 5

# 税务法规库，可连同正文一起取回
tax-analysis search-gov "研发费用加计扣除" --source fgk --size 5 --body
```

`search-gov` 的 `fgk` 一路没有页码；`--body` 也只对 `fgk` 有效，对
`chinatax` 使用会报参数错误。

### 3. 一次跑完检索和分层

```bash
tax-analysis analyze answer "研发费用加计扣除比例是多少" \
  --max-per-round 3 --json > answer.json
```

`analyze answer` 会先判型、生成检索计划，再按轮取数、定级并整理成底稿。
结果包含 `primary`（主依据）、`supporting`（其他法定依据）、`practice`
（执行口径与实务认定）、`to_verify`（待核对线索），以及 `conditions`、
`repealed`、`pending`、`citation_note` 等字段。它不写最终答复。

耗时主要来自联网取数和读正文。想先快速看证据，可以跳过慢步骤：

```bash
tax-analysis analyze gather "研发费用加计扣除比例是多少" \
  --no-body --no-check-citations --max-per-round 5 --json
```

- `--no-body`：不取税屋正文。
- `--no-check-citations`：不回官方库核对文号。
- `--max-per-round`：每轮每个源最多取几条，取值 1–200。
- `--at YYYY-MM-DD`：按指定观察时点判断时效，省略则按当前时间。

### 4. 检查账套、合同和内控

```bash
# 账套巡检：账套 JSON + 可选参数 JSON
tax-analysis check ledger ledger.json --params params.json --json

# 稽查模拟：没有 answers 也能生成问询单元
tax-analysis check inspect --json > diagnosis.json
tax-analysis check inspect --answers answers.json --json > diagnosis.json

# 多合同受理：先取空白表，填好合同名称等字段后交回
tax-analysis check intake-blank --json > document.json
tax-analysis check intake document.json --json
tax-analysis check reconcile document.json --json

# 把稽查结果转成九要素内控制度
tax-analysis check control --diagnosis diagnosis.json --json
```

`check intake-blank` 返回一份可编辑的 `document`，至少包含一条合同占位记录；
修改时要保留原有字段名，并填写合同名称。`check intake` 和 `check reconcile`
都接收这份文档。账套、合同和参数文件都必须是 UTF-8 JSON；缺字段时命令会
报 `invalid_request` 并指出缺哪一格，不会猜数。

### 5. 算式、类案和模板

```bash
tax-analysis calc list
tax-analysis calc run 从价计征 --params '{"计税依据": 100, "税率": 0.05}'

tax-analysis cases 虚开增值税专用发票 --limit 5 --json

tax-analysis templates list
tax-analysis templates show analysis
```

`calc run` 只做算式展开，不内置现行税率或扣除标准；参数要从检索到的文件
或你的业务数据里取。`calc` 的骨架共 6 条，`templates` 的模板共 11 个。

## 输入约定

- `--params`、`--evidence` 等 JSON 参数既收内联 JSON，也收 `@文件路径`。
- `check ledger`、`check intake`、`check reconcile`、`check control` 的文档
  参数直接收文件路径，不接受内联 JSON。
- `--json` 输出服务层的完整结果；字段名和层级与 MCP 工具返回的一致，API 在此
  基础上多一层 `data`/`meta` 信封。
- 日期使用 `YYYY-MM-DD`；检索词、法规标题和题面按原样传入，不要先改写。

## 输出与退出码

所有命令都支持 `--json`。不加时打印人读文本，加时打印完整 JSON。

| 退出码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 程序内部错误 |
| 2 | 参数不合法、缺参数、未知题型、未知骨架、多源翻页等请求错误 |
| 3 | 法规或模板不存在 |
| 4 | 上游取数失败 |
| 130 | 用户中断（Ctrl-C） |

错误默认写 stderr；加 `--json` 时输出 `{"error":{"code","message","details"}}`。

## 限制

- 只产出结构化底稿，不写最终答复，也不调用付费模型。
- 多源聚合没有页码维度，`--page > 1` 直接报错；需要翻页时限定
  `--source npc`。
- `search-gov` 的法规库那一路没有页码，`--page > 1` 报错；`--body` 只对
  法规库有效。
- 整次取数失败按错误码返回；多源里的单源失败会明确列出，不会当成「0 条」。
- 账套和合同检查按 JSON 里的字段判定；字段名不对或缺失时只报缺口，不猜测
  对应关系。
- 单进程同步工具，不负责并发；网络重试在取数层完成。
- `playwright` 只在税屋 WAF 挑战那条路使用，优先调用系统已安装的
  Edge、Chrome、Brave、360 或 Firefox，不额外下载内核。

## 独立运行与测试

包内 `src/tax_engine_cli/runtime/` 是取数脚本、判据注册表与输出模板的只读
快照，`MANIFEST.json` 记录每个文件的 SHA-256；运行时不查环境变量，也不找
同级目录。

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

测试用离线路径或替换服务函数，不访问外部站点。
