# AI Sale Order Assistant — Odoo 19 AI 网站购物助手

模块：`ai_sale_order_2nd` · 版本：`19.0.1.0.0` · 作者：Suto · 许可证：LGPL-3 · 文档更新：2026-11-16

本模块把商品查询和购物车操作提供给 Odoo AI Agent。访客在网站聊天中描述商品、规格和数量，AI 查询真实目录，明确具体商品后加入当前网站购物车，客户再通过 Odoo 标准流程核对、结账和付款。模块另提供一个面向内部用户的草稿报价工具。

## 1. 与 DeepSeek 模块的关系

| 模块 | 作用 | 使用方式 |
| --- | --- | --- |
| `ai_sale_order_2nd` | 提供商品搜索、加购、草稿报价等业务工具和 Topic | 可配合已支持工具调用的不同模型 |
| [`ai_deepseek`](../ai_deepseek/README.md) | 连接 DeepSeek、自动发现模型、配置 Key、转换消息和工具协议 | 使用 DeepSeek 时另外安装 |
| Odoo 原生网站与 AI 集成 | 提供网页聊天界面、访客会话、Agent 和工具执行框架 | 由本模块依赖带入 |

两个自定义模块互不依赖。只需要 DeepSeek 文字客服时，可以单独部署 `ai_deepseek` 和网站客服集成；需要本文的购物流程时安装本模块。安装模块后，还需配置模型凭据、Agent、Topic、网站和客服频道。

```text
访客消息 → 网站客服频道 → AI Agent + Website Cart Ordering
                              ↓
                       商品查询 / 规格确认
                              ↓
                       当前网站购物车
                              ↓
                    客户核对 → 标准结账流程
```

## 2. 环境与安装

### Odoo 依赖

本模块适配当前 Odoo 19 企业版 AI 接口，需要匹配版本的标准及已授权企业版源码。直接依赖已在 [manifest](__manifest__.py) 中声明：

| `depends` | 用途 |
| --- | --- |
| `ai_app` | Agent、Topic、工具及 AI 配置界面 |
| `sale` | 销售报价和订单基础功能 |
| `website_sale` | 网站商品、购物车与结账 |
| `website_livechat` | 网站客服频道与聊天入口 |
| `ai_livechat` | 将 AI Agent 接入在线客服 |
| `ai_website_livechat` | 页面内 AI 聊天区块集成 |

Odoo 会递归安装 `ai`、`website`、`im_livechat`、`ai_website`、`html_builder` 等下层依赖。相关源码必须已经存在于 `addons_path`；`depends` 不会下载企业版源码、配置 API Key，或替管理员绑定网站。

### 新数据库的 pgvector 前置条件

原生 `ai` 安装时需要 PostgreSQL 的 `vector` 扩展，即使当前购物工具不使用知识库，也要满足此条件。数据库服务器须先安装与 PostgreSQL 版本匹配的 pgvector。

然后用 PostgreSQL 管理员连接到**本次安装使用的目标数据库**，执行：

```sql
SELECT current_database();
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
```

每个新数据库需要单独启用。若报“只有超级用户能创建扩展”，由管理员预先执行上述 SQL 即可，不需要把 Odoo 业务账号改成超级用户。若报扩展文件不存在，应先安装 pgvector，不能通过跳过 AI 安装检查解决。

### 安装与升级

1. 将本模块目录放到配置的 `addons_path` 下；使用 DeepSeek 时同时放入 `ai_deepseek`。
2. 重新加载 Odoo 代码，在开发者模式下更新应用列表。
3. 搜索并安装 **AI Sale Order Assistant**。本模块 `application=False`，找不到时移除默认的“应用 / Apps”筛选。
4. 使用 DeepSeek 时安装 **AI DeepSeek Provider**，按其 README 配置 Key、同步模型并选择 Agent 模型。

也可以通过命令行安装。下面使用通用路径占位符，`python` 必须是 Odoo 使用的虚拟环境解释器；将 `your_database` 替换为实际数据库名，调整脚本和配置路径：

```powershell
# 新安装；同时使用 DeepSeek 时执行此示例。
python /path/to/odoo/odoo-bin -c /path/to/odoo.conf -d your_database -i ai_deepseek,ai_sale_order_2nd --stop-after-init --no-http --max-cron-threads=0

# 已安装环境更新依赖、工具和 Topic。
python /path/to/odoo/odoo-bin -c /path/to/odoo.conf -d your_database -u ai_sale_order_2nd --stop-after-init --no-http --max-cron-threads=0
```

通过命令行升级前停止同一目标环境的正常 Odoo 服务，完成后按原启动方式恢复。Python 修改需要重启加载；XML 或依赖修改需要升级模块。仅修改 Agent、频道规则或网站绑定时，保存并开启新的聊天会话即可。

## 3. 启用右下角 AI 在线客服

### 第一步：配置网站 Agent

进入 **AI → Agents / 智能体**，创建客服 Agent，或选择原生模块提供的 `Livechat AI Agent`：

- 选择已经配置有效凭据的模型。使用 `ai_deepseek` 时，先保存 Key，确认模型目录同步成功，再从实际返回的列表选择型号。
- 配置客服角色、回复语言和业务范围。
- 在 **Topics / 主题** 中添加 **`Website Cart Ordering`**。Topics 为空时，Agent 无法调用本模块的商品查询和加购工具。
- 对外网站 Agent 按用途选择必要 Topic；内部草稿报价场景使用的 `Sale Order Creation` 应关联到合适的内部 Agent。

`ai_deepseek` 当前禁止 DeepSeek Agent 关联 Sources。公司服务时间等简短背景可以写入提示词，PDF/说明书知识库需要另外的检索方案。

### 第二步：配置在线客服频道规则

进入 **在线客服 / Live Chat → 频道**，新建或打开一个频道，例如 `Support`，在 **Rules / 规则** 中配置：

| 字段 | 建议值 |
| --- | --- |
| Live Chat Button / 在线客服按钮 | `Show`；需要自动弹出时选择 `Open automatically` 并填写延时 |
| AI Agent | 第一步配置的网站客服 Agent |
| Scripted Bot / 脚本机器人 | 使用 AI 接待的规则中留空 |
| Enable ChatBot / 启用条件 | `Always`，让 AI 始终接待 |
| URL Regex / URL 正则 | 留空覆盖全部页面；只在商城启用可填写 `/shop` |
| Countries / 国家 | 普通全站启用时留空 |
| Matching order / 匹配顺序 | 能识别访客国家时，匹配的国家专属规则先于通用规则；同组中序号较小的规则先匹配 |

`Support` 只是示例名称，可以使用自己的频道。规则若只匹配 `/im_livechat/` 或 `/contactus`，就不会覆盖普通首页和商城。设置为 `Always` 且匹配到 AI 规则时，不需要人工客服在线。

### 第三步：将网站绑定到同一个频道

进入 **网站 → 配置 → 设置**，先选中实际使用的网站。在 **在线客服 / Livechat** 中启用功能，将 **Channel / 频道** 选择为第二步配置的频道并保存。

必须保证网站选择的频道与 AI 规则所在频道一致。多网站分别配置；给一个网站绑定频道不会自动启用其他网站。

### 第四步：在新会话中验证

1. 退出网站编辑模式，打开目标数据库、目标网站的前台页面。
2. 点击右下角聊天按钮，先问“你好，请用中文介绍你能提供的帮助”，验证模型连接。
3. 用本网站实际已发布的商品名或 SKU 询问、加购，再在**同一浏览器会话**打开 `/shop/cart` 核对。
4. 如果仍显示旧脚本机器人，结束旧会话重新开始；也可新开无痕窗口，确认数据库和网站选择正确。

页面内嵌的 AI 聊天区块是另一种原生入口，由 `ai_website_livechat` 提供，可在网站编辑器中添加并选择对应 Agent。仅放入页面区块不会自动配置右下角频道；两种入口应各自核对绑定和实际购物车会话。

## 4. Topic 与业务工具

下表的外部 ID 均以 `ai_sale_order_2nd.` 为前缀，配置定义在 [工具与 Topic XML](data/ai_sale_order_tool_data.xml)。

| 类型 | 界面名称 | 外部 ID 后缀 | 作用 |
| --- | --- | --- | --- |
| Topic | Website Cart Ordering | `ai_topic_website_cart_ordering` | 网站商品搜索、规格澄清、加购及购物车链接 |
| Topic | Sale Order Creation | `ai_topic_sale_order_creation` | 内部用户的草稿报价流程 |
| Tool | AI: Search Website Products | `ir_actions_server_ai_search_website_products` | 根据 `query` 查询当前网站真实目录 |
| Tool | AI: Add Products To Website Cart | `ir_actions_server_ai_add_products_to_website_cart` | 根据 `product_names`、`quantities`、`note` 执行加购 |
| Tool | AI: Create Draft Sale Order | `ir_actions_server_ai_create_sale_order` | 创建当前执行用户所关联客户的草稿报价 |

网站 Topic 包含搜索和加购两个工具；内部 Topic 包含草稿报价工具。内部报价使用执行用户的权限创建销售单，不提升权限，也不提供“指定任意客户”参数。

网站搜索返回 `product_id`、显示名、内部参考、英文目录名和属性，最多显示 10 项并用 `has_more` 标明还可能有结果。后续加购优先使用返回的准确内部参考或完整变体名，不应自行翻译、缩写或猜测目录标识。

## 5. 商品准备与使用示例

准备商品时，确认 **可销售、已发布、属于当前网站可用范围、通过标准商城加购校验**。建议为具体变体设置容易识别的 SKU，并维护必要的名称和属性翻译。

商品模板与商品变体要区分：例如“双人沙发”可能同时有 Velvet、Leather 等规格。只说模板名存在多个匹配时，工具会报告歧义，由 AI 根据真实候选追问缺失属性。明确型号和数量后再加入购物车。

以下语句需要替换为实际目录中的商品，示例本身不会创建商品：

```text
帮我找一下黑色抽屉。
把一个 SKU-001 加入购物车。
SKU-001 加两个，SKU-002 加一个。
双人沙发有哪些材质？我要其中天鹅绒款一件。
```

网站加购数量必须是有限的正整数；零、负数、小数、布尔值和无效数值会被拒绝。当前工具没有单位转换和复杂商品配置参数。

搜索会结合当前语言和英文目录匹配关键词，不代表能自动翻译所有商品术语。多语言目录应启用并维护所需语言；英文未激活时，Odoo 写入其他语言的翻译可能同时覆盖英文基础名称，需要在准备翻译数据时核对。

## 6. 业务边界与失败处理

| 行为 | 当前实现 |
| --- | --- |
| 商品访问范围 | 网站工具采用受限 `sudo()` 查询，显式限制可销售、已发布、当前网站及可加购商品；不能描述为完全依赖访客的普通商品记录规则 |
| 购物车归属 | 使用当前网站和 HTTP session 的标准购物车；切换浏览器、账号或网站可能对应不同购物车 |
| 加购数量 | 按增量增加，已有 1 件再加 1 件会变成 2 件 |
| 批量失败 | 先解析整批商品和数量；更新包在 savepoint 中，异常时回滚本批数据库修改并恢复相关 session 状态 |
| 标准商城警告 | 返回实际 `added_qty` 和警告；标准规则调整数量或返回 0 不等于抛异常，应按真实工具结果回复 |
| 成功后重试 | 尚无跨请求的持久化幂等机制；重复执行成功批次仍可能再次加量 |
| 实时价格与库存 | 搜索结果未提供专用价格/库存字段；价格、税费、配送等在标准购物车和结账中核对 |
| 确认订单、开票和支付 | 当前没有对应工具，由客户继续标准结账流程 |

报价工具与网站工具的数量校验、事务处理路径不同，不能把网站整批加购的保证自动套用到任意后台工具。业务成功以工具返回和数据库中的实际结果为准，模型输出“已完成”本身不构成完成证据。

## 7. 常见问题

| 现象 | 检查与处理 |
| --- | --- |
| 安装时提示 `vector` 权限不足 | 管理员在实际目标库创建 `vector`；不要只在 `postgres` 或其他业务库创建 |
| 应用列表找不到模块 | 核对 `addons_path`、更新应用列表、移除 Apps 筛选，检查依赖源码是否可用 |
| 网页没有聊天按钮 | 检查目标网站的频道、频道可用性、匹配规则是否隐藏按钮、URL/国家范围和网站编辑模式 |
| 只有 `/contactus` 或测试页能聊天 | 扩大 AI 规则 URL 范围，通常留空；确认网站绑定了这条规则所属频道 |
| 仍是脚本机器人或人工客服 | 检查规则中的 AI Agent、脚本机器人和启用条件；结束旧会话再测 |
| 能聊天但不会查商品、加购 | 给实际网站 Agent 添加 `Website Cart Ordering`，核对 Topic 中两个工具是否存在 |
| DeepSeek 下拉框为空或调用失败 | 在 AI 设置保存 Key、检查模型目录同步状态及网络；详见 [DeepSeek README](../ai_deepseek/README.md) |
| 找不到商品或有多个候选 | 检查发布、网站、可销售、规格和翻译；使用真实 SKU，按候选补齐属性 |
| `The current website does not allow ecommerce access` | 检查商城访问策略和当前匿名/Portal 身份，按策略登录后重试 |
| AI 说已加购，但购物车没有变化 | 核对工具实际结果；使用同一网站、同一浏览器 session，避免旧会话或其他数据库 |
| 加购数量翻倍 | 确认是否重复发送或模型重复调用了成功批次；当前没有跨请求去重 |
| Portal 调用草稿报价被拒绝 | 网站 Agent 应关联购物车 Topic；内部报价工具要求实际销售权限 |
| 更新代码后仍是旧提示词/依赖 | Python 重启加载；工具/Topic XML 和 `depends` 变更需升级模块 |

## 8. 开发、升级与验证

| 文件 | 阅读重点 |
| --- | --- |
| [models/ai_agent.py](models/ai_agent.py) | 三个业务入口、商品匹配、网站请求上下文和批量回滚 |
| [data/ai_sale_order_tool_data.xml](data/ai_sale_order_tool_data.xml) | 工具描述、参数 Schema、固定 Python 调用和 Topic 指令 |
| [tests/test_ai_website_cart.py](tests/test_ai_website_cart.py) | 商品范围、变体、数量、失败回滚、双语查询和搜索只读性 |
| [docs/README.md](docs/README.md) | 完整开发说明、客户讲稿、PPT 和 DeepSeek 专题入口 |

工具和 Topic XML 未使用 `noupdate`，模块升级会重新加载其中定义的字段。若在数据库中调整了这些 Topic 或工具，升级前记录自定义差异；长期客户化建议通过独立扩展或独立 Topic 维护，避免升级覆盖手工修改。

2026-11-16 的验证记录：本模块 **14 项网站购物车回归**与 `ai_deepseek` 的 **40 项协议及目录测试**合计 **54 项通过**。测试数据和测试期间的语言调整均回滚。旧 `deepseek-chat` 标识曾完成单商品及三商品批量真实加购，测试写入已回滚。

动态目录版本已真实获取 `deepseek-flash`、`deepseek-v4-pro`，并验证 Flash 文本请求；新型号尚未完成完整网站购物场景验收。更换模型后应重新验证工具选择、参数、歧义追问和连续对话，不应仅根据 `/models` 返回即承诺业务效果。

测试应在独立测试数据库执行，安装本模块后使用 `--test-tags /ai_sale_order_2nd`。当前用例使用 `MockRequest`，普通测试启动需要测试 HTTP 服务；不要直接复制安装命令中的 `--no-http`。经验证的无 HTTP shell 测试封装会显式 mock `HttpCase.http_port()`，细节见 [开发技术参考](docs/developer_reference_zh.md)。

上线前至少用目标网站和实际身份验证：普通文本回复、唯一商品加购、变体歧义追问、无效商品、失败批次不残留、已有购物车增量及同会话结账。匿名/仅登录商城、复杂配置商品、多公司和跨域嵌入按实际需求另外验收。

完整资料：[说明文档](docs/odoo19_ai_development_guide_zh.md) · [技术参考](docs/developer_reference_zh.md) · [会议指南](docs/meeting_guide_zh.md) · [DeepSeek 专题](docs/deepseek_integration_zh.md)。
