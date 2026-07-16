# B3 说明生成与工具调用模块 — 个人模块 README

---

## 1. 模块概述

### 1.1 模块名称

`B3：说明生成与工具调用模块 (Tool Schema & Tool Calling Layer)`

### 1.2 模块说明

B3 是 B2（Skill 工具函数层）和 B4（LLM 决策层）之间的**桥接层**，承担不可替代的"翻译"和"调度"职责。

**解决的问题**：LLM 无法直接识别和调用本地 Python 函数。B2 的 Skill 是普通 Python 函数，B4 的 LLM 只能理解标准化的 JSON 格式工具描述。B3 在这两层之间建立桥梁。

**核心功能**：
- **输入 → tools_schema**：将 `tools.yaml` 中的工具定义（或 Python 函数注解）转换为 OpenAI Function Calling 标准格式，供 LLM 绑定
- **输入 → ToolMessage**：接收 LLM 返回的 `tool_calls`，经过三层安全校验后动态导入 B2 的 Skill 函数并执行，返回标准化的 `ToolMessage`

**为什么必要**：没有本模块，LLM 不知道有什么工具可用、每个工具需要什么参数。B2 的 5 个 Skill 函数将变成孤立的脚本，Agent 的"思考→调用工具→获取结果→继续思考"闭环无法形成。

### 1.3 完成情况概览

| 类型 | 完成情况 |
|---|---|
| 基础要求 | ✅ 全部完成（tools_schema 生成、tool_call 执行、错误处理、日志记录、CLI 独立运行） |
| 进阶要求 | ✅ 三项全部完成（自动从 Python 注解生成 schema、去重缓存与统计、Schema 描述对比） |
| 可独立运行的演示 | `python b3_tool_layer.py --export_schema --execute` 两种模式 |
| 与团队系统集成情况 | B1 通过 `get_tools_schema()` 和 `execute_tool_calls()` 两个接口调用 B3 |

---

## 2. 环境、模型与数据依赖

### 2.1 运行环境

| 项目 | 要求 |
|---|---|
| Python 版本 | 3.10+ |
| 必要依赖 | PyYAML >= 6.0（其余为 Python 标准库） |
| 是否需要模型 | 基础功能不需要；进阶验收需要 Qwen3.5-4B |
| 是否需要 GPU | 基础功能不需要；进阶验收需要 |
| 是否需要外部数据集 | 不需要（测试数据项目自带） |

### 2.2 模型依赖

| 模型 | 来源 | 项目内相对路径 | 用途 |
|---|---|---|---|
| Qwen3.5-4B | ModelScope | 由团队 B4 模块加载 | Schema 描述对比（进阶验收） |

基础功能不依赖任何模型，可完全独立运行。

### 2.3 数据集或样例数据依赖

| 数据或文件 | 来源 | 项目内相对路径 | 用途 |
|---|---|---|---|
| tools.yaml | 项目自带 | `configs/tools.yaml` | 工具注册表 |
| tool_calls 测试文件 | 项目自带 | `data/messages/*.json` | 演示正常/错误 tool_call |
| schema_selection_cases.json | 项目自带 | `data/b3_eval/` | 进阶验收测试用例 |
| agent_intro.txt | 项目自带 | `data/docs/` | file_reader 测试文件 |

### 2.4 安装步骤

```bash
pip install pyyaml
```

无需其他依赖，全部使用 Python 标准库。

---

## 3. 文件结构与接口边界

### 3.1 文件结构

```text
b3/
├── b3_tool_layer.py          # 核心：schema生成 + tool_call执行（510行）
├── b3_advanced.py            # 进阶：重试/缓存/统计/描述对比（399行）
├── b3_acceptance.py          # 验收：一键进阶功能检验（93行）
├── common/                   # 公共工具
│   ├── io_utils.py           #   JSON/YAML/JSONL 读写
│   ├── path_utils.py         #   路径解析与安全校验
│   ├── logging_utils.py      #   日志时间戳
│   └── schemas.py            #   ToolMessage 与 tool_call 标准化
├── skills/                   # B2 工具函数（B3 动态加载调用）
│   ├── calculator.py         #   安全数学计算
│   ├── file_reader.py        #   读本地 txt/md 文件
│   ├── local_file_search.py  #   BM25 文件内容搜索
│   ├── table_analyzer.py     #   CSV/TSV 分析与统计
│   ├── format_converter.py   #   Markdown/JSON 格式转换
│   └── core/                 #   B2 基础设施（invoker、context、errors）
│       ├── invoker.py        #   invoke_callable：真正执行 B2 函数
│       ├── context.py        #   make_context：创建执行上下文
│       └── errors.py         #   SkillFault：统一错误格式
├── configs/
│   ├── tools.yaml            #   工具注册表（5个工具）
│   └── skill_limits.yaml     #   资源限制配置
└── data/
    ├── messages/             #   tool_calls 测试数据
    ├── b3_eval/              #   进阶验收测试用例
    └── docs/                 #   测试用文件
```

### 3.2 接口边界

| 类型 | 来源 / 去向 | 数据格式 | 说明 |
|---|---|---|---|
| 输入 | B1 调用 | `tools_config` (yaml路径) + `toolset` (字符串) | 生成 tools_schema |
| 输入 | B1 转发 B4 的 tool_calls | `{id, name, args}` 或 `{id, function: {name, arguments}}` | 执行工具调用 |
| 输出 | 返回给 B1 | `tools_schema` (JSON 数组，OpenAI Function Calling 格式) | LLM 工具绑定 |
| 输出 | 返回给 B1 | `ToolMessage` = `{role, tool_call_id, name, content, status}` | 工具执行结果 |
| 输出 | 保存到文件 | `tools_schema.json`, `tool_messages.json`, `tool_call_log.jsonl` | 日志与调试 |

---

## 4. 基础要求实现与演示

### 4.1 基础功能说明

基础功能实现了 B3 模块的核心能力，对应课件中的 7 项验收标准：

1. ✅ 读取 tools.yaml 并生成完整 tools_schema（5个工具）
2. ✅ 正确执行合法 tool_call，调用 B2 Skill
3. ✅ 拒绝不存在的工具名，返回明确错误
4. ✅ 校验参数完整性，缺少参数时给出具体提示
5. ✅ 捕获 Skill 执行异常，系统不崩溃
6. ✅ 保存完整调用日志（tools_schema.json / tool_messages.json / tool_call_log.jsonl）
7. ✅ 支持独立命令行测试（--export_schema 和 --execute 两种模式）

### 4.2 基础功能实现路径

| 文件 / 函数 | 作用 |
|---|---|
| `b3_tool_layer.py` / `_load_tools_config()` | 读取并解析 tools.yaml |
| `b3_tool_layer.py` / `_resolve_toolset()` | 解析 toolset，获取工具名列表 |
| `b3_tool_layer.py` / `_load_callable()` | 动态导入 B2 函数（importlib） |
| `b3_tool_layer.py` / `_tool_schema()` | 生成单个工具的 OpenAI 标准 schema |
| `b3_tool_layer.py` / `get_tools_schema()` | 遍历所有工具，生成完整 schema |
| `b3_tool_layer.py` / `_validate_args()` | 三层参数校验（必填/未知/类型） |
| `b3_tool_layer.py` / `execute_tool_calls()` | 主流程：校验→执行→返回 |
| `b3_tool_layer.py` / `_result_from_exception()` | 异常封装为统一格式 |

**执行流程**：
```text
输入 tool_call → 白名单校验 → 动态加载 B2 函数（importlib）
→ 生成参数 schema → 三层参数校验 → 自动注入上下文参数
→ invoke_callable() 执行 → 构造 ToolMessage → 记录日志
```

**关键代码**：
```python
def _load_callable(definition):
    """动态加载 B2 函数"""
    module = importlib.import_module(definition.get("module"))
    return getattr(module, definition.get("function"))
```

```python
def _validate_args(args, parameter_schema):
    # 第一层：必填检查
    missing = [n for n in required if n not in args]
    # 第二层：未知参数检查
    unknown = sorted(set(args) - set(properties))
    # 第三层：类型/枚举/范围检查
    for name, value in args.items():
        if not _schema_accepts(properties[name], value):
            raise SkillFault(...)
```

### 4.3 基础功能输入格式与样例

| 字段 | 类型 | 是否必需 | 说明 |
|---|---|---|---|
| `--tools_config` | yaml 路径 | 是 | tools.yaml 配置文件 |
| `--toolset` | 字符串 | 否 | 工具集名，默认 basic_tools |
| `--tool_calls` | JSON 文件路径 | `--execute` 时需要 | tool_calls 测试数据 |
| `--outdir` | 路径 | 是 | 输出目录 |

**样例输入**：

| 样例文件 | 用途 |
|---|---|
| `data/messages/b3_tool_call_format_converter_valid.json` | 正常 tool_call 演示 |
| `data/messages/b3_tool_call_unknown_tool.json` | 错误处理：不存在的工具 |
| `data/messages/b3_tool_call_missing_required.json` | 错误处理：参数缺失 |
| `data/messages/ai_message_with_tool_calls.json` | 读文件演示 |

### 4.4 基础功能演示命令

```bash
cd b3

# 演示1：生成 tools_schema
python b3_tool_layer.py \
    --tools_config configs/tools.yaml \
    --toolset basic_tools \
    --export_schema \
    --outdir ../outputs

# 演示2：执行正常 tool_call（格式转换）
python b3_tool_layer.py \
    --tools_config configs/tools.yaml \
    --tool_calls data/messages/b3_tool_call_format_converter_valid.json \
    --execute \
    --outdir ../outputs

# 演示3：错误处理（不存在的工具）
python b3_tool_layer.py \
    --tools_config configs/tools.yaml \
    --tool_calls data/messages/b3_tool_call_unknown_tool.json \
    --execute \
    --outdir ../outputs

# 演示4：错误处理（参数缺失）
python b3_tool_layer.py \
    --tools_config configs/tools.yaml \
    --tool_calls data/messages/b3_tool_call_missing_required.json \
    --execute \
    --outdir ../outputs
```

运行后应观察：
- ✅ 终端打印输出文件路径
- ✅ `tools_schema.json` 包含 5 个工具的完整 schema
- ✅ `tool_messages.json` 显示 `status: success`
- ✅ 错误处理时 status 为 error，程序不崩溃

### 4.5 基础功能输出格式

| 输出文件 | 格式 | 说明 |
|---|---|---|
| `tools_schema.json` | JSON 数组 | OpenAI Function Calling 格式 |
| `tool_messages.json` | JSON 数组 | `{role, tool_call_id, name, content, status}` |
| `tool_call_log.jsonl` | JSON Lines | 每行一条调用日志（含时间戳） |

### 4.6 基础功能结果截图

```text
[插入 tools_schema.json 截图]
[插入 tool_messages.json 正常执行截图]
[插入 tool_messages.json 错误处理截图]
```

---

## 5. 进阶要求实现与演示

### 5.1 选择的进阶要求

| 进阶要求 | 是否完成 | 对应文件 / 函数 | 简要说明 |
|---|---|---|---|
| 自动从 Python 函数注解生成 schema | ✅ 完成 | `b3_tool_layer.py` / `_function_parameter_schema()` | 用 inspect 读取函数签名，自动推导参数类型 |
| tool_call 去重缓存与统计 | ✅ 完成 | `b3_advanced.py` / `execute_with_retry_cache_stats()` | success_only 缓存策略 + 统计报告 |
| Schema 描述对比 | ✅ 完成 | `b3_advanced.py` / `compare_schema_descriptions()` | 用真实 Qwen3.5 对比两种描述方式的准确率 |

### 5.2 进阶功能 1：自动从 Python 函数注解生成 schema

#### 功能说明

不依赖 YAML 的 parameters 手动配置，直接从 Python 函数注解自动推导参数类型。加新函数时只需要写注解，不需要改 YAML。

#### 实现路径

| 文件 / 函数 | 作用 |
|---|---|
| `inspect.signature()` | 读取函数签名，获取参数名和默认值 |
| `get_type_hints()` | 读取类型注解（str, int, list[str] 等） |
| `get_origin()` / `get_args()` | 解析泛型类型（list[str] → list + str） |
| `_annotation_schema()` | 递归将 Python 类型转为 JSON Schema |

```text
def calculator(expression: str) -> dict:
    ↑ inspect.signature() 读签名
    ↑ get_type_hints() 读注解
    → expression: str → {"type": "string"}, required
```

#### 演示命令

```bash
cd b3
python b3_tool_layer.py \
    --tools_config configs/tools.yaml \
    --toolset basic_tools \
    --export_auto_schema \
    --outdir ../outputs/auto
```

#### 输出格式

| 输出文件 | 格式 | 说明 |
|---|---|---|
| `b3_auto_schema_from_python.json` | JSON | 从注解生成的完整 schema |

### 5.3 进阶功能 2：tool_call 去重缓存与统计

#### 功能说明

对 calculator 等确定性工具启用缓存，相同参数第二次调用时直接返回缓存结果，避免重复计算。同时输出调用统计报告。

#### 实现路径

| 文件 / 函数 | 作用 |
|---|---|
| `b3_advanced.py` / `_cache_key()` | 基于 config SHA256 + name + args 生成缓存 key |
| `b3_advanced.py` / `_is_cacheable()` | 检查工具是否可缓存（`cacheable: true`） |
| `b3_advanced.py` / `execute_with_retry_cache_stats()` | 主流程：重试→缓存→统计 |

```text
第1次调用 calculator(23*17+9) → 缓存 miss → 执行 → 写入缓存
第2次相同调用 → 缓存 hit → 直接返回（0ms）
```

#### 输出格式

| 输出文件 | 格式 | 说明 |
|---|---|---|
| `b3_tool_call_stats.json` | JSON | success_rate, cache_hit_count, p50/p95 延迟等 |

### 5.4 进阶功能 3：Schema 描述对比

#### 功能说明

用真实 Qwen3.5-4B 模型测试两种 schema 描述方式对工具选择准确率的影响，验证详细描述是否有助于 LLM 正确选工具。

#### 实现路径

| 文件 / 函数 | 作用 |
|---|---|
| `b3_advanced.py` / `_description_variants()` | 生成完整描述和弱化描述两种变体 |
| `b3_advanced.py` / `compare_schema_descriptions()` | 用真实模型测试准确率 |

#### 验收结果

| 变体 | 准确率 | 平均耗时 |
|---|---|---|
| full_description（完整描述） | 100% | 2.75s |
| name_only（仅名称描述） | 100% | 0.98s |

### 5.5 一键进阶验收

```bash
cd b3
# 需加载 Qwen3.5-4B 模型
AGENT_HOOK_ARTIFACT_DIR=../outputs/B3_acceptance/model_calls \
python b3_acceptance.py --outdir ../outputs/B3_acceptance

cat ../outputs/B3_acceptance/b3_acceptance_summary.json
```

验收结果：
```json
{
  "status": "success",
  "checks": {
    "python_auto_schema": true,
    "success_only_cache": true,
    "real_model_description_comparison": true
  }
}
```

---

## 6. 与团队系统的集成说明

**集成方式**：B3 通过函数调用方式接入整体系统。

| 交互对象 | 方式 | 说明 |
|---|---|---|
| **B1（Agent运行时）** | 函数调用 | B1 调用 `get_tools_schema()` 获取 schema 传给 B4；B1 将 B4 的 tool_calls 转发给 `execute_tool_calls()` 执行 |
| **B2（Skill工具函数）** | 函数调用（动态导入） | B3 根据工具名用 `importlib.import_module()` 动态加载 B2 函数并调用 |
| **B4（LLM决策模块）** | 数据传递（经 B1 中转） | B3 的 tools_schema 经 B1 转发给 B4；B4 的 tool_calls 经 B1 转发给 B3 |
| **文件系统** | 文件 I/O | 读取 tools.yaml，保存 tools_schema.json / tool_messages.json / tool_call_log.jsonl |

**联调问题**：B3 和 B4 之间 tool_calls 数据格式不一致（OpenAI 格式 `{id, function: {name, arguments}}` vs 简化格式 `{id, name, args}`），通过实现 `normalize_tool_call()` 统一处理解决。

---

## 7. 已知问题与后续改进

| 问题 | 当前原因 | 后续改进 |
|---|---|---|
| 缓存测试第二次运行会失败 | 缓存文件持久化，第二次运行时两次调用都命中缓存 | 验收脚本应在测试前清空缓存 |
| Schema 描述对比两项准确率均为 100% | 当前 4 个测试用例较简单 | 增加更多复杂用例以区分两种描述的效果 |
| 仅支持 Python 函数注解推导 | 未支持动态类型或无注解的函数 | 对无注解函数回退到 YAML configured 模式 |
