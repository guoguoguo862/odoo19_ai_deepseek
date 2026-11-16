# Odoo 19 AI 开发说明与客户会议资料

编制：Suto · 版本：1.3 · 日期：2026-11-16。内容依据匹配版本的 Odoo 19 企业版、独立 `ai_deepseek` 及 `ai_sale_order_2nd` 源码。

此目录保留可维护的文档源文件和图示。PDF、Word、PowerPoint、生成的 HTML 与 ZIP 不纳入 Git，可在本地按下方说明生成；原始源文件可以直接在 GitHub 阅读。

| 资料 | 用途 | 源文件 |
| --- | --- | --- |
| 功能说明 | 理解业务、平台原理和部署边界 | [完整说明](odoo19_ai_development_guide_zh.md) |
| 开发技术参考 | 调用链、Schema、权限、RAG、事务、测试与排障 | [技术附录](developer_reference_zh.md) |
| DeepSeek 接入专题 | 模型目录、协议、工具调用、继承实现与交付 | [DeepSeek 专题](deepseek_integration_zh.md) |
| 客户会议讲稿 | 会前准备、演示步骤和客户问答 | [会议指南](meeting_guide_zh.md) |
| 幻灯片内容与备注 | 生成 15 页客户会议演示 | [幻灯片 JSON](meeting_slides_zh.json) |
| 架构与流程图 | 系统分工、适配链路、购物流程 | [系统架构](assets/ai_architecture.svg) · [DeepSeek 适配](assets/deepseek_adapter.svg) · [购物流程](assets/ordering_flow.svg) |

文中的 Odoo 企业版和社区版源码路径是外部参考，需在单独准备的匹配版本、已授权源码中查阅。本仓库内模块之间的链接可以直接打开。

当前网站工具查询真实商品、明确规格并加入当前访客购物车，由客户核对结账；没有订单确认、开票或付款工具。DeepSeek 适配支持文本与工具，不支持 Sources/RAG。历史测试记录不代替客户环境验收，新同步的模型应验证文本、工具选择、连续对话和实际业务结果。

## 本地生成 PDF、Word 和 PPT

在独立工具虚拟环境中安装文档依赖，避免改变 Odoo 的运行环境。生成器目前使用 Windows 的 Microsoft YaHei 字体，并需要已安装的 Chromium 浏览器。Linux/macOS 使用者须调整字体路径及浏览器参数。

以下在仓库根目录执行，`python` 指向工具虚拟环境：

```powershell
python -m pip install markdown2 python-docx python-pptx beautifulsoup4 Pillow PyMuPDF
python -X utf8 ai_sale_order_2nd/docs/build_documents.py --browser 'C:\Program Files\Google\Chrome\Application\chrome.exe' --temp .build/docs
```

也可使用 `--packages` 指定已经准备好的独立 Python 依赖目录。构建默认临时目录为仓库下的 `.build/docs`，不进入 Git。

生成器会在本目录输出 Word、PDF、PPT、HTML 和 `odoo19_ai_documentation_zh.zip`。生成完成后，在浏览器打开本地的 `index.html`，可进入各格式文档和幻灯片。GitHub 不会执行这段构建过程；未生成时，HTML 资料页中的下载项尚不可用。

脚本只生成文档，不安装模块或写入业务数据库。重新生成前应核对说明与实际代码范围，生成后检查中文字体和分页。
