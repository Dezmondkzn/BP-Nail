"""Proposal layout based on the supplied ATechnika example."""

import io
from pathlib import Path
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from .domain import BusinessError
from .documents import rub
from datetime import date


def table(document, rows, widths):
    result = document.add_table(rows=0, cols=len(widths))
    result.autofit = False
    for col, width in zip(result.columns, widths):
        col.width = Cm(width)
    for index, values in enumerate(rows):
        row = result.add_row()
        props = row._tr.get_or_add_trPr()
        props.append(OxmlElement("w:cantSplit"))
        if index == 0:
            props.append(OxmlElement("w:tblHeader"))
        for cell, value, width in zip(row.cells, values, widths):
            cell.width = Cm(width)
            cell.text = str(value)
            pr = cell._tc.get_or_add_tcPr()
            borders = OxmlElement("w:tcBorders")
            for side in ("top", "left", "bottom", "right"):
                el = OxmlElement("w:" + side)
                el.set(qn("w:val"), "single")
                el.set(qn("w:sz"), "4")
                el.set(qn("w:color"), "B5B5B5")
                borders.append(el)
            pr.append(borders)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(2)
                paragraph.paragraph_format.space_before = Pt(2)
                for run in paragraph.runs:
                    run.font.size = Pt(10)
                    run.bold = index == 0
    return result


def build_proposal(letterhead, view, target):
    payload = view["payload"]
    if any(i.get("unit_price") is None or i.get("pricing_source") != "manager" for i in payload["items"]):
        raise BusinessError("Перед подготовкой КП укажите цену каждой позиции.")
    d = Document(io.BytesIO(letterhead))
    body = d._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)
    for section in d.sections:
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.top_margin, section.bottom_margin = Cm(4), Cm(1.8)
        section.left_margin, section.right_margin = Cm(2.2), Cm(2)
    for name, size in (("Normal", 12), ("Title", 14), ("Heading 1", 12)):
        if name not in d.styles:
            d.styles.add_style(name, 1)
        st = d.styles[name]
        st.font.name, st.font.size = "Times New Roman", Pt(size)
        st.font.color.rgb = RGBColor(0, 0, 0)
        st.paragraph_format.space_after = Pt(5)
        st.paragraph_format.line_spacing = 1.0
        if name != "Normal":
            st.font.bold = True
            st.paragraph_format.keep_with_next = True
    issued = date.fromisoformat(view["created_at"][:10]).strftime("%d.%m.%Y")
    d.add_paragraph(f"Исх. № КП-{view['id']:05d} от {issued} · Версия {view['version']}")
    title = d.add_paragraph("Коммерческое предложение", "Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph("Кому: " + payload["client"])
    d.add_paragraph(
        "ООО «АТЕХНИКА» предлагает Вам рассмотреть возможность приобретения следующей техники и оборудования."
    )
    for index, item in enumerate(payload["items"]):
        profile = item.get("profile") or {}
        if index:
            d.add_page_break()
        d.add_paragraph(item["name"], "Heading 1")
        if profile.get("description"):
            d.add_paragraph(profile["description"])
        if profile.get("benefits"):
            d.add_paragraph("Основные задачи и выгоды", "Heading 1")
            for benefit in profile["benefits"]:
                paragraph = d.add_paragraph("• " + benefit)
                paragraph.paragraph_format.space_after = Pt(4)
        image_key = profile.get("image_key")
        photo = view.get("_images", {}).get(image_key)
        if photo:
            d.add_paragraph().add_run().add_picture(io.BytesIO(photo), width=Cm(16.5))
        if profile.get("specifications"):
            d.add_page_break()
            d.add_paragraph("Краткая спецификация", "Heading 1")
            table(
                d, [("Параметр", profile.get("model", item["name"]))] + profile["specifications"], [11.7, 5.1]
            )
        elif item.get("configuration"):
            d.add_paragraph("Комплектация: " + item["configuration"])
        if profile.get("note"):
            note = d.add_paragraph(profile["note"])
            for run in note.runs:
                run.font.size = Pt(10)
        d.add_paragraph(
            f"Количество: {item['quantity']} шт. Цена за единицу с НДС {item['vat_rate']}%: "
            f"{rub(item['unit_price'])} руб. Сумма: {rub(item['line_total'])} руб."
        )
    d.add_paragraph("Коммерческие условия", "Heading 1")
    d.add_paragraph(
        f"Итого: {rub(payload['totals']['gross'])} руб., в том числе НДС {rub(payload['totals']['vat'])} руб."
    )
    d.add_paragraph("1. Срок поставки: " + payload["delivery_terms"])
    d.add_paragraph("2. Условия оплаты: предоплата 100%.")
    d.add_paragraph("3. Условия поставки: " + payload["collection"])
    d.add_paragraph(
        "Предложение действительно до "
        + date.fromisoformat(payload["valid_until"]).strftime("%d.%m.%Y")
        + "."
    )
    d.add_paragraph("Надеемся на взаимовыгодное сотрудничество.")
    d.add_paragraph("С уважением,\nМенеджер отдела продаж ООО «АТЕХНИКА»\n" + payload["manager"])
    d.save(Path(target))
