"""Build the Chinese AI documentation and presentation from local sources.

Dependencies: markdown2, python-docx, python-pptx, Pillow, PyMuPDF,
BeautifulSoup, plus a Chromium browser for the PDF export. Install build
dependencies separately; this script does not modify the Odoo environment.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import zipfile
from xml.sax.saxutils import escape


parser = argparse.ArgumentParser()
parser.add_argument("--packages", type=Path)
parser.add_argument("--browser", type=Path, default=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"))
parser.add_argument("--temp", type=Path, default=Path(__file__).resolve().parents[2] / ".build/docs")
args = parser.parse_args()
if args.packages:
    sys.path.insert(0, str(args.packages.resolve()))

import markdown2
from bs4 import BeautifulSoup
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor as PptColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt as PptPt
import pymupdf


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)
args.temp.mkdir(parents=True, exist_ok=True)
NAVY = "16324F"
TEAL = "087F8C"
GOLD = "E5A33A"
FONT_FILE = r"C:\Windows\Fonts\msyh.ttc"


def make_diagram(name, boxes, arrows, title, subtitle, width=1400, height=630):
    """Use identical SVG and Pillow coordinates, giving Word a PNG fallback."""
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0 0 L9 4.5 L0 9" fill="#7890a2"/></marker></defs>',
           '<rect width="100%" height="100%" fill="#f4f8fb"/>']
    bitmap = Image.new("RGB", (width, height), "#f4f8fb")
    draw = ImageDraw.Draw(bitmap)

    def label(x, y, content, size=24, color=NAVY):
        svg.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="{size}" fill="#{color}">{escape(content)}</text>')
        font = ImageFont.truetype(FONT_FILE, size)
        draw.text((x, y - size), content, font=font, fill=f"#{color}", anchor="mt")

    label(width // 2, 48, title, 30)
    label(width // 2, 84, subtitle, 20, "587184")
    for x1, y1, x2, y2 in arrows:
        svg.append(f'<path d="M{x1},{y1} L{x2},{y2}" fill="none" stroke="#7890a2" stroke-width="3" marker-end="url(#arrow)"/>')
        draw.line((x1, y1, x2, y2), fill="#7890a2", width=3)
        angle = math.atan2(y2 - y1, x2 - x1)
        draw.polygon([(x2, y2),
                      (x2 - 12 * math.cos(angle) + 6 * math.sin(angle), y2 - 12 * math.sin(angle) - 6 * math.cos(angle)),
                      (x2 - 12 * math.cos(angle) - 6 * math.sin(angle), y2 - 12 * math.sin(angle) + 6 * math.cos(angle))], fill="#7890a2")
    for box in boxes:
        x, y, w, h, heading, lines, color = box
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="white" stroke="#{color}" stroke-width="2"/>')
        draw.rounded_rectangle((x, y, x + w, y + h), radius=16, fill="white", outline=f"#{color}", width=2)
        label(x + w // 2, y + 43, heading, 25, color)
        for j, line in enumerate(lines):
            label(x + w // 2, y + 82 + j * 31, line, 20)
    svg.append("</svg>")
    (ASSETS / f"{name}.svg").write_text("\n".join(svg), encoding="utf-8")
    bitmap.save(ASSETS / f"{name}.png")


make_diagram("ai_architecture", [
    (35, 170, 260, 180, "网站聊天入口", ["客户描述需求", "同一网站 / 浏览器会话"], NAVY),
    (350, 170, 300, 180, "Odoo AI Agent", ["角色 + Topics + 历史", "工具定义与调用循环"], TEAL),
    (720, 170, 300, 180, "语言模型服务", ["理解商品、规格、数量", "返回工具名和参数"], TEAL),
    (350, 430, 300, 150, "受控业务工具", ["查目录 / 校验 / 加购"], NAVY),
    (720, 430, 300, 150, "Odoo 业务系统", ["商品 / 购物车 / 计价"], NAVY),
    (1080, 430, 280, 150, "客户核对结账", ["数量 / 地址 / 配送 / 付款"], "AA7217"),
], [(295, 260, 350, 260), (650, 260, 720, 260), (500, 350, 500, 430),
    (650, 505, 720, 505), (1020, 505, 1080, 505)],
    "Odoo AI：理解、工具与业务系统的分工", "当前下单模块复用平台聊天与商城能力；模型请求动作，Odoo 执行并返回真实结果")

make_diagram("ordering_flow", [
    (35, 160, 280, 155, "01  表达需求", ["一个黑色抽屉", "保留商品与数量 1"], NAVY),
    (375, 160, 280, 155, "02  查询真实目录", ["已发布 / 可售 / 当前网站", "返回 SKU 和实际规格"], TEAL),
    (715, 160, 280, 155, "03  判断具体商品", ["唯一 → 继续", "有歧义 → 询问缺少规格"], TEAL),
    (1055, 160, 310, 155, "04  校验并执行加购", ["整批预校验 + savepoint", "返回实际增加数量"], NAVY),
    (715, 420, 280, 155, "客户补充规格", ["基于真实候选回答", "再确认匹配是否唯一"], "AA7217"),
    (1055, 420, 310, 155, "05  核对并结账", ["打开 /shop/cart", "使用标准网站结账流程"], "AA7217"),
], [(315, 235, 375, 235), (655, 235, 715, 235), (995, 235, 1055, 235),
    (855, 315, 855, 420), (1210, 315, 1210, 420)],
    "从一句需求到真实购物车", "AI 负责理解与选择下一步；业务成功以工具结果和购物车实际数据为准")

make_diagram("deepseek_adapter", [
    (60, 150, 560, 165, "01  Odoo Agent 组织输入", ["用户问题 / Topics / 历史 / 工具 Schema", "所选模型映射到 deepseek Provider"], NAVY),
    (780, 150, 560, 165, "02  适配层转换请求", ["messages + tools + tool_choice", "API 地址与服务端 Key 鉴权"], TEAL),
    (780, 380, 560, 165, "03  DeepSeek API", ["POST /chat/completions", "返回自然语言或 tool_calls"], TEAL),
    (60, 380, 560, 165, "04  解析并交给统一执行循环", ["工具名 / tool_call_id / JSON 参数", "使用已提供工具列表与业务校验"], NAVY),
    (60, 610, 560, 165, "05  Suto 商品业务工具", ["查询真实目录 / 明确商品 / 执行加购", "保留网站范围、数量校验和失败回滚"], NAVY),
    (780, 610, 560, 165, "06  回填实际工具结果", ["role: tool + tool_call_id + content", "交回模型，继续执行或生成最终回复"], "AA7217"),
], [(620, 232, 780, 232), (1060, 315, 1060, 380),
    (780, 462, 620, 462), (340, 545, 340, 610),
    (620, 692, 780, 692), (1280, 610, 1280, 545)],
    "DeepSeek 适配：模型接口与 Odoo 业务工具的连接", "模型适配由独立模块 ai_deepseek 提供；业务工具由 ai_sale_order_2nd 提供", height=820)


CSS = """
@page { size:A4; margin:18mm 17mm 19mm; }
* { box-sizing:border-box; }
body { margin:0; color:#21354a; background:#edf2f6; font-family:'Microsoft YaHei','Noto Sans CJK SC',sans-serif; font-size:10.5pt; line-height:1.75; }
main { max-width:1050px; margin:28px auto; padding:46px 56px; background:white; }
h1 { color:#16324f; font-size:27pt; line-height:1.35; margin:0 0 24px; }
h2 { color:#087f8c; font-size:17pt; margin:32px 0 14px; padding-bottom:7px; border-bottom:1px solid #bcd8dd; break-after:avoid; }
h3 { color:#16324f; font-size:12.3pt; margin:23px 0 10px; break-after:avoid; }
p { margin:10px 0; widows:3; orphans:3; }
table { width:100%; border-collapse:collapse; margin:16px 0; font-size:9pt; }
thead { display:table-header-group; }
th { background:#e7f1f4; color:#16324f; text-align:left; }
td,th { border:1px solid #cbd8e2; padding:8px 10px; overflow-wrap:anywhere; }
tr { break-inside:avoid; }
blockquote { margin:18px 0; padding:12px 18px; border-left:4px solid #087f8c; background:#edf6f7; }
pre { background:#f2f5f8; padding:13px; border:1px solid #d9e2e9; white-space:pre-wrap; overflow-wrap:anywhere; font:8.3pt/1.6 Consolas,'Microsoft YaHei',monospace; }
code { font-family:Consolas,'Microsoft YaHei',monospace; font-size:.92em; }
img { width:100%; height:auto; break-inside:avoid; }
a { color:#087f8c; text-decoration:none; overflow-wrap:anywhere; }
li { margin:5px 0; }
.book-section { break-before:page; }
.screen-nav { max-width:1050px; margin:20px auto; font-size:10pt; color:#587184; }
.screen-nav a { margin-right:22px; }
.doc-meta { color:#587184; font-size:9pt; margin-bottom:24px; }
@media print { body { background:white; font-size:10pt; } main { margin:0; padding:0; max-width:none; } .screen-nav { display:none; } h2 { margin-top:22px; } a { color:inherit; } }
"""


def markdown_html(path):
    return str(markdown2.markdown(path.read_text(encoding="utf-8"), extras=["tables", "fenced-code-blocks", "strike", "cuddled-lists", "header-ids"]))


def write_html(name, title, sections):
    content = []
    for index, section in enumerate(sections):
        content.append(f'<section class="{"book-section" if index else ""}">{markdown_html(section)}</section>')
    text = f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(title)}</title><meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body><nav class="screen-nav"><a href="index.html">资料入口</a><a href="odoo19_ai_development_guide_zh.html">完整文档</a><a href="meeting_guide_zh.html">会议讲稿</a></nav><main>{''.join(content)}</main></body></html>'''
    target = ROOT / f"{name}.html"
    target.write_text(text, encoding="utf-8")
    return target


def set_run_font(run, size=None, bold=None, color=None, name="Microsoft YaHei"):
    run.font.name = name
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), name)


def rich_text(paragraph, element, bold=False, mono=False):
    for child in element.children:
        if isinstance(child, str):
            run = paragraph.add_run(str(child))
            set_run_font(run, bold=bold, name="Consolas" if mono else "Microsoft YaHei")
        elif child.name == "br":
            paragraph.add_run().add_break()
        elif child.name in ("strong", "b", "em", "i", "code", "a", "span"):
            rich_text(paragraph, child, bold or child.name in ("strong", "b"), mono or child.name == "code")
        else:
            rich_text(paragraph, child, bold, mono)


def add_markdown(doc, path, first=False):
    soup = BeautifulSoup(markdown_html(path), "html.parser")
    if not first:
        doc.add_page_break()
    for element in soup.children:
        tag = getattr(element, "name", None)
        if not tag:
            continue
        if tag in ("h1", "h2", "h3", "h4"):
            p = doc.add_heading(element.get_text(), level=int(tag[1]))
            p.paragraph_format.keep_with_next = True
        elif tag == "p":
            if element.find("img"):
                for img in element.find_all("img"):
                    image_path = ROOT / img["src"]
                    if image_path.suffix == ".svg":
                        image_path = image_path.with_suffix(".png")
                    doc.add_picture(str(image_path), width=Cm(17))
            else:
                rich_text(doc.add_paragraph(), element)
        elif tag in ("ul", "ol"):
            for item in element.find_all("li", recursive=False):
                p = doc.add_paragraph(style="List Number" if tag == "ol" else "List Bullet")
                rich_text(p, item)
        elif tag == "blockquote":
            p = doc.add_paragraph(style="Quote")
            rich_text(p, element)
        elif tag == "pre":
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(10)
            p.paragraph_format.keep_together = False
            shade = OxmlElement("w:shd")
            shade.set(qn("w:fill"), "F1F5F8")
            p._p.get_or_add_pPr().append(shade)
            run = p.add_run(element.get_text().rstrip())
            set_run_font(run, size=8, name="Consolas")
        elif tag == "table":
            rows = element.find_all("tr")
            if not rows:
                continue
            cols = len(rows[0].find_all(["th", "td"], recursive=False))
            table = doc.add_table(rows=0, cols=cols)
            table.style = "Table Grid"
            for idx, row in enumerate(rows):
                cells = table.add_row().cells
                for cell, source in zip(cells, row.find_all(["th", "td"], recursive=False)):
                    rich_text(cell.paragraphs[0], source, bold=idx == 0)
                    for p in cell.paragraphs:
                        p.paragraph_format.space_after = Pt(3)
                        for run in p.runs:
                            set_run_font(run, size=8.5)
                    if idx == 0:
                        shade = OxmlElement("w:shd")
                        shade.set(qn("w:fill"), "E6F1F4")
                        cell._tc.get_or_add_tcPr().append(shade)
                if idx == 0:
                    table.rows[-1]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
            doc.add_paragraph()


def write_docx(name, sections):
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(1.8)
    section.left_margin = section.right_margin = Cm(1.8)
    normal = doc.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal.font.size = Pt(10)
    normal._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.paragraph_format.line_spacing = 1.35
    normal.paragraph_format.space_after = Pt(7)
    for level, size in [(1, 23), (2, 17), (3, 12), (4, 11)]:
        style = doc.styles[f"Heading {level}"]
        style.font.name = "Microsoft YaHei"
        style._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string(TEAL if level == 2 else NAVY)
    header = section.header.paragraphs[0]
    set_run_font(header.add_run("SUTO  /  ODOO 19 AI 开发与功能说明"), size=8, color="62788A")
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_run_font(footer.add_run("Suto · 2026-11-16    |    "), size=8, color="62788A")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    for idx, source in enumerate(sections):
        add_markdown(doc, source, first=idx == 0)
    doc.core_properties.title = "Odoo 19 AI 功能开发与说明文档"
    doc.core_properties.author = "Suto"
    doc.core_properties.created = datetime(2026, 11, 10)
    target = ROOT / f"{name}.docx"
    doc.save(target)
    return target


def pdf_from_html(source, target):
    profile = args.temp / "chrome-profile"
    result = subprocess.run([
        str(args.browser), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        "--disable-extensions", "--disable-background-networking", "--allow-file-access-from-files",
        f"--user-data-dir={profile}", "--no-pdf-header-footer", f"--print-to-pdf={target}", source.as_uri(),
    ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    if not target.exists():
        raise RuntimeError(f"PDF export failed: {result.stderr[-1200:]}")


def write_pptx():
    source = json.loads((ROOT / "meeting_slides_zh.json").read_text(encoding="utf-8"))
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)

    def rect(slide, x, y, w, h, fill, radius=False):
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                                       Inches(x), Inches(y), Inches(w), Inches(h))
        shape.fill.solid()
        shape.fill.fore_color.rgb = PptColor.from_string(fill)
        shape.line.fill.background()
        return shape

    def text(slide, x, y, w, h, content, size, color=NAVY, bold=False):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = 0
        for i, line in enumerate(content.split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line
            p.font.name = "Microsoft YaHei"
            p.font.size = PptPt(size)
            p.font.bold = bold
            p.font.color.rgb = PptColor.from_string(color)
            p.space_after = PptPt(8)
        return box

    for idx, data in enumerate(source["slides"]):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        rect(slide, 0, 0, 13.333, 7.5, "F3F7FA")
        rect(slide, 0, 0, .19, 7.5, TEAL)
        text(slide, .65, .30, 11.8, .3, "SUTO   /   ODOO 19 AI", 11, TEAL, True)
        text(slide, .65, .90, 12.0, .7, data["title"], 31, NAVY, True)
        text(slide, .67, 1.65, 11.9, .65, data["subtitle"], 16, "62788A")
        if idx == 0:
            rect(slide, .65, 2.55, 12.0, 3.4, NAVY, True)
            for j, bullet in enumerate(data["bullets"]):
                text(slide, 1.0, 2.95 + .78 * j, 11.0, .6, bullet, 25, "FFFFFF", j == 0)
            text(slide, .7, 6.28, 11.8, .45, "真实目录  →  受控工具  →  当前购物车  →  客户核对结账", 17, TEAL)
        else:
            bullets = data["bullets"]
            columns = data.get("layout") == "columns"
            for j, bullet in enumerate(bullets):
                if columns:
                    x, y, w, h = .65 + (j % 2) * 6.10, 2.65 + (j // 2) * 1.72, 5.85, 1.45
                    rect(slide, x, y, w, h, "FFFFFF", True)
                    text(slide, x + .25, y + .17, .65, .35, f"0{j+1}", 14, TEAL, True)
                    text(slide, x + .25, y + .55, w - .5, .85, bullet, 22, NAVY, True)
                else:
                    x, y = .65, 2.55 + j * .93
                    rect(slide, x, y, 12, .79, "FFFFFF", True)
                    text(slide, x + .24, y + .18, .60, .45, f"0{j+1}", 16, TEAL, True)
                    text(slide, x + 1.0, y + .13, 10.5, .60, bullet, 22, NAVY)
        text(slide, .67, 7.04, 11.5, .22, "Suto  ·  当前项目实现与客户会议说明  ·  2026-11-16", 10, "62788A")
        text(slide, 12.1, 7.02, .6, .25, f"{idx + 1:02d}", 11, TEAL, True)
        slide.notes_slide.notes_text_frame.text = data["notes"]
    prs.core_properties.title = source["title"]
    prs.core_properties.author = "Suto"
    prs.save(ROOT / "odoo19_ai_customer_meeting_zh.pptx")


def slides_html_from_pptx():
    """Render this deck's simple rectangles/text as a portable browser companion."""
    prs = Presentation(ROOT / "odoo19_ai_customer_meeting_zh.pptx")
    slides = []
    for index, slide in enumerate(prs.slides):
        elements = []
        for shape in slide.shapes:
            x, y, w, h = [value / 914400 * 96 for value in (shape.left, shape.top, shape.width, shape.height)]
            style = f"left:{x:.2f}px;top:{y:.2f}px;width:{w:.2f}px;height:{h:.2f}px;"
            if shape.shape_type == 1:
                fill = str(shape.fill.fore_color.rgb)
                radius = "border-radius:12px;" if shape.auto_shape_type == MSO_SHAPE.ROUNDED_RECTANGLE else ""
                elements.append(f'<div class="shape" style="{style}background:#{fill};{radius}"></div>')
            if shape.has_text_frame and shape.text_frame.text:
                parts = []
                for paragraph in shape.text_frame.paragraphs:
                    if not paragraph.text:
                        continue
                    font = paragraph.font
                    size = (font.size.pt if font.size else 18) * 96 / 72
                    color = str(font.color.rgb) if font.color.type else NAVY
                    parts.append(f'<p style="font-size:{size:.2f}px;color:#{color};font-weight:{700 if font.bold else 400}">{html.escape(paragraph.text)}</p>')
                elements.append(f'<div class="shape text" style="{style}">{"".join(parts)}</div>')
        slides.append(f'<section class="slide" id="slide-{index+1}">{"".join(elements)}</section>')
    target = ROOT / "odoo19_ai_customer_meeting_zh.html"
    target.write_text(f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>Odoo 19 AI 客户会议演示</title>
<style>*{{box-sizing:border-box}} body{{margin:0;background:#dce5ec;font-family:'Microsoft YaHei',sans-serif}} .toolbar{{padding:14px 24px;color:#16324f}} a{{color:#087f8c}} .slide{{width:1280px;height:720px;position:relative;overflow:hidden;margin:24px auto;background:#f3f7fa;box-shadow:0 3px 20px #bbc9d3}} .shape{{position:absolute}} .text{{padding-top:4px;line-height:1.25;white-space:normal;overflow:hidden}} p{{margin:0 0 10px}} @page{{size:338.667mm 190.5mm;margin:0}} @media print{{body{{background:white}} .toolbar{{display:none}} .slide{{margin:0;box-shadow:none;break-after:page}} .slide:last-child{{break-after:auto}}}} body.present .toolbar{{position:fixed;z-index:100;background:#e8f1f7;opacity:.9}} body.present .slide{{display:none;position:fixed;top:50%;left:50%;margin:0;transform:translate(-50%,-50%) scale(var(--slide-scale))}} body.present .slide.active{{display:block}}</style>
</head><body><div class="toolbar"><a href="index.html">资料入口</a>　<button id="present">开始放映 / 退出</button>　放映模式使用 ← → 翻页，Esc 退出。PPT 中附有逐页讲稿备注。</div>{''.join(slides)}
<script>const slides=[...document.querySelectorAll('.slide')];let current=0;function show(){{slides.forEach((s,i)=>s.classList.toggle('active',i===current));document.documentElement.style.setProperty('--slide-scale',Math.min(innerWidth/1280,innerHeight/720));}}document.getElementById('present').onclick=()=>{{document.body.classList.toggle('present');show();}};addEventListener('resize',show);addEventListener('keydown',e=>{{if(e.key==='Escape')document.body.classList.remove('present');if(document.body.classList.contains('present')){{if(['ArrowRight','PageDown',' '].includes(e.key)){{e.preventDefault();current=Math.min(slides.length-1,current+1);}}if(['ArrowLeft','PageUp'].includes(e.key)){{e.preventDefault();current=Math.max(0,current-1);}}show();}}}});show();</script></body></html>''', encoding="utf-8")
    return target


def add_pdf_navigation(path, sources):
    """Add page numbers and heading bookmarks without relying on a PDF service."""
    document = pymupdf.open(path)
    normalize = lambda value: re.sub(r"\s+", "", value)
    texts = [normalize(p.get_text()) for p in document]
    entries = []
    minimum_page = 0
    for source in sources:
        for line in source.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^(#{1,2}) (.+)$", line)
            if not match:
                continue
            level, title = len(match.group(1)), match.group(2)
            needle = normalize(title)
            for index in range(minimum_page, len(document)):
                if needle in texts[index]:
                    entries.append([level, title, index + 1])
                    minimum_page = index
                    break
    if entries:
        document.set_toc(entries)
    for index, page in enumerate(document):
        page.insert_text((page.rect.width - 80, page.rect.height - 20), f"{index+1} / {len(document)}", fontsize=8, color=(.35, .43, .5))
        page.insert_text((48, page.rect.height - 20), "SUTO | Odoo 19 AI | 2026-11-16", fontsize=7.5, color=(.35, .43, .5))
    staged = args.temp / f"numbered_{path.name}"
    document.save(staged, garbage=3, deflate=True)
    document.close()
    path.write_bytes(staged.read_bytes())


main_source = ROOT / "odoo19_ai_development_guide_zh.md"
developer_source = ROOT / "developer_reference_zh.md"
deepseek_source = ROOT / "deepseek_integration_zh.md"
meeting_source = ROOT / "meeting_guide_zh.md"
complete_sources = [main_source, developer_source, deepseek_source]

complete_html = write_html("odoo19_ai_development_guide_zh", "Odoo 19 AI 功能开发与说明文档（含 DeepSeek 适配）", complete_sources)
meeting_html = write_html("meeting_guide_zh", "Odoo 19 AI 客户会议讲稿与演示指南", [meeting_source])
write_html("developer_reference_zh", "Odoo 19 AI 开发技术参考", [developer_source])
deepseek_html = write_html("deepseek_integration_zh", "DeepSeek 适配实现与交付说明", [deepseek_source])
write_docx("odoo19_ai_development_guide_zh", complete_sources)
write_docx("meeting_guide_zh", [meeting_source])
write_docx("deepseek_integration_zh", [deepseek_source])
write_pptx()
slides_html = slides_html_from_pptx()
pdf_from_html(complete_html, ROOT / "odoo19_ai_development_guide_zh.pdf")
pdf_from_html(meeting_html, ROOT / "meeting_guide_zh.pdf")
pdf_from_html(slides_html, ROOT / "odoo19_ai_customer_meeting_zh.pdf")
pdf_from_html(deepseek_html, ROOT / "deepseek_integration_zh.pdf")
add_pdf_navigation(ROOT / "odoo19_ai_development_guide_zh.pdf", complete_sources)
add_pdf_navigation(ROOT / "meeting_guide_zh.pdf", [meeting_source])
add_pdf_navigation(ROOT / "deepseek_integration_zh.pdf", [deepseek_source])

report = {"generated_at": "2026-11-16", "version": "1.3", "pdfs": {}}
for name in ("odoo19_ai_development_guide_zh", "meeting_guide_zh", "odoo19_ai_customer_meeting_zh", "deepseek_integration_zh"):
    with pymupdf.open(ROOT / f"{name}.pdf") as pdf:
        report["pdfs"][name] = {"pages": len(pdf), "characters": sum(len(p.get_text()) for p in pdf),
                                "empty_pages": [i + 1 for i, p in enumerate(pdf) if not p.get_text().strip()]}
        pages = sorted(set([0, min(4, len(pdf) - 1), len(pdf) - 1]))
        for i in pages:
            pdf[i].get_pixmap(matrix=pymupdf.Matrix(1, 1)).save(args.temp / f"{name}_page_{i + 1}.png")
report["presentation"] = {"slides": len(Presentation(ROOT / "odoo19_ai_customer_meeting_zh.pptx").slides)}
# Keep the overview's page counts current when documentation grows.
index_path = ROOT / "index.html"
index_text = index_path.read_text(encoding="utf-8")
for name in report["pdfs"]:
    index_text = index_text.replace("{{" + name + "_pages}}", str(report["pdfs"][name]["pages"]))
    index_text = re.sub(rf'(data-page-count="{name}">)\d+',
                        lambda match: match.group(1) + str(report["pdfs"][name]["pages"]), index_text)
index_path.write_text(index_text, encoding="utf-8")
archive_path = ROOT / "odoo19_ai_documentation_zh.zip"
files = [path for path in ROOT.rglob("*") if path.is_file() and path.suffix != ".zip" and "__pycache__" not in path.parts]
with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, Path("odoo19_ai_documentation_zh") / path.relative_to(ROOT))
report["archive"] = {"files": len(files), "bytes": archive_path.stat().st_size}
(args.temp / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
