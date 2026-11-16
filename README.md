# Odoo 19 AI：DeepSeek 接入与网站购物助手

两个独立 Odoo 19 二开模块，为原生 AI Agent 接入 DeepSeek，并提供网站商品查询、购物车加购及内部草稿报价工具。通过模块继承扩展，无需修改 Odoo 企业版核心源码。

| 模块 | 当前版本 | 功能 | 使用说明 |
| --- | --- | --- | --- |
| `ai_deepseek` | `19.0.1.1.0` | DeepSeek Key 配置、自动同步模型目录、文本对话、业务工具调用 | [DeepSeek README](ai_deepseek/README.md) |
| `ai_sale_order_2nd` | `19.0.1.0.0` | 查询网站真实商品、确认规格、批量加入当前访客购物车、创建内部草稿报价 | [购物助手 README](ai_sale_order_2nd/README.md) |

两个模块互不依赖。购物助手也可以配合其他已支持工具调用的模型；同时安装两者即可组合 DeepSeek 和购物业务能力，之后仍需配置凭据、Agent、Topic 和网站入口。

## 环境要求

- Odoo **19.0**，具备匹配版本、合法授权的企业版 AI 模块源码，且可部署 Python 二开模块。
- PostgreSQL 已安装 pgvector，并在实际目标数据库启用 `vector` 扩展；首次安装时由数据库管理员执行 `CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;`。
- 使用 DeepSeek 时，Odoo 服务器可以访问 `api.deepseek.com`，并持有可用的客户 API Key。
- 本仓库不包含 Odoo 企业版源码。依赖声明会让 Odoo 安装已有模块，不会下载企业版源码或自动创建模型凭据。

`ai_deepseek` 直接依赖 `ai_app`；购物助手直接依赖 `ai_app`、`sale`、`website_sale`、`website_livechat`、`ai_livechat`、`ai_website_livechat`。Odoo 会递归加载下层依赖。

## 安装

```bash
git clone --branch 19.0 https://github.com/guoguoguo862/odoo19_ai_deepseek.git
```

把**克隆后的仓库根目录**加入 Odoo 配置的 `addons_path`，保留原有标准模块和企业版模块路径。例如：

```ini
[options]
addons_path = /path/to/odoo/addons,/path/to/enterprise,/path/to/odoo19_ai_deepseek
```

重启 Odoo、开启开发者模式、更新应用列表，然后搜索并安装两个模块。本仓库模块均为 `application=False`，搜索时可能需要移除默认的“应用 / Apps”筛选。

命令行安装示例（所有路径和数据库名均需替换）：

```text
python /path/to/odoo/odoo-bin -c /path/to/odoo.conf -d target_db -i ai_deepseek,ai_sale_order_2nd --stop-after-init --no-http --max-cron-threads=0
```

使用与 Odoo 服务相同的 Python 环境。安装、升级前停止使用该数据库的正常 Odoo 服务，命令结束后恢复正常服务；不要将安装命令中的 `--max-cron-threads=0` 用作日常运行配置，否则模型目录不会每日自动刷新。

## 启用网页客服与聊天购物

1. 在 **AI → Configuration → Settings → Providers** 中填写 DeepSeek Key，保存并刷新模型目录。
2. 在 **AI → Agents** 中选择实际同步返回的 DeepSeek 模型，配置客服角色和回答范围。
3. 在该 Agent 的 **Topics** 中添加 **Website Cart Ordering**，启用商品查询和加购工具。
4. 在在线客服频道的规则中选择该 Agent；使用 AI 接待时清空 Scripted Bot，将启用条件设为 `Always`，按需求配置 URL 范围。
5. 在目标网站设置中绑定同一个客服频道，退出网站编辑模式并新开聊天会话。
6. 使用真实已发布商品名或 SKU 测试加购，在同一浏览器会话打开 `/shop/cart` 核对结果。

网页聊天界面由 Odoo 原生模块提供。右下角客服与页面内 AI 聊天区块的具体配置、规则优先级和排障步骤见两个模块的 README。

## 当前范围

- DeepSeek 适配支持文本和工具调用；当前不支持 Sources / RAG、图片、文件或音频输入。
- 模型列表通过 DeepSeek `/models` 自动同步并缓存，界面展示实际 API 返回的型号，不固定承诺某个产品名称。
- 网站工具按增量添加购物车，客户继续使用标准结账流程；当前没有自动确认订单、开票或付款工具。
- 同一次批量加购发生异常时回滚；成功批次重复调用仍可能重复加量，目前没有跨请求持久化去重。
- 本仓库面向 Odoo 19。Odoo 20 的 Agent、Skill、会话和服务接口已有变化，不能只修改版本号后直接安装。

## 文档与验证

完整说明、开发参考、DeepSeek 专题和客户会议材料源文件见 [文档索引](ai_sale_order_2nd/docs/README.md)。仓库保留 Markdown、JSON、构建脚本和图示，PDF、Word、PPT 等可按文档说明在本地生成。

历史验证记录（2026-11-16）：19 项适配测试、21 项模型目录测试、14 项购物车回归测试，合计 **54 项通过**。真实模型目录查询及 Flash 文本请求已验证；旧模型标识下做过真实加购验证并回滚。Flash / Pro 的完整网页购物场景尚需单独验收。本次仓库整理不等于重新执行这些业务测试。

问题反馈：[GitHub Issues](https://github.com/guoguoguo862/odoo19_ai_deepseek/issues)。提交问题时请移除 API Key、数据库密码和客户数据。

## 许可证

模块作者：Suto。两个模块按 manifest 声明使用 **LGPL-3**，许可证正文见 [LICENSE](LICENSE)，其引用的 GPL v3 正文见 [COPYING](COPYING)。Odoo 企业版依赖遵循自身授权，不包含在本仓库中。
