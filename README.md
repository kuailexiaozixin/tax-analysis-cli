# tax-analysis-cli

在终端里完成税务问题分析：判断题型与前提缺口、核对依据覆盖、检索法规、
读原文并核对时效与效力，最后按模板产出结构化底稿；账套巡检、稽查模拟、
合同受理与内控生成也在同一套命令里。

适合税务顾问、会计和分析人员把分析过程写进脚本、批处理或本地留档。包内
自带引擎快照，不依赖同级目录或其他项目；人读结果直接打印，加 `--json`
给程序消费。

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

输出里的「引擎」就是 `engine_root`，指向包内自带的 `runtime/`，不是外部
目录；加 `--json` 可以看到 `"status": "ok"` 和完整字段。

`classify` 输出（节选）：

```text
题型：政策查询（lookup，把握 0.85）
判型依据：命中 2 个该类信号词
题面未交代：time、entity、place、scale
建议先问：
  · 时点：这笔业务发生在什么时间？涉及哪个纳税年度？
这类题要答到位，需要：对应的现行有效法条或文件
结论应包含：结论 + 效力位阶 + 文号 + 生效时点
```

`tax-analysis` 不在 `PATH` 时，用 `python -m tax_engine_cli ...` 运行；未安装
时在仓库根目录先设 `PYTHONPATH=src`（PowerShell：`$env:PYTHONPATH='src'`）。

Windows 的 Git Bash 等终端若中文显示乱码，设 `PYTHONUTF8=1` 再运行
（PowerShell：`$env:PYTHONUTF8='1'`）；`--json` 输出同样受此影响。

## 环境

- Python ≥ 3.10；依赖见 `pyproject.toml`。
- `playwright` 只在税屋 WAF 挑战那条路用，浏览器取系统已安装的
  Edge/Chrome/Firefox。

## 能做什么

| 任务 | 命令 | 得到什么 |
|---|---|---|
| 判型 | `classify` | 题型、把握度、题面缺口与建议追问（离线） |
| 依据覆盖 | `coverage` | 必备依据逐项状态与覆盖率；区分「没检」与「检了没有」 |
| 检索 | `search`、`search-gov` | 六源聚合；或只查税务总局站内／法规库，并叠加时效、文种、文号等条件 |
| 读法规 | `law info`、`law text`、`law interpretations`、`law related` | 元数据、正文段落、官方解读、税屋／公众号／全网实务线索 |
| 分析 | `analyze plan`、`analyze gather`、`analyze answer` | 检索计划；逐轮取数与定级；一次跑完的结构化底稿（不写最终答复） |
| 算式 | `calc list`、`calc run` | 算式骨架与参数化展开；缺参数、多余参数都会报出 |
| 类案 | `cases` | 税务总局查处通报与曝光典型的台账 |
| 检查件 | `check` 下的 `ledger`、`inspect`、`intake`、`intake-blank`、`reconcile`、`control` | 账套巡检、稽查问询、多合同受理、条款对账、九要素内控制度 |
| 词表与模板 | `health`、`tax-types`、`templates` | 引擎状态、33 个税种/专题、输出模板原文 |

`search`、`search-gov`、`law`、`cases` 与 `analyze gather` / `analyze answer`
需要联网；其余命令离线可用。

## 常用示例

```bash
# 单源检索并翻页
tax-analysis search "增值税" --source npc --page 2 --size 5

# 税务总局法规库，按文种收窄
tax-analysis search-gov "研发费用加计扣除" --source fgk \
  --doc-type 财政部税务总局公告 --size 5

# 公式展开
tax-analysis calc run 从价计征 --params '{"计税依据": 100, "税率": 0.05}'

# 整题分析：只取数定级，不抓正文、不核引用
tax-analysis analyze answer "研发费用加计扣除比例是多少" \
  --no-body --no-check-citations --max-per-round 3

# 取空白受理表，填好合同名称后交回
tax-analysis check intake-blank --json > document.json
```

`--evidence`、`--params` 一类 JSON 参数既收内联 JSON，也收 `@文件路径`；
`check` 的账套/合同参数与 `--diagnosis` 直接收文件路径。

## 输出与退出码

所有命令都支持 `--json`，返回完整结构化结果；不加时打印人读文本。

| 退出码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 程序内部错误 |
| 2 | 参数不合法、缺参数、多源翻页等请求错误 |
| 3 | 法规或模板不存在 |
| 4 | 上游取数失败 |
| 130 | 用户中断（Ctrl-C） |

错误默认写 stderr；加 `--json` 时输出
`{"error":{"code","message","details"}}`，与 API、MCP 的语义一致。

## 限制

- 只产出结构化底稿，不写最终答复，也不调用付费模型。
- 多源聚合没有页码维度，`--page > 1` 直接报错；需要翻页时限定
  `--source npc`。
- `search-gov` 的法规库那一路没有页码，`--page > 1` 报错；`--body` 只对
  法规库有效。
- 取数失败按错误码返回，不会打印成「0 条」。
- 单进程同步工具，不负责并发；重试在取数层完成。

## 独立运行与测试

包内 `src/tax_engine_cli/runtime/` 是取数脚本、判据注册表与输出模板的只读
快照，`MANIFEST.json` 记录每个文件的 SHA-256；运行时不查环境变量，也不找
同级目录。

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

测试只用离线路径或替换服务函数，不联网。
