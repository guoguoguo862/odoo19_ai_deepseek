# AI DeepSeek Provider — Odoo 19

为 Odoo AI Agent 接入 DeepSeek，支持自动发现模型、文本对话和业务工具调用。通过独立二开模块继承 Odoo AI 框架，无需修改企业版核心源码。

| 项目 | 内容 |
| --- | --- |
| 技术名称 | `ai_deepseek` |
| 应用名称 | AI DeepSeek Provider |
| 模块版本 | `19.0.1.1.0` |
| 适用版本 | Odoo 19，具备匹配的企业版 AI 模块 |
| 直接依赖 | `ai_app`，由其递归加载 `ai` 等基础模块 |
| 作者 / 许可证 | Suto / LGPL-3；Odoo 企业版依赖仍遵循其自身授权 |
| 文档更新 | 2026-11-16 |

## 1. 两个模块如何分工

| 模块 | 负责什么 | 使用场景 |
| --- | --- | --- |
| `ai_deepseek` | DeepSeek Key、模型目录、API 协议及工具结果回传 | 需要用 DeepSeek 的 AI Agent |
| [ai_sale_order_2nd](../ai_sale_order_2nd/README.md) | 网站商品查询、规格匹配、购物车更新和内部草稿报价工具 | 聊天购物、内部草稿报价 |
| Odoo 原生网站 / Live Chat 集成 | 网页入口、客服频道、访客会话、AI Agent 绑定 | 网站客服 |

两个二开模块互不依赖。只做 DeepSeek 文字客服时，安装本模块和原生网站客服集成即可；要使用查询商品和加购功能，再安装 `ai_sale_order_2nd`。购物模块已在 `depends` 中声明商城及网站 AI 客服依赖。

安装本模块后，需要配置 Key、选择 Agent 模型，并为实际入口绑定 Agent。模块不会自动创建客户凭据、切换已有 Agent、关联业务 Topic 或配置网站频道。

## 2. 安装前准备

- 准备匹配的 Odoo 19 标准模块、企业版模块和本模块源码，确保所在目录已加入 `addons_path`。
- 使用可部署 Python 二开模块的 Odoo 环境，以及能安装应用和修改 AI 设置的管理员账号。
- Odoo 服务端能够通过 HTTPS 访问 `api.deepseek.com`，并持有可用的 DeepSeek API Key。
- PostgreSQL 已安装与其版本匹配的 pgvector，且目标 Odoo 数据库已启用 `vector`。

### 新数据库的 pgvector 初始化

原生 `ai` 模块安装 hook 执行 `CREATE EXTENSION IF NOT EXISTS vector`，其模型还会创建向量字段与索引。因此，即使本扩展当前不支持知识库，安装 AI 基础模块仍需准备 pgvector。

由 PostgreSQL 管理员连接**实际安装 Odoo 的数据库**，例如在 pgAdmin 中选中目标库后打开 Query Tool，执行：

```sql
-- 先确认这里是目标 Odoo 库，而不是 postgres 管理库。
SELECT current_database(), current_user;

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

SELECT e.extname, e.extversion, n.nspname AS schema
FROM pg_extension e
JOIN pg_namespace n ON n.oid = e.extnamespace
WHERE e.extname = 'vector';
```

结果应包含 `vector`，schema 为 `public`。扩展按数据库启用，新建另一个 Odoo 数据库时要再次初始化。若提示扩展文件不存在，先在 PostgreSQL 服务器安装 pgvector；若提示只有超级用户能创建扩展，使用 PostgreSQL 管理员执行上述 SQL。Odoo 业务账号无需因此长期获得超级用户权限。

## 3. 安装与升级

### 后台操作

1. 将 `ai_deepseek` 放入配置的附加模块目录，重启 Odoo 加载代码。
2. 开启开发者模式，在应用中更新应用列表。
3. 搜索技术名称 `ai_deepseek` 或应用名称 **AI DeepSeek Provider**；若找不到，移除默认的“应用”筛选。本模块 `application=False`。
4. 新环境点击安装，旧环境点击升级。

命令行也可执行。以下从包含 `odoo-bin` 的目录运行，`python` 应指向该环境的 Python；将 `odoo.conf` 和 `target_db` 替换为实际配置路径及**单个**目标数据库。先停止正在使用该数据库的 Odoo 服务，完成后按原启动方式恢复服务：

```text
# 首次安装
python odoo-bin -c odoo.conf -d target_db -i ai_deepseek --stop-after-init --no-http --max-cron-threads=0

# 升级已有模块
python odoo-bin -c odoo.conf -d target_db -u ai_deepseek --stop-after-init --no-http --max-cron-threads=0
```

从 `19.0.1.0.0` 升级到本版时，迁移脚本会尝试同步一次模型目录。已有 Key 和 Agent 模型保留；没有 Key 或网络暂时失败不会使目录同步阻塞模块安装、升级。

## 4. 配置 Key、同步模型并选择 Agent

1. 进入 **AI → Configuration → Settings → Providers**。中文翻译可能显示为“AI → 配置 → 设置 → 服务提供商”。
2. 开启 **Use your own DeepSeek account**，填写 DeepSeek API Key，保存设置。
3. 查看模型同步状态、可用文本模型数量及最后成功同步时间。也可点击 **Save Key and Refresh Models（保存 Key 并刷新模型）**。
4. 进入 **AI → Agents**，创建或打开目标 Agent，从模型下拉框中选择同步返回的 DeepSeek 型号。
5. 配置角色与回答范围，按业务需要添加 Topics，然后保存。当前 DeepSeek Agent 不应添加 Sources，也不要启用依赖资料来源的问答配置。

刷新按钮会将输入框中的 Key 保存到数据库后立即请求模型目录，即使之前尚未点击全局“保存”。它不代替保存其他设置项。同步后重新打开 Agent 表单，确保前端重新读取下拉选项。

### 凭据和缓存位置

| 配置 | 作用 |
| --- | --- |
| `ai.deepseek_key` | 当前数据库的 API Key，读取时优先使用 |
| `ODOO_AI_DEEPSEEK_TOKEN` | 数据库未配置 Key 时，回退到 Odoo 服务进程的环境变量 |
| `ai.deepseek_models` | 自动维护的目录 JSON，包括当前型号、历史 ID、时间和状态；不含 Key |

Key 字段和手动同步仅管理员可访问，界面掩码显示。使用环境变量时，变量必须属于实际运行 Odoo 的服务进程；只在另一个终端设置不会改变已运行服务的环境。需要立即读取环境变量中的 Key 时，可以在数据库 Key 为空的情况下点击刷新按钮。

系统参数和模型目录按数据库保存。配置某个数据库不会给另一个数据库设置 Key；共用一个服务进程的数据库则可能读取相同的环境变量回退值。

## 5. 自动模型目录的行为

模型发现请求为 `GET https://api.deepseek.com/v1/models`，使用服务端 Key 鉴权，超时为 10 秒。API 返回的 `id` 用于真实请求，`name` 用于显示；缺少显示名时使用 ID，必要时增加 DeepSeek 显示前缀。

| 触发时机 | 行为 |
| --- | --- |
| 首次安装 | 尝试同步一次；没有 Key 时提示待配置 |
| 从旧版升级到 `19.0.1.1.0` | 迁移脚本尝试同步一次 |
| 保存设置 | Key 改变或尚无成功同步记录时尝试同步 |
| 手动刷新 | 保存输入框 Key，立即同步并提示结果 |
| 每日定时任务 | 自动更新当前数据库目录 |
| 打开 Agent 下拉框、正常对话 | 只读缓存，不额外请求 `/models` |

定时任务名称为 **DeepSeek: Refresh available models**。开发者模式下可在“设置 → 技术 → 自动化 → 计划任务”查看。每日刷新需要该任务保持启用、Odoo 定时任务正常运行；长期以 `--max-cron-threads=0` 运行服务时不会自动执行。

同步会整批校验响应，拒绝空目录、重复或无效 ID、与原生 Provider 冲突的 ID；显式不支持文本输入或输出的模型会被过滤。能力字段缺省的型号可以进入目录，是否满足具体业务仍需实测。

缺 Key、超时、鉴权失败或目录格式错误时，保留上次成功目录和时间，并显示同步状态。新库尚未同步成功时不会固定添加旧 Chat / Reasoner 选项。

API 不再返回的型号如果仍被现有或归档 Agent 使用，会保留显示并标注 **not in current catalog**。这用于查看和迁移旧配置，不保证供应商继续接受该 ID；同步不会自动替换 Agent 的模型。历史 `deepseek-chat` / `deepseek-reasoner` 仅保留兼容识别，若供应商实际返回它们，也会作为当前目录项出现。

2026-11-16 的真实 `/models` 验证返回：

| API ID | 当时返回的显示名称 |
| --- | --- |
| `deepseek-flash` | `DeepSeek-V4.1-Flash` |
| `deepseek-v4-pro` | `DeepSeek-V4-Pro` |

该表是验证记录，实际列表以当前账号的 API 返回为准。模型发现成功、文本调用成功、业务流程通过是不同层次的验证。

## 6. 启用网站在线客服

### 右下角聊天框

准备 `website`、`im_livechat`、`website_livechat`、`ai_livechat` 等原生模块。安装购物模块时会由其依赖自动带入；单独安装本模块只会带入 AI 基础模块。

1. 在 **AI → Agents** 中准备非系统 Agent，选择已同步的 DeepSeek 型号。
2. 打开 **在线客服 / Live Chat**，创建或选择频道，例如 `Support`，进入 **Rules / 规则**。
3. 按下表配置一条 AI 接待规则并保存。
4. 进入 **网站 → 配置 → 设置**，选中目标网站，在 **Livechat / 在线客服** 的 **Channel / 频道** 中选择同一个频道，保存。
5. 退出网站编辑模式，刷新前台，结束旧聊天并新开会话测试。多网站应分别选择频道。

| 规则字段 | 示例配置 |
| --- | --- |
| Live Chat Button | `Show`，或需要自动弹出时选 `Open automatically` |
| AI Agent | 上一步已配置的 DeepSeek Agent |
| Scripted Bot | 清空，使用 AI 接待该规则 |
| Enable ChatBot | `Always`，不受人工坐席是否在线限制 |
| URL Regex | 留空覆盖所有页面；只覆盖商城时可填写 `/shop` |
| Countries | 留空表示不按国家限制 |
| Matching order | 能识别访客国家时，匹配的国家专属规则先于通用规则；同组中数字较小的规则优先 |

正确关系为：**目标网站 → 客服频道 → 匹配当前 URL 的规则 → DeepSeek Agent**。频道存在 AI 规则且启用条件为 `Always` 时，无需人工客服保持在线。`/im_livechat/` 只覆盖相关路径，不会自动覆盖首页或商城。

### 页面内的 AI 聊天区块

使用原生 `ai_website_livechat` 模块。在网站编辑器中添加 **AI / AI Livechat** 区块，在区块选项中选择 AI Agent，并按需要设置客服频道，保存并发布页面。区块中的 Agent 选择与右下角聊天框的频道规则应分别核对。

### 同时启用聊天购物

安装 [ai_sale_order_2nd](../ai_sale_order_2nd/README.md)，在上述网站 Agent 的 Topics 中添加 **Website Cart Ordering**。文本客服不要求该 Topic；缺少它时，Agent 没有本模块的商品查询和加购工具。产品准备、购物测试和批量回滚说明见购物模块 README。

## 7. 支持范围和实现边界

| 能力 | 当前实现 |
| --- | --- |
| 文本对话与对话历史 | 支持，复用 Odoo Agent 和原生历史消息 |
| 业务工具调用 | 支持工具定义、整批调用格式校验、执行循环及结果回传 |
| 新模型自动发现 | 支持，使用本地数据库缓存 |
| 普通动态型号的思考模式 | 显式发送 `thinking={"type": "disabled"}` |
| 旧 `deepseek-reasoner` | 保留原协议，工具轮保留 `reasoning_content`，不发送 `temperature` |
| Sources / embedding / RAG | 当前扩展不支持，Agent 和资料关联入口会校验并拒绝 |
| 图片、文件、PDF、音频输入 | 当前扩展不支持 |
| 独立输出 `schema`、联网 `web_grounding` | 当前扩展不支持；工具参数 Schema 正常使用 |
| 系统其他 AI 自动化入口 | 按各入口实现决定，不会全局切换成 DeepSeek |

Flash / Pro 是型号，思考是独立运行参数。原生 Odoo 历史主要重建 `role/content`，没有完整保存跨用户轮的 `reasoning_content`；本版对普通动态型号禁用思考以兼容现有文本和工具链路，尚未提供思考开关。供应商宣称支持的能力不代表本连接器已经接入。

工具执行权限取决于实际业务工具。模型只请求已提供的工具；是否 `sudo()`、可读取哪些记录、是否允许写入，应按具体业务模块核对。输出语言由 Agent/Topic 指令引导，仍可能出现英文过程文字。

## 8. 常见问题

| 现象 | 排查与处理 |
| --- | --- |
| 安装时报创建 `vector` 权限不足 | 由 PostgreSQL 管理员在目标数据库执行第 2 节 SQL，再重试安装 |
| 应用列表找不到模块 | 检查 `addons_path`、重启代码、更新应用列表，并移除“应用”筛选 |
| 没有 DeepSeek 模型选项 | 确认本数据库已安装模块、已保存 Key、同步状态成功；再重新打开 Agent 表单 |
| 保存 Key 后列表仍旧 | 检查同步状态及时间；点击手动刷新。系统参数页面直接改 Key 不会触发设置页保存逻辑 |
| 每天没有更新 | 检查计划任务是否启用、Odoo cron 是否运行；可先手动刷新验证网络 |
| 看到 Chat / Reasoner 且标记不在目录 | 有已有 Agent 使用旧 ID；选择当前目录型号并单独验证后再迁移 |
| 模型已同步但文本报错 | 目录查询不代表对话可用；检查模型调用日志、账号额度、请求参数及 API 连通性 |
| 后台可对话，网页没回复 | 核对目标网站频道、规则的 Agent、URL、国家和启用条件；新开聊天会话 |
| 能回复但不能查商品或加购 | 安装购物模块并给实际网站 Agent 添加 `Website Cart Ordering` |
| 添加 Sources 被拒绝 | 当前适配不支持知识来源；改用已支持该能力的 Provider 或另行开发检索组合 |

新型号验收建议依次执行：普通文本 → 带工具的对话 → 连续两轮对话 → 目标网站和身份下的实际业务检查。客服回复“已完成”后，还需核对真实业务结果。

## 9. 开发入口、升级与卸载

| 文件 | 作用 |
| --- | --- |
| [__manifest__.py](__manifest__.py) | 模块依赖、版本、视图、计划任务和安装/卸载 hook |
| [models/ai_agent.py](models/ai_agent.py) | 动态 Selection、模型值校验、Provider 路由及 Sources 限制 |
| [services/model_catalog.py](services/model_catalog.py) | 每数据库目录缓存、刷新状态及已用旧 ID 兼容 |
| [services/deepseek_api_service.py](services/deepseek_api_service.py) | `/models`、Chat Completions、工具调用解析和结果回传 |
| [models/res_config_settings.py](models/res_config_settings.py) / [设置视图](views/res_config_settings_views.xml) | 管理员 Key 设置、同步按钮及状态 |
| [models/ai_agent_source.py](models/ai_agent_source.py) | 资料直接创建、重新关联等入口的限制 |
| [每日任务](data/ir_cron.xml) / [升级脚本](migrations/19.0.1.1.0/post-migrate.py) | 自动刷新及旧版升级同步 |
| [hooks.py](hooks.py) | 安装同步；卸载时恢复核心默认型号 |
| [协议测试](tests/test_deepseek.py) / [目录测试](tests/test_model_catalog.py) | 协议、缓存、兼容、权限和卸载回归 |

动态 Selection 通过 `selection="_get_llm_model_selection"` 绑定可继承方法；Odoo 19 的原字段采用函数对象，不能直接使用 `selection_add`。仅 DeepSeek Agent 使用独立 `LLMApiService` 子类，其他 Provider 继续 `super()`。没有修改进程级 `PROVIDERS` 或替换核心类。

升级 Python 代码需重新加载服务；字段、视图、计划任务或迁移变更还需升级模块。Key、Agent 模型和网站频道属于数据库运行配置，保存后对新请求生效；模型目录同步后重新打开表单读取新选项。

卸载本模块会将包含归档记录在内的 DeepSeek Agent 切回核心默认 `gpt-4o`，保留 Agent、Topic、消息及客户 Key。回退后需要可用的 OpenAI 凭据才能继续调用；重新安装不会自动将这些 Agent 切回 DeepSeek。若要删除 Key，应由管理员单独处理。

## 10. 验证记录与更多资料

截至 2026-11-16，`19.0.1.1.0` 在升级后的 Odoo 19 注册表中完成以下验证：

- 19 项原适配测试、21 项自动目录测试、14 项购物车测试，合计 **54 项通过，0 失败、0 错误**。自动化模型请求使用模拟响应，事务测试回滚测试数据。
- 真实 `/models` 返回 Flash、Pro 两个型号；`deepseek-flash` 非思考模式真实文本请求成功。
- 2026-11-10 使用旧 `deepseek-chat` 标识完成过 Portal 身份的单品和三商品批量加购验证，测试写入已回滚。
- 截至上述验证记录，Flash / Pro 的完整网站购物场景尚未单独验收，不能由目录查询成功推导其业务效果。

原企业版 DeepSeek 补丁已于 2026-11-10 拆出；新部署只需安装本模块，不需要修改 `ai/utils/llm_api_service.py` 或 `llm_providers.py`。

更多资料见 [购物模块 README](../ai_sale_order_2nd/README.md)、[开发与会议资料索引](../ai_sale_order_2nd/docs/README.md)、[DeepSeek 开发专题](../ai_sale_order_2nd/docs/deepseek_integration_zh.md)。DeepSeek 官方资料：[模型目录接口](https://api-docs.deepseek.com/api/list-models/) / [思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)。
