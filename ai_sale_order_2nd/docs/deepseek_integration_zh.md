# Odoo 19 AI 与 DeepSeek 接入开发说明

**编制：Suto｜版本：1.3｜日期：2026-11-16**

本文是《Odoo 19 AI 功能开发与说明文档》的 DeepSeek 接入专题，依据当前工作区源码编写。面向成本敏感、倾向使用 DeepSeek 的客户，介绍时应把“模型接入”和“购物业务工具”一起作为完整方案说明；交付时也必须同时包含对应代码、配置和验证。

**当前方案是：Odoo 19 企业版 AI 框架 + 独立 `ai_deepseek` 模型适配 + 可选 `ai_sale_order_2nd` 购物业务模块。** 原有 `enterprise-19/ai/utils/llm_api_service.py` 和 `llm_providers.py` 中的 DeepSeek 修改已还原到当前 Git 基准；新模块通过继承提供功能，不改全局 Provider 列表，也不做 monkey patch。DeepSeek 属于本项目二开能力，文中代码与 JSON 为说明性节选或教学示例，不含真实密钥。

`ai_deepseek` 的 `19.0.1.1.0` 版本改为通过官方 `/models` 自动发现型号，保存到数据库缓存。模型下拉框不再固定登记 Chat / Reasoner；本专题中的旧 `deepseek-chat` 业务验证属于历史记录，不能用于推导新型号已验收。

## 1. 客户会议中应该怎样介绍

可以使用以下表述：

> 本方案使用 Odoo 的 AI 智能体和业务工具机制，并接入 DeepSeek 作为当前购物助手的语言模型。DeepSeek 负责理解客户商品、规格和数量的表达；Odoo 负责查真实目录、校验并加入购物车。对于成本敏感的客户，我们把 DeepSeek 作为优先评估选项，并通过实际商品场景比较成功率、耗时和每次成功加购的模型成本。

客户通常关心“能否用 DeepSeek”“为什么能用”“是否需要重新开发全部功能”和“实际费用多少”。可以分四点回答：

1. **能用的依据**：当前项目已经存在 DeepSeek API 适配，`deepseek-chat` 在实际模型和工具流程中验证过网站商品查询与加购。
2. **接入方式**：通过 HTTPS 调用 DeepSeek 的 Chat Completions 接口，转换消息、工具定义和工具结果；使用客户授权的 API 凭据。
3. **业务复用**：商品查询、规格消歧、数量校验和购物车更新仍由 Odoo 工具执行，不需要针对 DeepSeek 再写一套购物业务逻辑。
4. **费用判断**：按部署时有效的供应商定价和真实调用账单测量。即使所选模型的每百万 token 单价较低，仍需结合多轮调用、重试、上下文及成功率判断整体成本。

会议上的“DeepSeek 接入”不是单独增加一个 Key 参数。Key 只解决请求鉴权，模型发现、消息格式、工具请求解析和结果回传都需要适配代码。

## 2. 整体结构：模型适配与业务工具分工

```text
客户在 Odoo 网站表达购买需求
    ↓
Odoo ai.agent：模型、角色、Topics、最近对话
    ↓
本项目 DeepSeek 适配
    ├─ 将消息与工具 Schema 转成 Chat Completions 请求
    ├─ 读取服务端凭据，发送至 DeepSeek API
    └─ 将响应中的 tool_calls 转回 Odoo 统一工具调用
    ↓
Odoo 统一工具循环
    ↓
Suto 业务工具：查询真实商品 → 校验 → 加入当前购物车
    ↓
工具结果转成 role=tool 消息，交回 DeepSeek
    ↓
模型按中文提示组织回复，Odoo 发布到聊天频道
    ↓
客户进入购物车核对并按标准网站流程结账
```

| 层次 | 代码或配置位置 | 当前职责 |
| --- | --- | --- |
| 模型扩展 | `ai_deepseek/models/ai_agent.py` | 从数据库目录追加模型选项和 Provider 映射，仅 DeepSeek 使用独立服务 |
| 模型发现 | `ai_deepseek/services/model_catalog.py` | 同步 `/models`、保留成功缓存、已用旧模型和同步状态 |
| API 适配 | `ai_deepseek/services/deepseek_api_service.py` | Endpoint、凭据、消息/工具转换、响应解析、结果回传 |
| Agent 基础 | `enterprise-19/ai/models/ai_agent.py` | 原生角色、Topic、上下文、历史和消息发布 |
| 设置入口 | `ai_deepseek/models/res_config_settings.py` 与设置视图 | 管理员设置 DeepSeek Key，复用既有系统参数 |
| 能力约束 | `ai_deepseek/models/ai_agent.py` 与 `ai_agent_source.py` | 禁止 DeepSeek Agent 关联本版不支持的 Sources |
| 工具框架 | `enterprise-19/ai/models/ir_actions_server.py` | 参数校验、执行固定动作、错误反馈 |
| 业务实现 | `ai_sale_order_2nd/models/ai_agent.py` | 查找真实网站商品、整批预校验、购物车更新与失败回滚 |
| 工具与流程配置 | `ai_sale_order_2nd/data/ai_sale_order_tool_data.xml` | 商品搜索/加购工具 Schema、描述和 Topic 指令 |
| 部署参数 | 系统参数或进程环境 | API 凭据、Agent 模型选择、网站入口及商品范围 |

`ai_deepseek` 只依赖 `ai_app`，与 `ai_sale_order_2nd` 互不依赖；它可以独立支持其他 Agent 工具。购物方案需要同时部署这两个模块及原生网站集成、商城依赖。功能通过 Odoo 数据库注册表继承生效，同一进程中的其他数据库不安装该模块，就不会增加 DeepSeek Agent 选项。

```text
ai_deepseek/
├── __manifest__.py                 # 依赖 ai_app
├── hooks.py                        # 卸载时回退模型，保留 Agent 与 Key
├── models/
│   ├── ai_agent.py                 # 模型选择、生成路径、Sources 校验
│   ├── ai_agent_source.py          # 覆盖资料侧关联入口
│   └── res_config_settings.py      # 管理员 Key 设置
├── services/
│   ├── deepseek_api_service.py     # /models 与 Chat Completions 服务
│   └── model_catalog.py            # 每数据库目录缓存与旧模型兼容
├── data/ir_cron.xml               # 每日刷新模型目录
├── migrations/19.0.1.1.0/         # 升级后同步目录
├── views/
│   └── res_config_settings_views.xml
└── tests/                         # 适配回归
```

## 3. 六个代码环节，说明适配到底做了什么

### 3.1 环节一：发现模型并注册 Provider 路由

来源：[独立 Agent 扩展](../../ai_deepseek/models/ai_agent.py)、[模型目录服务](../../ai_deepseek/services/model_catalog.py) 与 [DeepSeek 服务](../../ai_deepseek/services/deepseek_api_service.py)。核心 `llm_providers.py` 已恢复，只保留原生 OpenAI、Google。新模块调用官方接口发现实际型号，关键请求为：

```python
payload = self._request(
    "get", "/models", self._get_base_headers(), None, timeout=10,
)
```

响应中的 `data[].id` 是实际发送给 API 的模型标识，`name` 是显示名；没有 `name` 时使用 ID。完整响应先校验再替换缓存，拒绝空/无效目录、重复 ID 和与原生模型冲突的 ID；显式不支持文本输入或输出的型号会被过滤。能力字段缺省的型号仍可列出，但必须进行文本与工具业务验收。

`DeepSeekModelCatalog` 将目录保存在当前数据库的 `ai.deepseek_models`，包含当前模型、历史已知 ID、最后成功/尝试时间和状态。Agent 扩展在 `super()._get_llm_model_selection()` 结果后追加本地目录；`_get_provider()` 对动态目录和兼容旧 ID 返回 `deepseek`，其他模型仍调用 `super()`。打开下拉框、读取字段和正常聊天不请求 `/models`，避免加载界面依赖外部网络。

首次安装与升级到本版时尝试同步；保存变化后的 Key 或尚无成功目录时同步；定时任务每天同步。管理员也可点击设置页的 **Save Key and Refresh Models**，它会先保存当前输入框的 Key，再获取目录。缺 Key、网络失败或坏响应时保留上次成功目录并提示，不让暂时故障清空正在使用的选项。

API 已不返回的型号如果仍被现有或归档 Agent 使用，会标注 `not in current catalog` 并保留，以便查看、编辑和手动迁移。模块不会自动替换 Agent 的模型；保留旧 ID 不代表供应商仍接受它。新库首次同步前没有固定 Chat / Reasoner 选项。

Odoo 19 的核心 `llm_model` Selection 使用函数对象，不能直接以 `selection_add` 扩展。独立模块将 Selection 重绑为可继承的方法名：

```python
llm_model = fields.Selection(selection="_get_llm_model_selection")
```

核心服务类同样没有被替换；只有选择 DeepSeek 的 Agent 才实例化新服务。

截至 2026-11-16，[官方模型文档](https://api-docs.deepseek.com/quick_start/pricing/) 列出 `deepseek-flash`、`deepseek-v4-pro`；实际下拉框以当前 Key 调用 [`GET /models`](https://api-docs.deepseek.com/api/list-models/) 的结果为准。型号被发现只表示供应商列出它，不能代表购物流程已验收。历史真实购物验证使用的是旧 `deepseek-chat` 标识。

新模块不再登记此前未经验证的 `deepseek-embed`，也不尝试通过它调用 `/embeddings`。本版明确只支持文本与工具，拒绝 DeepSeek Agent 关联 Sources。

### 3.2 环节二：选择 Endpoint，读取 API Key

来源：[deepseek_api_service.py](../../ai_deepseek/services/deepseek_api_service.py) 的 `DeepSeekLLMApiService.__init__()`、`_get_api_token()`。

现有 Endpoint 分支节选：

```python
self.provider = "deepseek"
self.base_url = "https://api.deepseek.com/v1"
```

凭据读取节选：

```python
token = self.env["ir.config_parameter"].sudo().get_param("ai.deepseek_key")
token = token or os.getenv("ODOO_AI_DEEPSEEK_TOKEN")
```

读取顺序是：优先读取当前数据库 `ir.config_parameter` 的非空 `ai.deepseek_key`，否则读取运行 Odoo 进程的 `ODOO_AI_DEEPSEEK_TOKEN` 环境变量。两者都没有时，抛出缺少 API Key 的错误。

请求头由服务端生成，格式为 `Authorization: Bearer <服务端读取的凭据>`。真实 Key 不应放在模块 XML、版本库、前端 JavaScript、会议截图或发给客户的示例请求中。

需要解释三个部署细节：

- 数据库参数优先，因此修改环境变量后，数据库里仍有非空旧值时不会覆盖旧值。
- 环境变量属于进程启动环境，修改系统环境后，已经运行的服务未必能看到新值，应按服务部署方式重新加载。
- 安装 `ai_deepseek` 后，AI 设置页新增 DeepSeek API Key 输入项，密码显示，字段限制系统管理员读取；保存到同一个 `ai.deepseek_key`。

已有数据库参数作为运行配置保留，新模块直接读取，不将客户 Key 写进安装 XML，也不要求迁移时重新复制。新客户在其目标环境单独配置自己的凭据。

### 3.3 环节三：把 Odoo 消息和工具转成 DeepSeek 请求

来源：独立服务的 `_request_llm()`。

方法首先构造 `messages`，把系统指令转换为 `role=system`，保留已支持的 `system/user/assistant/tool` 历史，再加入用户提示。

本版为普通动态模型显式发送 `thinking={"type": "disabled"}`。原生 Odoo 仅重建 `role/content` 历史，没有完整保存跨用户轮的 `reasoning_content`；禁用思考模式使新模型沿用当前文本客服和工具链路。Flash / Pro 是型号，思考是独立运行参数，不能将它们直接当作旧 Chat / Reasoner 的一一替代。旧 `deepseek-reasoner` Agent 继续使用原协议：工具轮保留推理字段且不发送 `temperature`；这不表示已经通过同等的真实多轮业务验收。

工具定义转换节选：

```python
if tools:
    body["tools"] = [{
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_description,
            "parameters": tool_parameter_schema,
        },
    } for tool_name, (tool_description, __, __, tool_parameter_schema)
      in tools.items()]
    body["tool_choice"] = "auto"
```

这里把 Odoo 的工具名称、描述、Schema 转换为 Chat Completions 的 function tools。Python 回调保留在 Odoo 服务端，不发送给模型。

`tool_choice="auto"` 表示模型可以决定回答文字或请求工具；它不保证一定调用加购工具。因此 Topic 需要清楚说明先查目录、保留数量、歧义时追问等流程，并通过真实对话验证模型行为。

实际请求通过 `_request("post", "/chat/completions", ...)` 发送到当前 DeepSeek base URL。当前代码没有在这条方法中开启流式返回；网站聊天仍按现有请求与消息发布机制显示回答。

### 3.4 环节四：解析 `choices.message.tool_calls`

模型响应可能包括文字 `content`，也可能包括 `tool_calls`。适配方法验证 `choices` 为非空列表、第一项及其 `message` 为对象后，读取第一条消息。以下为通过结构校验后的取值示意：

```python
message = choices[0]["message"]
```

如果模型返回工具调用，代码保留原 assistant 消息，包括存在时的 `reasoning_content`，再逐项取 `function.name` 和 `function.arguments`。后者是 JSON 字符串，需要用 `json.loads()` 解析；参数必须是对象，不能是列表、标量或任意可执行代码。

关键节选：

```python
tool_name = function.get("name")
call_id = tool_call.get("id")
if tool_name not in (tools or {}):
    raise UserError("DeepSeek requested a tool that is not available.")
if not isinstance(call_id, str) or not call_id:
    raise UserError("DeepSeek returned an invalid tool call identifier.")
arguments = json.loads(function.get("arguments") or "{}")
if not isinstance(arguments, dict):
    raise UserError("DeepSeek tool arguments must be a JSON object.")
calls.append((tool_name, call_id, arguments))
```

真实实现还会捕获非法 JSON 并转成 `UserError`。同一模型响应中的工具调用必须整批通过校验，才交给核心；后续项非法时，前面的工具也不会先执行。无效响应结构、缺少调用 ID 或 `finish_reason="length"` 同样返回明确错误。正常请求转换成 Odoo 统一 `(tool_name, call_id, arguments)` 结构。

这一步只完成“协议转译”。商品是否存在、数量是否合法、网站是否允许访问等，还需要工具框架和具体业务方法检查。

### 3.5 环节五：执行统一工具循环，并以 `role=tool` 回填

来源：恢复后的核心 LLMApiService（`enterprise-19/ai/utils/llm_api_service.py`） 的 `_request_llm_silent()`，及独立服务的 `_build_tool_call_response()`。新服务继承核心请求、日志、工具循环和 HTTP 错误处理，只覆盖 DeepSeek 协议所需方法。

统一循环做以下工作：请求模型，取得工具调用；检查工具名；调用服务端固定工具回调；把结果作为新的输入；再次请求模型。模型可以进一步搜索、执行加购、追问或结束回答。

DeepSeek 工具结果格式节选：

```python
return {
    "role": "tool",
    "tool_call_id": tool_call_id,
    "content": str(return_value),
}
```

`tool_call_id` 对应模型刚才发出的调用 ID，用于把结果和请求关联。当前 `content` 使用 `str(return_value)`：搜索工具返回 Python 字典时会成为字典的字符串表达；它不保证是 `json.dumps()` 生成的 JSON。模型可以读取该文本，但开发其他消费者时不能假定其正文是严格 JSON。

当前循环默认最多连续 20 次模型请求，每轮最多执行 20 个工具，分别由 `ai.max_successive_calls`、`ai.max_tool_calls_per_call` 配置。它们是上限，不代表每条聊天固定请求 20 次，也不是针对 DeepSeek 的业务成功保证。

工具执行复用 `ir.actions.server` 的 `_get_ai_tools()` 与 `_ai_tool_run()`。框架会校验参数、执行预先配置的动作；大多数工具异常会变成结果文本交回模型恢复。**框架捕获异常不等于自动回滚该工具已经执行的全部数据库写入。** Suto 购物车方法已有自己的整批预校验、savepoint 和 session 恢复逻辑，换成 DeepSeek 时这些保护仍然有效。

### 3.6 环节六：Agent 选择 DeepSeek，购物工具保持复用

来源：[独立 Agent 扩展](../../ai_deepseek/models/ai_agent.py) 的 `_generate_response()`。以下为路由逻辑节选：

```python
if self.llm_model not in DeepSeekModelCatalog(self.env).get_model_ids():
    return super()._generate_response(prompt, chat_history, extra_system_context)
self._check_deepseek_sources()
return DeepSeekLLMApiService(self.env).request_llm(
    self.llm_model,
    self._build_system_context(extra_system_context=extra_system_context),
    [],
    inputs=(chat_history or []) + [{'role': 'user', 'content': prompt}],
    tools=self.topic_ids.tool_ids._get_ai_tools(),
    temperature=TEMPERATURE_MAP[self.response_style],
)
```

当 Agent 的 `llm_model` 属于已发现的 DeepSeek 目录或兼容的旧型号，生成调用进入独立服务，实际模型 ID 原样发送；Topic 提供的查询商品和加购工具保持原样。当前问题只加到 `inputs` 一次，`user_prompts` 为空，避免两种输入通道重复发送当前问题。

核心在 Provider 切换时会询问 embedding 模型。无 Sources 的 DeepSeek Agent 返回 `False`，允许正常切换；已有 Sources 则拒绝切换。Agent 字段约束和 `ai.agent.source` 关联约束共同覆盖直接创建资料、重新关联、上下文默认 Agent 及内联资料入口，防止在无 embedding 适配时进入资料处理任务。

当前业务方法位于 [Suto ai_agent.py](../models/ai_agent.py)：网站加购约第 59 行，网站商品搜索约第 142 行。它们调用 Odoo ORM 与标准商城方法，不关心模型供应商是谁。更换模型主要影响理解、工具选择和参数生成，因此仍需重新验收模型表现；业务权限和数据写入控制继续由 Odoo 执行。

## 4. 一次完整请求与响应的教学示例

以下示例演示“帮我下单一个黑色抽屉”，保留此前 `deepseek-chat` 的协议示例以解释请求与响应。新部署应使用同步目录中选定的真实 ID，并按本版实现发送非思考参数。为了便于阅读，系统提示经过缩短，只放入本次查询需要的一个工具。真实 Agent 会发送其实际 Topic 工具集合与更多上下文。示例不包含真实密钥，调用 ID、商品信息与响应字段用于说明协议。

### 4.1 发起商品查询前的请求

```text
POST https://api.deepseek.com/v1/chat/completions
Content-Type: application/json
Authorization: Bearer <从服务端安全读取的凭据>
```

请求 JSON：

```json
{
  "model": "deepseek-chat",
  "messages": [
    {
      "role": "system",
      "content": "你是网站购物助手。先查询真实目录，保留用户已经给出的数量，规格不唯一时追问。只根据工具结果说明执行情况。"
    },
    {
      "role": "user",
      "content": "帮我下单一个黑色抽屉"
    }
  ],
  "temperature": 0.2,
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "ir_actions_server_ai_search_website_products",
        "description": "Search the current website's published sellable catalog and return real product references and names.",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {
              "type": "string",
              "description": "Product name, reference, barcode, or attribute keywords."
            }
          },
          "required": ["query"]
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

### 4.2 模型返回搜索工具请求

```json
{
  "id": "chatcmpl-example-001",
  "object": "chat.completion",
  "model": "deepseek-chat",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call-search-001",
            "type": "function",
            "function": {
              "name": "ir_actions_server_ai_search_website_products",
              "arguments": "{\"query\":\"黑色抽屉\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

模型在这里仅提出工具请求，尚未查询 Odoo，也没有添加商品。适配层解析 JSON 参数后，由 Odoo 执行查询工具。

### 4.3 Odoo 返回搜索结果，继续请求模型

Odoo 将上一步的 assistant 工具请求及以下工具结果加入后续 `messages`。这里展示的是新增的完整工具消息对象，后续请求仍需带回必要的原始系统/用户消息、assistant 工具请求、可用工具定义。

```json
{
  "role": "tool",
  "tool_call_id": "call-search-001",
  "content": "{'products': [{'product_id': 33, 'name': '[FURN_8900] 黑色抽屉', 'reference': 'FURN_8900', 'catalog_name': 'Drawer Black', 'attributes': []}], 'has_more': False}"
}
```

正文中单引号和 `False` 对应当前代码 `str(dict)` 的表达方式；外层消息对象仍是有效 JSON。真实商品 ID 和名称由目标数据库决定。

### 4.4 模型请求真实 SKU 加购

实际 Agent 同时提供加购工具时，模型可以在后续轮次返回如下请求消息。工具完整 Schema 在本模块 XML 中定义，商品数组和数量数组一一对应。

```json
{
  "role": "assistant",
  "content": null,
  "tool_calls": [
    {
      "id": "call-cart-002",
      "type": "function",
      "function": {
        "name": "ir_actions_server_ai_add_products_to_website_cart",
        "arguments": "{\"product_names\":[\"FURN_8900\"],\"quantities\":[1],\"note\":\"\"}"
      }
    }
  ]
}
```

Odoo 校验并执行成功后，返回工具消息，例如：

```json
{
  "role": "tool",
  "tool_call_id": "call-cart-002",
  "content": "Cart update results:\n- [FURN_8900] 黑色抽屉 x 1\nYou can open /shop/cart to review quantities and proceed to checkout."
}
```

模型再基于真实结果生成回复，Topic 要求使用中文，但提示词不构成输出语言的代码级保证；本次真实调用仍偶有英文过程性文字。最终业务成功证据是工具结果和当前购物车实际数据，而不只是模型输出“已完成”。标准加购是增加数量：若购物车已有一件，本轮再加一件后总量会变成两件。

## 5. 当前支持范围与尚需验证的范围

| 能力 | 当前代码和验证状态 | 对客户的准确表达 |
| --- | --- | --- |
| 动态文本模型目录 | `/models` 自动同步与本地缓存；普通型号禁用思考 | 可从实际返回的型号选择，新增型号需单独验收 |
| 旧 `deepseek-chat` 文本回答 | 拆分阶段完成过真实网站模型流程验证 | 这是历史验证，不证明新型号具有相同效果 |
| function tools | 已适配定义、响应解析、结果回填 | 可请求 Odoo 允许的查询与加购工具 |
| 中文数量与规格描述 | 已有部分真实场景验证 | 支持已验证场景，客户商品和表达需建立验收集 |
| 旧 `deepseek-reasoner` | 保留已有 Agent 的兼容识别，未完成同等业务验证 | 新库不固定增加该选项；不能由旧协议测试承诺业务效果 |
| 文件、图片、PDF 直接输入 | 当前 Chat Completions 方法遇到 `files` 会拒绝 | 不能按现有购物接入承诺已支持 |
| 独立结构化输出 `schema` | 当前方法遇到该参数会拒绝 | 与已支持的工具参数 Schema 分开理解 |
| 联网搜索 `web_grounding` | 当前方法明确拒绝 | 当前购物助手不依赖此能力 |
| embedding / RAG | 不登记 `deepseek-embed`，明确拒绝 embedding 和 Sources | 本版不支持；采用已有支持的 Provider 或另行开发检索组合 |
| 语音转写、实时音频 | 服务明确拒绝 | 不属于本版支持范围 |
| 其他 AI 入口 | 不进行全局替换 | 按入口模型选择和接口能力分别核实 |
| 所有 AI 自动化统一用 DeepSeek | 未实现这种统一切换 | Agent 模型只影响使用该 Agent 的路径 |

`ir.actions.server` 的 `state="ai"` 自动化路径当前另有 `AI_PROVIDER="openai"` 和 `AI_MODEL="gpt-4.1"` 默认值。改变网站 Agent 的 `llm_model` 不会修改这条自动化路径；对客户宣称“系统 AI 全部切到 DeepSeek”前，必须逐个核对入口。

## 6. 新客户环境要交付哪些内容

### 6.1 交付清单

| 类别 | 需要交付或配置的内容 | 为什么需要 |
| --- | --- | --- |
| Odoo 基础环境 | 匹配版本的企业版 AI、网站客服、商城及相关依赖；所需授权 | 提供框架和标准业务流程 |
| 独立适配模块 | `ai_deepseek` 的 Python、设置视图、卸载 hook 和回归测试 | 在不修改企业版核心的情况下提供 DeepSeek Agent 功能 |
| Suto 业务模块 | `ai_sale_order_2nd` 的 Python、XML 和测试 | 提供商品查询、加购和草稿报价能力 |
| 模型凭据 | 客户授权的 API Key，通过约定的服务端配置方式保存 | Key 不属于代码或模块安装数据 |
| Agent 配置 | 从同步目录选择目标型号，配置提示、语言和必要 Topics，并完成验收 | 让实际入口走正确模型和工具流程 |
| 网站入口 | 网站/客服频道/规则或页面 AI 区块关联 Agent | 决定客户消息是否进入该助手 |
| 商品数据 | 发布、网站、SKU、规格、翻译和可售规则 | 业务工具只能依据真实目录执行 |
| 验收与维护 | 适配回归、14 项购物工具回归、模型场景集、浏览器/session 验证 | 保证模型接入与真实业务结果一致 |

`ai_deepseek` 提供模型接入，`ai_sale_order_2nd` 提供购物工具；两者都不会自动替客户绑定网站 Agent 或写入客户密钥。软件交付应包含需要的独立模块；本文件所在资料压缩包只是文档包，不是完整安装包。

### 6.2 推荐上线顺序

1. 确认目标 Odoo 版本和依赖，把 `ai_deepseek` 放入 `addons_path`，安装该模块；购物方案同时安装 `ai_sale_order_2nd`。
2. 管理员在 AI 设置配置并保存 DeepSeek Key，或配置服务环境变量后刷新目录；确认同步成功，且 Agent 无 Sources。
3. 创建或选择测试 Agent，从目录选择当前可用模型，先验证普通文本回答。
4. 关联网站购物 Topic，确认搜索和加购工具都已提供。
5. 验证只读商品搜索，再验证加购和失败回滚。
6. 按匿名/Portal 身份和商城访问策略，从实际网站入口验收同一 session 的购物车。
7. 记录真实模型费用和耗时，明确当前上线范围，再开放客户使用。

Python 适配代码修改后要让服务重新加载代码；字段、设置视图或工具/Topic XML 变更需要升级相应模块。系统参数和 Agent 是运行配置，目标环境需单独核对。本次独立拆分已完成，不需要把 DeepSeek 分支重新写入企业版核心。

卸载 `ai_deepseek` 时，hook 将包括归档记录在内的 DeepSeek Agent 模型切回 `gpt-4o`，保留 Agent、Topic、消息历史和客户 Key。卸载不是供应商账户注销，也不抹除凭据；回退后的 Agent 需要有效 OpenAI Key 才能继续调用模型。

## 7. 客户选择模型时如何比较成本

### 7.1 把 DeepSeek 作为优先评估项

当客户看重 API 成本时，可以从当前同步的 DeepSeek 文本型号中选择候选，并使用同一批客户真实商品表达和相同业务工具比较。应一起看：正确加购比例、必要追问是否合理、错误恢复、响应耗时，以及每次成功任务的模型成本。旧 Chat 标识的验证不能代替当前 Flash / Pro 等型号的实测。

本文不填未经核实的实时模型报价，也不承诺固定节省百分比。供应商价格、缓存规则、模型名称和计费单位可能调整，报价时应记录生效日期、币种及当期官方计费规则。

### 7.2 一条聊天不等于一次模型调用

“理解需求 → 查询商品 → 判断结果 → 加入购物车 → 组织回复”可能经过多轮 API 请求。后续请求通常再次携带必要上下文、工具定义和工具结果，因此累计输入量会增加。没有找到商品而反复搜索、成功后错误重试，也会影响成本和耗时。

若供应商分别计费缓存命中输入、未命中输入和输出，可按实际账单互斥分类计算：

```text
一轮模型费用 =
    未命中输入 token × 对应输入单价
  + 缓存命中输入 token × 对应缓存单价
  + 输出 token × 对应输出单价

一次任务模型费用 = 该任务全部模型请求费用之和
每次成功加购平均模型费用 = 统计期内相关模型总费用 ÷ 成功加购任务数
```

单价若按百万 token 报价，应除以 1,000,000 后换算；缓存命中与未命中输入是互斥计费项，不能先计全部输入，再把缓存输入重复加一次。若所选模型存在其他计费分类，按供应商正式账单补充，不应套用不适用的公式。

当前 Odoo AI 日志有字符数推算 token 的粗估逻辑，可辅助定位，但不能替代供应商正式用量。评估还需单列 Odoo 许可部署、定制实施、运维及可选知识向量服务费用。

### 7.3 降低无效消耗的实施方式

- 给网站助手关联必要 Topic，减少无关指令和工具定义。
- 商品检索返回有限的真实候选；有歧义时问缺少属性，避免盲目反复查询。
- 使用真实 SKU 或完整目录名称执行，降低错误匹配和重复尝试。
- 监控 API 次数、工具耗时、失败类型与供应商费用，按场景优化。
- 提前明确单次任务的轮数上限与错误处理；上限不是可用性替代品。

这些做法优化整体方案的有效执行成本，最终效果仍需客户数据实测。

## 8. 验收矩阵

| 层次 | 建议场景 | 验收事实 |
| --- | --- | --- |
| 适配配置 | 同步目录中的目标型号 + 正确 Key | 正常文本回答，实际请求进入预期 Provider |
| 模型同步 | 首次配置、每日刷新、网络失败、供应商移除型号 | 当前列表来自 API；失败保留目录，旧 Agent 不被自动切换 |
| 凭据优先级 | 数据库参数、环境变量各自配置 | 读取顺序符合约定；不在日志或前端暴露 Key |
| 只读工具 | 查询真实 SKU、中文商品、英文规格 | 工具参数正确；返回实际当前网站目录；不新增购物车行 |
| 唯一商品 | “帮我下单一个黑色抽屉” | 查询并加购唯一真实商品，数量 1 |
| 规格歧义 | 白色可定制化桌子 | 列真实选项，只追问缺失属性，不任意选变体 |
| 批量与混合语言 | 两个桌子 SKU 加 Velvet 沙发 | 最终三个真实变体及数量正确 |
| 失败批次 | 最后一个商品无效、中途业务校验失败 | 一次失败批次整体回滚并恢复相关 session 状态 |
| 成功重复 | 相同成功加购再次调用 | 识别当前增量行为；如要求防重复，先开发持久化幂等 |
| 身份与会话 | Portal、匿名、仅登录商城、换浏览器 | 符合商城访问策略和实际购物车归属 |
| 成本与耗时 | 同一验收集多次运行 | 比较成功率、轮数、实际账单和响应分布 |
| 能力拒绝 | 文件、独立 schema、联网、embedding、Sources、语音 | 在不支持的路径返回明确错误，不进入未验证的接口 |
| 其他模型/入口 | Reasoner、自动化 AI Action | 逐项单独验收，不能由 Chat 购物成功推导 |
| 模块隔离与卸载 | 核心 Provider、不安装扩展的数据库、卸载回退 | 核心不被全局修改；卸载保留 Agent、Topic 和 Key |

本次在核心源码还原、独立适配安装后，19 项 DeepSeek 适配测试与 14 项网站工具回归合计 33 项全部通过。真实 DeepSeek 下单验证也重新运行，黑色抽屉和三商品混合语言场景均成功，测试写入已回滚。这些记录不能代替新客户目录、当前服务可用性及浏览器身份链路的验收。

## 9. 版本维护与交付建议

模型接入已整理为独立 `ai_deepseek`，原有企业版 `llm_api_service.py`、`llm_providers.py` 已还原。版本管理应记录核心基准、新模块版本及适配测试结果；升级 Odoo 时重点回归 Agent Selection、`_generate_response()`、核心工具循环和设置视图扩展点。独立模块降低了维护核心补丁的负担，但不代表无需检查上游 API 变化。

新模块依赖具有相应授权的 Odoo 企业版 `ai_app`；交付扩展不等于获得企业版代码的公开分发许可。DeepSeek Reasoner 仍需同等业务验收；知识检索和其他 AI 入口若要采用 DeepSeek，应作为后续独立范围设计，不能通过放开当前 Sources 校验来替代实现。

客户交付说明建议明确列出：框架版本、DeepSeek 适配版本、业务模块版本、已验收模型和场景、凭据配置方式、能力范围及维护责任。这样客户能理解为何选择 DeepSeek、它在整个方案中的作用，以及迁移到新数据库时需要哪些步骤。

面向业务的重点可以落在“自然语言便利性与实际成本”；面向技术的重点是“协议适配、可控工具、运行配置和业务验证”。两部分共同构成当前 DeepSeek 购物助手方案。
