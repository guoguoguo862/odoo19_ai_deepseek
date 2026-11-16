# Odoo 19 AI 功能开发与说明文档：开发技术附录

**编制：Suto｜版本：1.3｜日期：2026-11-16**

本附录面向实施顾问、开发人员和运维人员，以当前工作区的 Odoo 19 企业版源码及 `ai_sale_order_2nd` 模块为依据。它解释当前实现，也标注尚需开发或单独验收的能力。源码行号为编制时位置，后续修改可能使行号移动，应同时按方法名定位。

当前网站使用由独立 `ai_deepseek` 模块从 DeepSeek `/models` 获取的文本模型。该模块与 `ai_sale_order_2nd` 分别负责模型接入和购物业务。原有企业版 AI 适配修改已还原到当前 Git 基准；不应向客户宣传为“Odoo 19 官方默认支持所有 DeepSeek 能力”。文档不展示任何真实密钥。

版本 1.3 对应已完成的独立适配与自动模型发现，补充目录缓存、继承扩展点、管理员设置入口、Sources 限制、卸载行为和双模块交付。独立 [DeepSeek 适配实现与交付说明](deepseek_integration_zh.md) 讲解协议及完整请求响应；本附录第 8 章保留跨 Provider 的配置比较。

## 1. 先建立准确的技术模型

Odoo AI 的运行由“对话配置、模型服务、受控业务工具、Odoo 业务模型”协作完成。语言模型接收提示词、历史和工具定义，决定回复文字或请求调用某个工具；真正的数据查询与写入由 Odoo 执行预先开发的代码。

| 层次 | 主要对象 | 职责 | 与本模块的关系 |
| --- | --- | --- | --- |
| 网站入口 | Livechat、页面 AI 聊天区块 | 收集消息、创建会话、显示回复 | 复用现有入口，本模块没有自建聊天界面 |
| 消息与会话 | `discuss.channel`、`mail.message`、`mail.guest` | 保存对话，识别成员，关联 Agent | AI 工具在这条请求链中使用网站会话 |
| Agent | `ai.agent` | 模型、角色提示、风格、Topics、Sources | 本模块继承它，增加业务方法 |
| Topic | `ai.topic` | 一组任务指令及允许使用的工具 | 本模块定义后台报价和网站购物两个 Topic |
| Tool | `ir.actions.server` | 工具描述、参数 Schema、固定执行代码 | 本模块定义三个工具 |
| 模型适配 | `LLMApiService` | API 请求、工具调用解析、循环处理 | 本模块复用，不直接请求模型 |
| 可选知识库 | `ai.agent.source`、`ai.embedding`、附件、pgvector | 资料提取、分块、向量检索 | 商品加购工具直接查询商品，不依赖商品向量化 |
| 业务执行 | ORM、`website_sale`、`sale.order` | 商品权限及可售校验、购物车、报价单 | 本模块调用这些标准能力 |

需要分清三个概念：

1. **Agent 是配置对象。** 它通常对应某个用途的助手，而不是一个独立训练出来的新模型。
2. **Topic 是指令与工具集合。** 当前实现拼接一个 Agent 的全部 Topic 指令，并合并其工具；不是先选中某一个 Topic 后只加载它。
3. **Tool 是服务端预先定义的动作。** 模型提出工具名与参数，Odoo 决定实际可以执行的代码与业务边界。

框架同时还有文本辅助、AI 字段、AI 自动化动作等入口。“使用同一个 AI 基础模块”不代表每个入口都会读取同一个 Agent 配置。

## 2. 关键源码索引

本仓库模块使用可点击的相对链接；`enterprise-19/` 和 `odoo-19.0/` 是单独准备的 Odoo 企业版、社区版源码根目录示意，不包含在本仓库中。请在匹配版本的已授权源码中按文件和方法定位。

| 源码 | 编制时关键位置 | 阅读重点 |
| --- | --- | --- |
| AI Agent 核心（`enterprise-19/ai/models/ai_agent.py`） | `AIAgent` 第 237 行；`_generate_response` 第 496 行 | Agent 字段、对话组织、历史、RAG、工具集合 |
| Topic 模型（`enterprise-19/ai/models/ai_topic.py`） | 第 5 行 | 指令与工具关联 |
| AI 控制器（`enterprise-19/ai/controllers/main.py`） | `/ai/generate_response` 第 11 行 | public/guest、频道与消息访问检查 |
| 前端消息扩展（`enterprise-19/ai/static/src/discuss/core/common/thread_model_patch.js`） | `Thread.post()` 第 9 行 | 先发消息，再请求生成 AI 回复 |
| 服务器动作扩展（`enterprise-19/ai/models/ir_actions_server.py`） | `_get_ai_tools` 第 142 行；`_ai_tool_run` 第 306 行 | 工具注册、参数校验、执行环境、错误捕获 |
| 模型服务（`enterprise-19/ai/utils/llm_api_service.py`） | `LLMApiService`、`_request_llm_silent()` | 已还原的核心请求、工具循环、上限、超时 |
| Provider 定义（`enterprise-19/ai/utils/llm_providers.py`） | `PROVIDERS` 第 14 行 | 模型名称和 Provider/embedding 映射 |
| [独立 DeepSeek Agent 扩展](../../ai_deepseek/models/ai_agent.py) | `_get_llm_model_selection()`、`_generate_response()` | 从本地目录动态选择、Provider 映射、仅 DeepSeek 使用独立服务 |
| [DeepSeek 模型目录](../../ai_deepseek/services/model_catalog.py) | `refresh()`、`get_selection()` | `/models` 同步、失败保留、退役 Agent 兼容 |
| [DeepSeek API 服务](../../ai_deepseek/services/deepseek_api_service.py) | `DeepSeekLLMApiService` | 消息转换、密钥、整批工具调用校验、结果回填 |
| [DeepSeek 设置字段](../../ai_deepseek/models/res_config_settings.py) | `deepseek_key` | 复用系统参数并限制管理员读取 |
| [DeepSeek 资料限制](../../ai_deepseek/models/ai_agent_source.py) | `_check_deepseek_agent()` | 关联资料时检查 Agent 能力 |
| [DeepSeek 卸载处理](../../ai_deepseek/hooks.py) | `uninstall_hook()` | 保留 Agent 与 Key，并回退到默认模型 |
| [DeepSeek 回归测试](../../ai_deepseek/tests/test_deepseek.py) | `TestDeepSeekIntegration` | 适配协议、配置、工具、Sources 与卸载 |
| 参数校验器（`enterprise-19/ai/utils/tools_schema/validators.py`） | 第 36 行 | 实际支持的参数校验规则 |
| 资料来源（`enterprise-19/ai/models/ai_agent_source.py`） | 第 11 行；`user_has_access` 第 153 行 | 文件/URL、处理状态、引用访问标记 |
| Embedding 模型（`enterprise-19/ai/models/ai_embedding.py`） | 向量第 32 行；检索第 40 行；cron 第 64 行 | pgvector、相似片段、异步向量化 |
| 附件文字分块（`enterprise-19/ai/models/ir_attachment.py`） | `_chunk_text` 第 169 行 | 分块参数与文本处理 |
| Livechat 规则（`enterprise-19/ai_livechat/models/im_livechat_channel_rule.py`） | `ai_agent_id` 第 10 行 | 客服规则指定 Agent |
| 网站 AI 区块组件（`enterprise-19/ai_website_livechat/static/src/website/components/ai_livechat_component/ai_livechat.js`） | 提交第 188 行；建频道第 211 行 | 页面区块如何进入聊天 |
| [本模块业务方法](../models/ai_agent.py) | 第 15、59、132、142、203、265、275 行 | 报价、加购、网站上下文、搜索、商品解析 |
| [本模块工具与 Topic](../data/ai_sale_order_tool_data.xml) | 三个工具、两个 Topic | 描述、Schema、Python 桥接、工作指令 |
| 购物车标准方法（`odoo-19.0/addons/website_sale/models/sale_order.py`） | `_cart_add` 第 319 行；最终校验第 633 行 | 标准加购行为与扩展点 |
| 网站购物车方法（`odoo-19.0/addons/website_sale/models/website.py`） | 建车第 666 行；取车第 778 行；商城访问第 1012 行 | session、网站、客户、购物车有效性 |
| [本模块回归测试](../tests/test_ai_website_cart.py) | 第 100 行起 | 14 个工具业务层回归场景 |

## 3. 一条网站消息的完整调用过程

以“帮我下单一个黑色抽屉”为例，执行过程如下。

```text
浏览器 Thread.post()
    → 保存用户消息 mail.message
    → 检查频道是否有 ai_agent_id
    → POST /ai/generate_response
    → 检查频道可见性和消息访问权限
    → ai.agent._generate_response_for_channel()
    → 解析消息、准备最近历史及额外上下文
    → ai.agent._generate_response()
    → 构建系统指令、Topics、可选 RAG
    → 核心 LLMApiService 或独立 DeepSeekLLMApiService.request_llm()
    → 模型请求搜索工具
    → Odoo 执行真实商品查询，将结果交回模型
    → 模型请求加购工具
    → Odoo 校验并调用标准购物车方法
    → 将真实执行结果交回模型
    → 模型生成回复
    → _post_ai_response() 以 Agent 身份发布消息
    → Odoo 消息系统更新网页聊天记录
```

这条链路中，一句用户消息可能产生多次模型 API 请求。常见顺序是“理解 → 搜索 → 判断 → 加购 → 解释结果”；有规格歧义时，在搜索后就会转为向用户追问。

当前网站实现通过普通 JSON-RPC 等待处理，再将结果发布为聊天消息。前端的“正在思考”和 Odoo 消息总线更新，不等于模型 token 逐字流式显示；当前这条链路不能宣传为已经实现模型 SSE 流式输出。

### 3.1 模型收到什么

`_build_system_context()` 与 `_generate_response()` 组织的主要内容包括：

- Agent 的 `system_prompt`。
- 当前 UTC 时间、用户时区；非 public 用户还可能附带姓名、职位、邮箱、电话等用户信息。
- Agent 关联的全部 Topic 指令。
- 当前页面或会话额外上下文。
- 默认最近 20 条历史消息，以及当前问题。
- 可用工具的名称、描述和参数 Schema。
- 配置资料来源时，增加检索到的相关片段。

模型服务因此可能接收到用户消息、必要商品信息及上述用户上下文。项目的数据传输说明应以实际 Provider 和实际发送字段为准；不能简单说“数据始终完全留在本地数据库”。

### 3.2 聊天历史如何使用

`_retrieve_chat_history(..., no_messages=20)` 默认取有限窗口。聊天记录保存在 Odoo 数据库，与模型本轮能看到多少条历史是两件事。它不表示模型永久学习了客户偏好，也不表示跨浏览器、跨账号、跨所有会话自动共享记忆。

### 3.3 网站两个入口的差别

| 入口 | Agent 的来源 | 后续对话机制 |
| --- | --- | --- |
| 右下角在线客服 | 网站的 `channel_id` → Livechat 频道 → 匹配规则的 `ai_agent_id` | 进入聊天频道，复用 Agent 生成回复 |
| 页面 AI 聊天区块 | 区块中指定的 Agent 与客服频道 | 可使用现有 livechat，也可创建 `ai_chat`，再复用 Agent |

`ai_livechat` 负责将 Agent 接入客服；`ai_website_livechat` 负责网站编辑器中的 AI 聊天区块；`ai_website` 还包含网站编辑和页面生成等能力。不要单凭模块名字推断它们承担同一职责。

匿名访客通常以 `mail.guest` 参与对话，登录的 Portal/内部用户以 `partner_id` 参与。public 路由仍检查频道和消息访问权限，不表示所有 Agent 和业务数据都向互联网开放。核心 Agent 默认内部可用，Livechat 和网站区块扩展显式允许对应 Agent 被公开入口访问。

成功转人工后，`ai_livechat` 会清除频道的 `ai_agent_id`。旧频道此后不自动触发 AI，是转接后的正常状态；排查不回复时要检查这一字段。

## 4. Agent、Topic、Tool 的配置方法

### 4.1 Agent 的关键字段

| 字段 | 作用 | 开发注意点 |
| --- | --- | --- |
| `llm_model` | 选择实际聊天模型 | 对应 Provider 的 Key 必须存在；只改名称不等于供应商适配完成 |
| `system_prompt` | 角色、语言、任务总规则 | 尽量与 Topic 指令一致 |
| `response_style` | 分析/平衡/创造风格 | 温度映射为 0.2/0.5/0.8，具体模型未必接受或采用 |
| `topic_ids` | 加载任务规则与工具 | 全部合并，避免无关 Topic 导致冲突与上下文膨胀 |
| `sources_ids` | 添加资料来源 | 支持的 Provider 会请求 embedding；本版 DeepSeek Agent 禁止关联 |
| `restrict_to_sources` | 追加按资料回答的提示 | 属于模型行为约束，不是数据权限隔离 |
| `active` | 是否可用 | 被归档 Agent 无法正常接待 |

后台通常可从 AI 应用的 Agents、Topics、Configuration 进入配置；菜单名称随语言和已安装模块变化。网站 Agent 应优先只配置对该入口必要的 Topic，尤其避免把“内部导航、内部报价、CRM 获客、网站加购”全部作为同等指令暴露后期待模型自动消除冲突。

### 4.2 一个业务工具由什么构成

本模块网站搜索工具的关键结构可以简写为：

```xml
<record id="ir_actions_server_ai_search_website_products"
        model="ir.actions.server">
    <field name="name">AI: Search Website Products</field>
    <field name="model_id" ref="ai.model_ai_agent"/>
    <field name="state">code</field>
    <field name="use_in_ai" eval="True"/>
    <field name="ai_tool_allow_end_message" eval="False"/>
    <field name="code">
ai['result'] = record._ai_tool_search_website_products(query)
    </field>
    <!-- 实际文件还定义 ai_tool_description 与 ai_tool_schema -->
</record>
```

`ai_tool_description` 决定模型在什么条件下考虑使用该工具，`ai_tool_schema` 定义参数结构，`code` 负责把参数传入固定 Python 方法。`ai['result']` 是返回给模型的工具执行结果。

`_get_ai_tools()` 优先使用 XML ID 的后半部分作为工具名。例如本工具的完整 XML ID 是 `ai_sale_order_2nd.ir_actions_server_ai_search_website_products`，模型调用名通常是 `ir_actions_server_ai_search_website_products`，不一定与界面显示名或 Python 方法名相同。没有 XML ID 时才回退为 `action_<id>`。

### 4.3 参数 Schema 与业务校验

加购工具使用两个一一对应的数组：

```json
{
  "product_names": ["DESK0005", "DESK0006", "Two-Seat Sofa (Velvet)"],
  "quantities": [1, 1, 1],
  "note": ""
}
```

相同下标表示同一商品的数量。Schema 声明数组与元素类型，Python 再检查数组长度、商品存在性、规格唯一性及数量合法性。当前网站代码要求正的有限整数，排除布尔值、字符串、零、负数、小数、NaN 和无穷大。

当前校验器处理 required、类型、pattern、enum、maxLength、对象和数组递归等，但不是完整 JSON Schema 引擎。例如不能只在 Schema 中写 `minimum` 就假定业务端一定校验最小值；核心验证器未实现的约束必须由 Python 检查。当前数量 Schema 使用 `number`，整数规则由网站方法强制执行。

本模块关闭 `ai_tool_allow_end_message`，让工具的实际结果交回模型后再向用户解释。若开启，该机制可以添加 `__end_message` 参数，工具成功后提前结束模型循环；写操作工具应先确认它不会使回复跳过真实结果核实。

## 5. 执行身份、权限与可信边界

### 5.1 模型不能通过工具任意执行代码

模型只提供已经公布的工具名和参数。Odoo 检查工具名是否在可用集合中，然后执行开发者预先配置的服务器动作。服务器动作的 `safe_eval` 执行的是已保存的代码，不是把用户聊天内容当 Python 运行。

本模块的工具代码只桥接到明确的 Python 方法，不向模型开放任意 SQL、任意模型写入或付款接口。这一设计仍要求开发者限制参数、返回字段和可操作范围；提示词本身不能承担全部授权职责。

### 5.2 Server Action 的执行环境

`_ai_tool_run()` 将 `record`、`records`、`model` 设为 `sudo(False)`，并令 eval 环境 `env` 使用 `su=False`。这些设置使业务代码默认沿当前执行用户的正常 ORM 权限运行。

但应同时理解两个细节：

1. AI 工具路径会跳过服务器动作本身的一部分执行/用户组检查，源码专门对此显示配置警告。不能只给 Server Action 设置 group，就认定公开网站工具已经完成访问控制。
2. 业务方法内部如果主动使用 `sudo()`，仍会提升访问权限，因此要在方法内重新收紧公开可用范围。

Agent 一般通过 `self.topic_ids.tool_ids._get_ai_tools()` 提供工具，并未给本模块工具绑定某条 Agent 记录。回调中的 `record` 可能是空的 `ai.agent` recordset；本模块方法依赖 `self.env`，不需要读某条 Agent 字段。新增工具若一开始就 `self.ensure_one()`，需要先确认调用路径确实传入了单条记录。

### 5.3 本模块使用 sudo 的位置与含义

网站商品查询使用 `product.product.sudo()`，随后约束 `sale_ok=True`、`is_published=True`、当前网站或共享网站范围，并检查 `_is_add_to_cart_allowed()`。它返回目录名称、SKU、属性等必要信息，不返回成本价。

因此，正确表述是“网站工具显式限制对外商品范围”，而不是“查询完全遵守当前 Portal 用户的所有商品记录规则”。

`website.website_domain()` 允许 `website_id=False` 的共享内容及当前网站内容。`with_company(website.company_id)` 设置公司环境，不等于代码已经添加了严格的 `company_id` 隔离域。复杂多公司、多网站、客户专属目录应按实际规则专项验收。

标准网站购物车创建本身使用提升权限的内部实现，再回到当前用户的上下文并保存会话。Portal/匿名用户能用购物车，不表示获得了后台销售模型的全部权限。

## 6. 本模块两个业务流程与三个工具

模块清单依赖 `ai_app`、`sale`、`website_sale`、`website_livechat`、`ai_livechat`、`ai_website_livechat`；通过 XML 注册三个工具及两个 Topic。安装会带上原生商城、网站客服和页面 AI 聊天区块所需模块。网站/客服绑定和 Agent 选择仍需配置。

| 工具 | 对应方法 | 结果 | 当前适用入口 |
| --- | --- | --- | --- |
| AI: Create Draft Sale Order | `_ai_tool_create_sale_order` | 新建 `sale.order` 草稿报价单 | 有正常销售创建权限的内部业务入口 |
| AI: Search Website Products | `_ai_tool_search_website_products` | 查询网站真实商品候选 | 网站/Portal 聊天 |
| AI: Add Products To Website Cart | `_ai_tool_add_products_to_website_cart` | 给当前网站会话购物车增量加购 | 网站/Portal 聊天 |

后台报价工具将客户固定为工具执行时当前用户的 `partner_id`，没有提供“选择任意客户”的参数。它不 `sudo()` 创建销售单，所以普通 Portal 用户通常不能把它当后台下单通道使用。

网站 Topic 要求使用购物车工具，避免将 Portal 需求路由到后台报价工具。工具本身不执行 `action_confirm()`、不创建发票、不发起支付；网站客户仍进入标准购物车与结账流程。

### 6.1 网站商品搜索

`_ai_tool_search_website_products(query)` 做以下工作：

1. 检查非空查询、当前网站与商城访问权限。
2. 准备网站请求上下文。
3. 在已发布可售商品及网站范围内，搜索名称、SKU、条码、规格值。
4. 尝试当前界面语言及英语；完整查询无结果时，对词语做跨语言命中交集。
5. 优先精确 SKU/条码/名称，过滤不能加购的商品。
6. 最多返回 10 项，用 `has_more` 告知模型需要缩小范围。

返回结构示例：

```json
{
  "products": [
    {
      "product_id": 33,
      "name": "[FURN_8900] 黑色抽屉",
      "reference": "FURN_8900",
      "catalog_name": "Drawer Black",
      "attributes": []
    }
  ],
  "has_more": false
}
```

示例编号属于当前测试目录，不应硬编码进业务逻辑。搜索不会新增购物车商品或生成订单；为了衔接网站环境，它可能初始化或缓存价目表、税务位置等请求/session 信息。

当前返回没有价格和实时库存字段。因此现阶段应介绍“查询真实目录并加入购物车”，不能把该工具说成已经实现准确的自然语言实时报价、实时库存查询。标准购物车的价格、税务、库存扩展等规则仍按已安装模块与配置执行。

### 6.2 商品模板、变体与跨语言

Odoo `product.template` 是商品模板，`product.product` 是具体变体。商品 `name` 往往只含模板名，`display_name` 才显示 SKU 和属性。例如 `Two-Seat Sofa (Velvet)` 的基础名称可能是 `Two-Seat Sofa`，Velvet 保存在属性值中。直接把展示名称当普通 `name` 搜索，可能找不到真实存在的商品。

本模块按精确 SKU、条码、名称、规格关键词、展示名回退查找。它允许用户只给出部分属性：剩余匹配唯一时可以继续；有多个候选时必须追问缺失的规格，不能简单取第一条。

如“白色可定制化桌子”仍可能对应不同桌腿材质；“天鹅绒沙发”还需要从真实目录识别 Velvet。对模型的规则是：中文回复可以翻译说明，但工具参数优先使用原始 SKU，或完整复制目录返回的实际变体名，不自行编造翻译名称。

当前关键词提取使用 `re.findall(r"\w+", query.casefold())`，每词在商品名/SKU/条码/属性间 OR，词与词 AND。它是结构化关键词检索，不是商品语义向量搜索。连续中文组合可能成为一个词，模型需要分离关键词或缩小查询；不能据此承诺所有中文口语都一次精确匹配。

### 6.3 网站上下文与购物车 session

`/ai/generate_response` 没有 `website=True`。常规商城路由准备的网站对象，不一定在 AI 请求中已经就绪，所以 `_ai_prepare_website_sale_request()` 补齐：

- `request.website`：当前网站。
- `request.cart`：当前有效购物车。
- `request.fiscal_position`：税务位置。
- `request.pricelist`：当前价目表。

购物车归属依赖当前 HTTP session，核心缓存包括 `sale_order_id`、`website_sale_cart_quantity`。同一浏览器、同一 Odoo 网站聊天后打开 `/shop/cart`，才是最直接的对应验证方式。更换无痕窗口、浏览器或账号，可能对应不同购物车。

框架支持部分跨域聊天入口，不表示外部任意商城会自动共享 Odoo 购物车。跨域部署要单独验证 cookie、guest 身份、域名、网站识别和购物车归属。

## 7. 为什么预校验、savepoint 和 session 恢复都需要

### 7.1 框架捕获工具错误后，模型可以继续工作

`_get_ai_tools()` 内部 `_exec_tool()` 捕获多数异常，把错误文字返回给模型，让模型可以调整查询或向客户解释。数据库序列化错误会继续向上抛出。

这里没有为每个业务工具自动创建 SQL savepoint。某个工具执行了部分写入再抛出业务异常，异常被捕获后，请求可能继续，前面的写入未必自动撤销。

这正是原先“三件商品中最后一件找不到，前两件已加购；模型重试后前两件重复”的原因之一。

### 7.2 当前加购工具的保护顺序

```text
检查网站/商城访问
    → 校验数组和数量
    → 预先解析全部商品
    → 记录原 request.cart 和 session 值
    → 开启数据库 savepoint
        → 取/创建购物车
        → 逐行调用标准 _cart_add()
        → 最后一次 _verify_cart_after_update()
        → 可选备注
    → 成功：返回真实 added_qty 与 warning
    → 失败：savepoint 回滚，并恢复 request.cart/session
```

先解析全部商品，避免已知无效商品导致前序写入；savepoint 处理加购过程或最终校验异常；session 恢复处理数据库回滚不能恢复的浏览器会话缓存。这三层各有作用。

每行使用 `skip_cart_verification=True`，完整批次结束后统一最终校验，避免逐行最终校验产生额外副作用；并继续复用标准加购路径与相应扩展。

### 7.3 原子性与幂等性不是同一个保证

当前保证的是：**本次失败批次不留下部分商品增加。** 它没有实现持久化幂等键，也没有跨请求成功操作去重。

标准 `_cart_add(quantity=1)` 表示再加一件。如果相同批次成功执行两次，数量会累加两次。Topic 中“成功后不要重复调用”可减少模型重复操作，但不是数据库级幂等机制。

若后续需要更强保障，应开发操作 ID/请求 ID、执行记录及唯一约束，并针对并发请求验证。不能将此项作为当前已交付能力。

当前工具没有设置总数量、删除商品、清空购物车、应用优惠券或修改地址的接口；也未开放复杂配置器的自定义文本、组合商品明细和独立计量单位参数。网站数量当前要求整数，按米/重量销售的小数数量需要专门扩展。

## 8. 模型 Provider 与密钥的正确配置

### 8.1 当前本地适配情况

| Provider | 当前代码路径 | 可据此说明的范围 |
| --- | --- | --- |
| OpenAI | `_request_llm_openai()` | 对应 Responses API 路径，具体模型按配置与供应商支持验收 |
| Google | `_request_llm_google()` | Gemini 请求与工具适配，部分功能组合有限制 |
| DeepSeek | 独立 `DeepSeekLLMApiService._request_llm()` | 仅安装 `ai_deepseek` 的数据库中增加文本和 function tools 路径 |

DeepSeek 当前方法明确拒绝 `files`、独立结构化输出参数 `schema` 和 `web_grounding`，以 `UserError` 提示能力范围；embedding 与语音入口也明确拒绝。工具参数 Schema 与“要求模型按指定结果 Schema 直接输出”是不同用途。

因此下单测试通过，不等于图片理解、PDF 直接输入、联网检索、语音和知识库都已通过同一模型验证。

### 8.2 密钥来源与优先级

`_get_api_token()` 优先读取数据库系统参数，其次读取进程环境变量。

| Provider | 数据库系统参数名 | 进程环境变量名 |
| --- | --- | --- |
| OpenAI | `ai.openai_key` | `ODOO_AI_CHATGPT_TOKEN` |
| Google | `ai.google_key` | `ODOO_AI_GEMINI_TOKEN` |
| DeepSeek | `ai.deepseek_key` | `ODOO_AI_DEEPSEEK_TOKEN` |

表中只是名称，不包含实际值。密钥只放入受管理的配置，会议截图、文档、日志摘录、代码提交都不应包含实际 Key。

标准设置保留 OpenAI、Google 字段；安装 `ai_deepseek` 后继承 `ai_app.res_config_settings_view_form`，在 `ai_providers` 区域新增 DeepSeek API Key、同步状态和刷新按钮。保存变化后的 Key 会获取 `/models` 并写入 `ai.deepseek_models`。字段使用 `config_parameter="ai.deepseek_key"`，限制 `base.group_system`，界面密码显示。既有参数直接复用，安装时不会另写一份客户 Key。

### 8.3 改一个 Agent 不会切换所有 AI 功能

网站对话使用 `ai.agent.llm_model`。而 `ir.actions.server` 的 `state="ai"` 是另一条自动化路径，当前类中默认 `AI_PROVIDER="openai"`、`AI_MODEL="gpt-4.1"`。

所以把网站 Agent 从某个 GPT 模型改为 DeepSeek，只影响使用该 Agent 的对话路径。其他 AI Action、语音、编辑器等入口需分别核实其模型选择方式和 API 支持。

### 8.4 新增或更换模型时验收什么

至少验证普通中文回复、工具名称和参数格式、多轮工具结果回传、错误后恢复、歧义追问、超时表现、实际成本及延迟。能调用一个 OpenAI 兼容接口，不等于其工具、Schema、文件、embedding 全部兼容。

独立扩展已经完成：`ai_deepseek` 依赖 `ai_app`，通过模型继承、目录缓存和独立服务实现，不改动核心 `PROVIDERS`、不做全局 monkey patch。`llm_model` 原字段的 Selection 采用函数对象，Odoo 19 不能直接用 `selection_add` 扩展；模块将 selection 重新绑定为方法名 `_get_llm_model_selection`，在 `super()` 结果上追加当前数据库缓存的 DeepSeek 模型。仅选择 DeepSeek 目录型号的生成路径实例化新服务，其他模型继续 `super()`。

Agent 切换 Provider 时，核心 `write()` 即使没有 Sources 也会询问 embedding 模型，所以动态 DeepSeek 模型在无 Sources 时返回 `False`；若已有 Sources 则拒绝切换。模型目录刷新失败会保留上次成功列表；供应商移除但仍在用的 ID 会标记为不在当前目录，不自动切换。资料模型另加约束，覆盖直接创建、改关联 Agent、上下文默认值和内联资料入口。卸载 hook 将含归档记录的 DeepSeek Agent 切回 `gpt-4o`，保留 Agent、Topic、历史与客户 Key；卸载后继续对话需要有效 OpenAI 配置。

## 9. RAG 知识库的实现与权限事实

### 9.1 RAG 用于什么

RAG 是检索增强生成：先从资料找到相关片段，再将片段与问题一起交给语言模型。适合产品手册、FAQ、退换货政策和操作规程。它通常不需要微调模型，也不是把资料永久写入模型参数。

商品 SKU、当前发布状态和具体变体属于结构化业务数据，本模块直接查询 ORM。不要用旧文档片段替代购物车执行前的真实商品校验。

### 9.2 当前源码的资料处理流程

```text
上传文件或添加 URL
    → ai.agent.source（processing）
    → URL 抓取/附件文字提取
    → 文本分块
    → 后台 cron 请求 embedding API
    → ai.embedding 保存片段及向量（indexed）

用户提问
    → 将问题向量化
    → pgvector 检索对应资料中最相似的片段
    → 默认取 top 5
    → 片段拼入本轮模型上下文
    → 生成回答和适用的引用
```

当前分块目标约 1500 字符，margin 200，最小 1000、最大 5000；这些是字符分块参数，不是模型 token 上限。向量字段定义维度 1536，使用 pgvector 余弦距离索引；供应商返回维度必须匹配。

`ai` 模块 pre-init 会尝试创建 PostgreSQL `vector` 扩展。商品工具本身不使用向量检索，但当前基础 AI 模块安装仍会检查扩展，所以安装前应准备好数据库扩展和相应数据库权限。

### 9.3 聊天可用不代表 embedding 可用

本版独立适配不登记 `deepseek-embed`，`get_embedding()` 明确拒绝调用，并通过 Agent 和资料模型约束禁止 DeepSeek Agent 关联 Sources。其支持范围是文本与业务工具。知识问答应选用已有支持的 Provider，或另行开发经验证的检索服务组合，不能将网站加购成功宣传为知识库已支持。

### 9.4 文件不能下载，不代表模型不会读到内容

当前 `user_has_access` 主要参与引用显示判断。`_build_rag_context()` 会把检索片段放进模型上下文，对被标为不可访问的引用，提示模型不要列出引用；这不等于先从正文中剔除了所有相关内容。

因此不能对客户承诺“Portal 不能下载某附件，所以 AI 也绝不会使用其内容”。对外网站 Agent 应配置可对外使用的资料。若要求内外部机密资料混用且严格隔离，必须在检索层做实际身份过滤，或拆分 Agent 与资料范围，并增加相应测试。

`restrict_to_sources` 也是提示规则，不是硬性权限控制；资料本身包含的指令仍应按不可信内容处理。涉及授权、价格、支付的决策应由业务工具和业务规则确认。

## 10. 新增业务工具的开发步骤

建议按以下顺序实施：

1. 定义业务边界：入口身份、允许读取/修改对象、必需参数、成功依据。
2. 在业务方法中写硬性校验，先验证完整输入，复用 Odoo 业务 API。
3. 写操作需要明确事务范围、失败回滚和成功重复提交策略。
4. 返回模型能理解的实际结果；必要时返回结构化候选和明确错误。
5. 注册 `ir.actions.server` 的描述、Schema、桥接代码。
6. 将工具加入合适 Topic，写清何时搜索、何时追问、何时执行。
7. 将 Topic 关联目标 Agent，而不是默认暴露给所有 Agent。
8. 分别做业务方法测试、真实模型对话测试、浏览器/session 验证。

### 10.1 教学示例：查询一个网站商品摘要

**以下代码仅用于讲解如何开发新工具，尚未加入当前模块，不属于已交付功能。** 示例不新增库存或价格能力，也不允许任意字段读取。

```python
from odoo import _, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.http import request


class AIAgent(models.Model):
    _inherit = "ai.agent"

    def _ai_tool_get_website_product_summary(self, reference):
        if not isinstance(reference, str):
            raise UserError(_("Please provide a product reference."))
        reference = reference.strip()
        if not reference or len(reference) > 80:
            raise UserError(_("Please provide a valid product reference."))

        website = (
            getattr(request, "website", None)
            or self.env["website"].get_current_website()
        )
        if not website or not website.has_ecommerce_access():
            raise UserError(_("The current website does not allow ecommerce access."))

        Product = self.env["product.product"].sudo().with_company(
            website.company_id
        ).with_context(website_id=website.id)
        domain = (
            Domain("sale_ok", "=", True)
            & Domain("is_published", "=", True)
            & website.website_domain()
            & Domain("default_code", "=ilike", reference)
        )
        products = Product.search(domain, limit=2).filtered(
            lambda product: product._is_add_to_cart_allowed()
        )
        if len(products) != 1:
            raise UserError(_("Please provide a unique available product reference."))

        return {
            "name": products.display_name,
            "reference": products.default_code,
            "unit": products.uom_id.name,
        }
```

该示例沿用当前项目网站目录边界；若客户有独立多公司规则，需要再补对应域和测试。选择允许返回的固定字段，优于接收模型任意传入 `fields` 后直接 sudo 读取。

### 10.2 教学示例：注册工具及 Topic

**以下 XML 同样是新增能力的教学模板，不能将其存在于文档理解为系统已经安装。** 假定它位于一个声明依赖 `ai_sale_order_2nd` 的独立扩展模块。

```xml
<odoo>
    <record id="action_ai_website_product_summary" model="ir.actions.server">
        <field name="name">AI: Website Product Summary</field>
        <field name="model_id" ref="ai.model_ai_agent"/>
        <field name="state">code</field>
        <field name="use_in_ai" eval="True"/>
        <field name="ai_tool_allow_end_message" eval="False"/>
        <field name="ai_tool_description">
Read the public summary for one exact product reference on the current website.
Use the original reference from a catalog result; do not invent a reference.
        </field>
        <field name="ai_tool_schema"><![CDATA[
{
  "type": "object",
  "properties": {
    "reference": {"type": "string", "description": "Exact catalog reference"}
  },
  "required": ["reference"]
}
        ]]></field>
        <field name="code">
ai['result'] = record._ai_tool_get_website_product_summary(reference)
        </field>
    </record>

    <record id="topic_ai_website_product_summary" model="ai.topic">
        <field name="name">Website Product Summary</field>
        <field name="description">Read a public catalog summary.</field>
        <field name="instructions">
Use this tool only when a valid catalog reference is known.
If the user supplies a vague description, search the catalog first.
Explain only fields actually returned; do not claim stock or delivery availability.
        </field>
        <field name="tool_ids"
               eval="[(6, 0, [ref('action_ai_website_product_summary')])]"/>
    </record>
</odoo>
```

方法、描述、参数名、Schema required、桥接代码必须相互一致。缺省参数策略也要一致；例如当前本模块把 `note` 列为 required，但没有备注时传空字符串，避免模型遗漏导致参数验证失败。

## 11. 安装、升级与配置生效

### 11.1 在新环境启用网站下单

顺序建议为：

1. 准备匹配版本的 Odoo 19 企业版代码、相关依赖和 PostgreSQL vector 扩展。
2. 确认 `addons_path` 包括标准 addons、企业版 addons、本仓库根目录。
3. 安装 `ai_deepseek` 和 `ai_sale_order_2nd`；其 `depends` 会带上 AI、商城和网站聊天集成模块，前置模块代码须在 `addons_path` 中可用，不需要修改企业版核心。
4. 管理员在 AI 设置配置并保存 DeepSeek Key，确认模型目录同步成功；Agent 从当前目录选择型号且不关联 Sources，先验证简单文本回复。
5. 创建/选择网站 Agent，关联 `Website Cart Ordering` Topic，确认搜索和加购工具都在 Topic 中。
6. 在网站设置选择 Livechat 频道，在频道规则指定 Agent；或在页面 AI 区块指定 Agent。
7. 检查商品可售、已发布、网站可见、SKU 和规格信息。
8. 使用 Portal/匿名身份按商城访问策略验收，同一浏览器检查购物车结果。

当前购物模块 manifest 已直接依赖 `website_livechat`、`ai_livechat` 和 `ai_website_livechat`，网站、在线客服及网站 AI 等下层依赖由 Odoo 递归安装。`ai_deepseek` 与购物模块互不依赖，前者可单独用于其他 Agent，后者也可使用其他已支持的模型。安装两个模块仍不会自动完成网站聊天入口配置。

### 11.2 什么变化需要什么操作

| 变化 | 通常需要的操作 | 原因 |
| --- | --- | --- |
| 修改已有 Python 方法 | 重启加载相关代码的 Odoo 进程 | 运行进程已导入 Python 模块 |
| 修改工具/Topic XML | 升级模块，或受控地导入目标记录；然后核对数据库值 | 工具描述与指令实际保存在数据库 |
| 新增字段、模型、依赖、权限文件 | 按发布流程升级模块并重启 | 涉及注册表、表结构或安装数据 |
| 在后台修改 Agent 模型/Topic | 保存配置并核对新会话使用的 Agent | 多数配置本来存数据库，不等于改 Python |
| 修改前端 JS/资源声明 | 按部署方式更新模块/资源，必要时重启并刷新 | 浏览器资源缓存与服务端资源构建 |
| 修改进程环境变量 | 重启读取该环境的服务进程 | 已运行进程不会自动获得外部环境变化 |

只重启不能保证修改过的 XML 已写入数据库；只改 XML 文件也不能假定当前 Agent/工具记录已改变。公开会话之前已转人工或关联旧 Agent 时，应检查会话本身，必要时开启新对话。

### 11.3 升级命令示例

以下使用 Windows 路径占位符作为操作示例，**文档编制没有执行这些命令**。在维护窗口按项目流程停掉目标服务，避免第二个进程与现有服务同时争抢升级，确认数据库后执行：

```powershell
& 'C:\path\to\venv\Scripts\python.exe' `
  'C:\path\to\odoo\odoo-bin' `
  -c 'C:\path\to\odoo.conf' `
  -d target_db `
  -u ai_sale_order_2nd `
  --stop-after-init --no-http --max-cron-threads=0
```

随后启动正常服务并核对目标工具和 Topic。`-u` 是升级已安装模块，首次安装使用 `-i`。数据库名与路径均为占位示例，执行前必须替换。

模块 XML 中没有 `noupdate` 包裹的记录，升级可能覆盖这些 XML 字段上手工修改的数据库配置。客户现场调整的指令应纳入版本管理或明确记录，避免升级后丢失。

此前修复采用目标记录受控导入，使三个网站工具/Topic 相关配置生效；这是一种当前实例的修复方式，不替代以后可重复的模块升级与版本交付流程。

## 12. 有序排障：先确定失败在哪一层

排查要以当前正在监听端口的进程、它加载的配置、对应数据库和最新日志为准。IDE 打开的文件、旧日志或另一套 Odoo 进程都可能与用户正在访问的网站不一致。

| 现象 | 优先检查 | 验证依据与处理方向 |
| --- | --- | --- |
| 消息发送后一直没有 AI 回复 | 频道 `ai_agent_id`、前端 `/ai/generate_response`、模型 Key/网络 | 先确认是否触发生成路由，再看 API 错误；转人工旧频道可能已清空 Agent |
| 界面也没有友好的错误提示 | `/ai/post_error_message` 是否再次失败 | 当前错误改写也依赖同一 Agent 模型；模型不可用时它也可能失败 |
| 普通聊天正常，但买商品只反复追问 | Agent 的 Topic、搜索工具是否加载、真实工具参数 | 应先查目录，再询问确实缺失的规格；用真实模型对话复现 |
| 后台工具测试可用，Portal 失败 | 是否调用错后台报价工具 | 网站应调用购物车工具；内部创建报价权限与网站购物车不同 |
| 商品存在但报找不到 | 发布/可售/网站范围、SKU、语言、属性、真实 `name` 与 `display_name` | 从搜索工具结果复制 SKU 或完整变体名，禁止自行编造目录名 |
| 提示多个商品匹配 | 是否真实存在多个变体 | 列出实际候选并问缺少属性；不要把合理消歧当异常 |
| 聊天说加购成功，但车里没有 | 当前浏览器/session、网站、账号、实际工具成功记录 | 同一会话打开 `/shop/cart` 检查销售行；聊天文字不能代替数据库事实 |
| 数量比预期多 | 之前已有数量、是否重复成功调用 | `_cart_add` 是增加数量；失败批次回滚不等于跨请求幂等 |
| 第三件失败却前两件留下 | 运行进程是否加载最新原子性修复 | 检查全部预解析、savepoint、session 恢复；用回归测试验证 |
| Sources 无法保存到 DeepSeek Agent | 模型和 Sources 的支持范围 | 本版适配主动禁止；采用已支持的 Provider，或另行开发检索方案 |
| 改代码后行为没变化 | 端口监听 PID、Python 重启、XML 数据是否更新 | 分清代码与数据库配置两个生效渠道 |
| 网站 A 出现网站 B 商品或复杂多公司疑问 | 网站识别、共享商品、`website_domain`、公司政策 | 共享网站商品是允许行为；严格多公司策略需实际域与专项验收 |
| 回复慢 | 模型轮数、每轮网络时延、Topic/历史长度、工具查询 | 一条消息可能多次调用；不要只统计最后一次 API |

### 12.1 推荐保留的诊断信息

定位问题通常需要：测试页面 URL、测试身份、会话/消息 ID、时间、当前网站、Agent 名称与模型、工具名与必要参数、业务错误和最终购物车结果。向外部共享前移除 Key、个人联系方式和无关业务数据。

常见日志线索包括：

```text
AI: Call action AI: Search Website Products with arguments: ...
AI: Call action AI: Add Products To Website Cart with arguments: ...
An error occurred while executing ...
LLM API request failed: ...
AI: API calls ...
```

没有工具调用日志，不等于商品查询工具报错；模型可能根本没有调用。已有工具错误日志时，再核对传入参数、目录事实与业务异常。

### 12.2 循环和超时参数

| 参数 | 当前默认 | 含义 |
| --- | --- | --- |
| `ai.max_successive_calls` | `20` | 单次处理最多模型调用轮数 |
| `ai.max_tool_calls_per_call` | `20` | 每轮最多执行的工具数量 |
| 模型 `_request()` 默认超时 | `30` 秒 | 单次 API 请求默认超时，不是完整业务必定 30 秒结束 |
| 历史消息窗口 | `20` 条 | `_retrieve_chat_history()` 默认参数 |
| 资料检索片段 | `5` 条 | 当前 RAG 默认 top_n |

多个工具在当前 Python 循环中逐一执行，不能把模型一次返回多个工具说成服务端自动并发。调高轮数上限可能增加费用与等待时间，应先解决无效循环。

`ai_logging.py` 提供调用次数、工具耗时和 token 估算。当前 token 估算有按字符数折算的粗略逻辑，不是供应商正式计费账单；费用核算应结合供应商实际用量。

### 12.3 当前未实现的错误兜底改进

前端生成失败后会调用错误改写接口，后者仍依赖同一模型。未来可增加不依赖模型的静态故障提示、请求跟踪 ID 和模型可用性监控，但这些属于建议，不能列为当前已实现。

## 13. 测试、验收与发布记录

### 13.1 已有 14 个业务层回归测试

测试位于 `tests/test_ai_website_cart.py`，标记为 `post_install`、`-at_install`。覆盖：

1. 完整变体显示名、去括号变体名和 SKU。
2. 只提供模板名称时保持歧义。
3. 排除未发布和其他网站专属商品。
4. 正常批次全量加购，最终校验只执行一次。
5. 第三件无效时保持原购物车不变。
6. 第二行加购失败时回滚第一行。
7. 新购物车最终校验失败时回滚订单与 session。
8. 非法数量不创建购物车。
9. 部分规格词仍唯一时正确匹配。
10. 部分规格存在多个候选时报告歧义。
11. 搜索返回真实 SKU 与网站范围内商品。
12. 中文上下文下英文目录名与中英混合关键词。
13. 搜索不新增订单或购物车行。
14. 超过 10 个结果时提示 `has_more`。

本次源码还原并安装独立适配后，这 14 项再次通过；独立适配的 19 项测试也全部通过，覆盖模型选择、核心隔离、Key 优先级、消息与工具协议、整批非法调用、能力限制、Sources 和卸载回退。两模块合计 33 项测试，失败 0、错误 0。

事务回归中特别要避免测试自己的 `assertRaises` savepoint 掩盖生产方法缺少回滚的问题；关键失败用例应在接住业务异常后直接核对原业务状态与 session。

### 13.2 还要做真实模型对话验收

业务方法测试能验证“给定正确参数后做什么”，不能证明模型一定能提取正确参数或选对工具。本次还使用实际 DeepSeek 与 Portal 身份、真实 Agent/Topic、请求模拟环境，在核心已还原、新适配已安装的状态下重新验证了：

- `帮我下单一个黑色抽屉`：查询真实目录后，给产品 `FURN_8900` 加购 1 件。
- `帮我下单 DESK0005、DESK0006 各一个，再加一个 Two-Seat Sofa 天鹅绒。`：最终传入三个真实商品标识，分别加购 1 件。

这些实际模型业务链路测试的写入已回滚，不是会议当天浏览器状态的永久保证。发布后仍应在目标网站、目标身份和同一浏览器 session 中完成一次界面验收。

建议演示前检查：唯一商品加购、真实变体追问、不存在商品、已有购物车再加数量、模型服务可用性。库存限制、多公司、匿名/仅登录商城、跨域和复杂配置商品，应按客户真实范围另外测试。

### 13.3 测试命令示例

以下为独立测试数据库的命令模板，**不是本次执行记录**。测试数据库须有匹配模块与安装环境，数据库名为占位示例。

```powershell
& 'C:\path\to\venv\Scripts\python.exe' `
  'C:\path\to\odoo\odoo-bin' `
  -c 'C:\path\to\odoo.conf' `
  -d ai_cart_test_db `
  -u ai_sale_order_2nd `
  --test-enable --test-tags /ai_sale_order_2nd `
  --stop-after-init --http-port=8071 --max-cron-threads=0
```

示例使用独立测试端口，执行前确认该端口可用。现有用例使用 `MockRequest`，它会读取测试 HTTP 服务的端口；不要直接将普通测试启动命令加上 `--no-http` 后就假定同样可运行。若通过无 HTTP 的 Odoo shell 运行测试，应沿用已经验证的测试封装，显式 mock `HttpCase.http_port()`，而不是改动生产业务代码。

### 13.4 后续开发优先级建议

| 方向 | 解决的问题 | 当前状态 |
| --- | --- | --- |
| 成功操作幂等与审计 | 模型/网络重试导致重复成功加购 | 需要新增持久化机制 |
| 静态故障提示与监控 | 模型失效时连错误改写也失败 | 需要新增 |
| 对外 Agent 精简 Topic | 减少任务冲突、无关工具和上下文费用 | 需按客户用途治理配置 |
| 独立模型适配模块及设置页 | 降低核心修改升级风险、便于客户配置 | 已由 `ai_deepseek` 实现；升级时持续回归扩展点 |
| 库存/价格专用工具 | 对客可靠回答实时价格及可用性 | 当前搜索工具未提供这些字段 |
| 资料检索身份过滤 | 严格隔离内部与外部知识内容 | 需按权限需求设计与验收 |
| 复杂商品和计量单位 | 小数数量、自定义属性、组合商品 | 需要专门参数和业务支持 |
| 受审批的确认/支付流程 | 扩展业务自动化范围 | 当前没有对应工具，需另行设计 |

开发交付应始终把“模型能说什么”“工具实际执行了什么”“数据库最终状态是什么”放在同一条验收链路中核对。客户会议可以围绕自然语言便利性介绍价值，技术交付则以工具边界、真实业务结果和可重复测试为准。
