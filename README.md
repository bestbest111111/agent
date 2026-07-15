# B3 说明生成与工具调用模块

## 📌 模块定位

B3 是 **B2（Python 工具函数）** 和 **B4（LLM 决策模块）** 之间的**桥接层**。

核心两件事：
1. **生成 tools_schema** — 把 B2 的 Python 函数翻译成 LLM 能懂的 OpenAI Function Calling 格式
2. **执行 tool_calls** — 接收 LLM 的调用指令，校验后安全地派发给 B2 执行

## 📁 目录结构

```
b3/
├── b3_tool_layer.py          # 核心：schema生成 + tool_call执行（510行）
├── b3_advanced.py            # 进阶：重试/缓存/统计/描述对比（399行）
├── b3_acceptance.py          # 验收：一键进阶功能检验（93行）
│
├── common/                   # 公共工具
│   ├── io_utils.py           #   JSON/YAML/JSONL 读写
│   ├── path_utils.py         #   路径解析与安全校验
│   ├── logging_utils.py      #   日志时间戳
│   └── schemas.py            #   ToolMessage 与 tool_call 标准化
│
├── skills/                   # B2 工具函数（B3 动态加载调用）
│   ├── calculator.py         #   安全数学计算
│   ├── file_reader.py        #   读本地 txt/md 文件
│   ├── local_file_search.py  #   BM25 文件内容搜索
│   ├── table_analyzer.py     #   CSV/TSV 分析与统计
│   ├── format_converter.py   #   Markdown/JSON 格式转换
│   └── core/                 #   B2 基础设施（invoker、context、errors）
│       ├── invoker.py        #   invoke_callable：真正执行 B2 函数
│       ├── context.py        #   make_context：创建执行上下文
│       ├── errors.py         #   SkillFault：统一错误格式
│       └── contracts.py      #   SkillContext 数据契约
│
├── configs/
│   ├── tools.yaml            #   工具注册表（5个工具配置）
│   └── skill_limits.yaml     #   资源限制配置
│
└── data/
    ├── messages/             #   tool_calls 测试数据
    │   ├── b3_tool_call_format_converter_valid.json
    │   ├── b3_tool_call_unknown_tool.json
    │   ├── b3_tool_call_missing_required.json
    │   └── ai_message_with_tool_calls.json
    ├── b3_eval/              #   进阶验收测试用例
    │   └── schema_selection_cases.json
    └── docs/
        └── agent_intro.txt   #   测试用文件
```

## ⚙️ 核心功能

### 1️⃣ 生成 tools_schema

从 `tools.yaml` 配置或 Python 函数注解生成 OpenAI Function Calling 标准格式。

```bash
python b3/b3_tool_layer.py \
    --tools_config b3/configs/tools.yaml \
    --toolset basic_tools \
    --export_schema \
    --outdir outputs/schema
```

输出示例（calculator 工具）：
```json
{
  "type": "function",
  "function": {
    "name": "calculator",
    "description": "Calculate a safe arithmetic expression.",
    "parameters": {
      "type": "object",
      "properties": {
        "expression": {"type": "string", "description": "Arithmetic expression..."}
      },
      "required": ["expression"]
    }
  }
}
```

### 2️⃣ 执行 tool_call

接收 LLM 返回的 tool_calls，进行三层安全校验后执行。

```bash
python b3/b3_tool_layer.py \
    --tools_config b3/configs/tools.yaml \
    --tool_calls b3/data/messages/b3_tool_call_format_converter_valid.json \
    --execute \
    --outdir outputs/execute
```

执行流程：
```
输入 tool_call → 白名单校验 → 动态加载 B2 函数 → 参数校验
→ 自动注入上下文 → 执行 B2 Skill → 返回 ToolMessage → 记录日志
```

### 3️⃣ 错误处理

| 场景 | 命令 | 预期结果 |
|:----|:----|:--------|
| 不存在的工具 | `--tool_calls b3_tool_call_unknown_tool.json` | 返回错误，不崩溃 |
| 参数缺失 | `--tool_calls b3_tool_call_missing_required.json` | 提示缺少参数 |

### 4️⃣ 进阶功能

```bash
# 从 Python 注解自动生成 schema
python b3/b3_tool_layer.py --tools_config b3/configs/tools.yaml \
    --toolset basic_tools --export_auto_schema --outdir outputs/auto

# 一键进阶验收（需加载 Qwen3.5-4B）
python b3/b3_acceptance.py --outdir outputs/acceptance
```

## 🏗️ 架构设计

```
用户 → B1 Runtime → B3 get_tools_schema() → tools_schema
                         │
                    B1 转发给 B4 LLM
                         │
                    LLM 返回 tool_calls
                         │
                    B3 execute_tool_calls()
                         ├─ 白名单校验
                         ├─ 动态加载 B2 函数（importlib）
                         ├─ 三层参数校验
                         ├─ 自动注入 data_root 等上下文
                         ├─ invoke_callable() 执行
                         └─ 返回 ToolMessage
                         │
                    B1 把结果给 LLM → 最终回答
```

## 🔧 技术要点

| 技术 | 用途 |
|:----|:----|
| `importlib.import_module()` | 按字符串名动态加载 B2 函数，加新工具不改代码 |
| `inspect.signature()` | 读取函数签名，自动推导参数名和默认值 |
| `get_type_hints()` | 读取类型注解（`str`、`int`、`list[str]` 等） |
| `get_origin()` / `get_args()` | 解析泛型类型，支持 `str\|int`、`Literal` 等 |
| `argparse` | CLI 命令行参数解析 |
| `SkillResult` 统一格式 | 成功/失败都用同一结构返回，不崩溃 |

## 🔒 三层安全机制

| 层级 | 校验内容 | 示例错误信息 |
|:----:|:---------|:------------|
| ① 白名单校验 | 工具名是否在 toolset 中 | `"tool is not available in basic_tools: xxx"` |
| ② 参数校验 | 必填/未知参数 | `"missing required parameters: expression"` |
| ③ 类型校验 | 类型/枚举/数值范围 | `"parameter max_chars must match integer"` |

## 📊 验收结果

使用 `b3_acceptance.py` 加载真实 Qwen3.5-4B 模型测试：

| 检查项 | 结果 | 说明 |
|:------|:----:|:----|
| `python_auto_schema` | ✅ | 自动生成 schema ≥5 个工具 |
| `success_only_cache` | ✅ | 缓存正常（第1次miss→执行，第2次hit） |
| `real_model_description_comparison` | ✅ | 描述对比通过 |
| **整体状态** | **`success`** | **全部通过** |

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install pyyaml

# 2. 生成 tools_schema
cd b3
python b3_tool_layer.py \
    --tools_config configs/tools.yaml \
    --toolset basic_tools \
    --export_schema \
    --outdir ../outputs

# 3. 执行 tool_call（读文件）
python b3_tool_layer.py \
    --tools_config configs/tools.yaml \
    --tool_calls data/messages/ai_message_with_tool_calls.json \
    --execute \
    --outdir ../outputs

# 4. 查看结果
cat ../outputs/tool_messages.json
```

## 📄 依赖

- Python 3.10+
- PyYAML >= 6.0（解析 tools.yaml）
- 其余为 Python 标准库（无需额外安装）

