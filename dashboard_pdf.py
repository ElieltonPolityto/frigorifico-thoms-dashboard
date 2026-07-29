"""PDF export for the current Thoms dashboard selection."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
from PIL import Image as PilImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.ttfonts import TTFError
from reportlab.platypus import (
    Image,
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from dashboard_charts import continuous_phase_chart, hourly_metric_chart
from thoms_dashboard_data import (
    PHASE_ORDER,
    Cycle,
    cycle_metrics,
    hourly_phase_summary,
    selection_insights,
)


PAGE_SIZE = landscape(A4)
BRAND_BLUE = colors.HexColor("#142B51")
ACCENT_BLUE = colors.HexColor("#3CAAFB")
LIGHT_BLUE = colors.HexColor("#E5F3FD")
GRID_COLOR = colors.HexColor("#D9E3EE")


def _register_fonts(logo_path: Path) -> tuple[str, str]:
    fonts_folder = logo_path.parent.parent / "fonts"
    regular_path = fonts_folder / "GothamBook.otf"
    bold_path = fonts_folder / "GothamBold.otf"
    regular_name = "GothamBook"
    bold_name = "GothamBold"
    try:
        if regular_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
        if bold_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
        return regular_name, bold_name
    except (OSError, TTFError):
        # Gotham OTF files use PostScript outlines, which ReportLab cannot embed.
        return "Helvetica", "Helvetica-Bold"


def _styles(regular_font: str, bold_font: str):
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ThomsTitle",
            parent=styles["Title"],
            fontName=bold_font,
            fontSize=20,
            leading=24,
            textColor=BRAND_BLUE,
            alignment=TA_LEFT,
            spaceAfter=5 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ThomsHeading",
            parent=styles["Heading2"],
            fontName=bold_font,
            fontSize=13,
            leading=16,
            textColor=BRAND_BLUE,
            spaceBefore=4 * mm,
            spaceAfter=2.5 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ThomsBody",
            parent=styles["BodyText"],
            fontName=regular_font,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#263238"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="ThomsSmall",
            parent=styles["BodyText"],
            fontName=regular_font,
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#5D6C7B"),
        )
    )
    return styles


def _paragraph(value: object, style) -> Paragraph:
    text = "—" if value is None or pd.isna(value) else str(value)
    return Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)


def _table(data, widths, regular_font: str, bold_font: str, repeat_rows: int = 1):
    table = LongTable(data, colWidths=widths, repeatRows=repeat_rows, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), bold_font),
                ("FONTNAME", (0, 1), (-1, -1), regular_font),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("LEADING", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.35, GRID_COLOR),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _chart_png(chart) -> bytes:
    import vl_convert as vlc

    return vlc.vegalite_to_png(chart.to_dict(), scale=1.5)


def _chart_image(chart, maximum_width: float, maximum_height: float = 170 * mm) -> Image:
    png = _chart_png(chart)
    with PilImage.open(BytesIO(png)) as image:
        source_width, source_height = image.size
    scale = min(maximum_width / source_width, maximum_height / source_height)
    return Image(
        BytesIO(png),
        width=source_width * scale,
        height=source_height * scale,
    )


def _format_value(value, suffix: str, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.{decimals}f} {suffix}"


def _summary_tables(
    selected_cycles: list[Cycle],
    data: pd.DataFrame,
    styles,
    regular_font: str,
    bold_font: str,
):
    overview = [
        [
            "Ciclo",
            "Período",
            "C",
            "R",
            "P",
            "Até 7 °C",
            "Perda até 7 °C",
        ]
    ]
    detail = [
        [
            "Ciclo",
            "Peso de referencia",
            "Peso aos 7 °C",
            "Espeto inicial",
            "Espeto final",
            "DT_ref médio",
        ]
    ]
    for index, cycle in enumerate(selected_cycles):
        metrics = cycle_metrics(data, cycle)
        time_to_target = metrics["Tempo ate 7 C"]
        reference_weight = metrics.get(
            "Peso referencia",
            metrics.get("Peso inicial"),
        )
        overview.append(
            [
                f"Ciclo {index + 1}",
                _paragraph(cycle.label, styles["ThomsSmall"]),
                _format_value(metrics["Duracao carga"], "h"),
                _format_value(metrics["Duracao ate meta"], "h"),
                _format_value(metrics["Duracao pos meta"], "h"),
                (
                    _format_value(time_to_target, "h")
                    if isinstance(time_to_target, (int, float))
                    else "Meta não atingida"
                ),
                _format_value(metrics["Perda"], "%", 2),
            ]
        )
        detail.append(
            [
                f"Ciclo {index + 1}",
                _format_value(reference_weight, "kg"),
                _format_value(metrics["Peso final"], "kg"),
                _format_value(metrics["Espeto inicial"], "°C"),
                _format_value(metrics["Espeto final"], "°C"),
                _format_value(metrics["DT_ref medio"], "°C"),
            ]
        )
    return (
        _table(
            overview,
            [18 * mm, 68 * mm, 18 * mm, 18 * mm, 18 * mm, 25 * mm, 29 * mm],
            regular_font,
            bold_font,
        ),
        _table(
            detail,
            [22 * mm, 30 * mm, 32 * mm, 30 * mm, 30 * mm, 30 * mm],
            regular_font,
            bold_font,
        ),
    )


def _hourly_table(
    selected_cycles: list[Cycle],
    data: pd.DataFrame,
    metric: str,
    selected_hours: list[str],
    styles,
    regular_font: str,
    bold_font: str,
):
    rows: dict[tuple[str, int, str], list[object]] = {}
    for index, cycle in enumerate(selected_cycles):
        hourly = hourly_phase_summary(data, cycle, metric)
        hourly = hourly[hourly["hour_label"].isin(selected_hours)]
        for record in hourly.to_dict("records"):
            key = (
                str(record["phase"]),
                int(record["phase_hour"]),
                str(record["hour_label"]),
            )
            row = rows.setdefault(
                key,
                [str(record["phase"]), str(record["hour_label"])]
                + ["—"] * len(selected_cycles),
            )
            partial = " - parcial" if bool(record["partial"]) else ""
            row[2 + index] = (
                f'{float(record["value"]):.2f} {record["unit"]} | '
                f'{float(record["coverage_minutes"]):.0f} min{partial}'
            )
    ordered = [
        row
        for _, row in sorted(
            rows.items(),
            key=lambda item: (PHASE_ORDER.index(item[0][0]), item[0][1]),
        )
    ]
    header = ["Fase", "Hora"] + [
        f"Ciclo {index + 1}" for index in range(len(selected_cycles))
    ]
    paragraph_rows = [
        [_paragraph(value, styles["ThomsSmall"]) for value in row]
        for row in [header] + ordered
    ]
    widths = [42 * mm, 15 * mm] + [48 * mm] * len(selected_cycles)
    return _table(paragraph_rows, widths, regular_font, bold_font)


def _page_footer(canvas, document, regular_font: str):
    canvas.saveState()
    canvas.setStrokeColor(GRID_COLOR)
    canvas.line(15 * mm, 10 * mm, PAGE_SIZE[0] - 15 * mm, 10 * mm)
    canvas.setFont(regular_font, 7)
    canvas.setFillColor(colors.HexColor("#5D6C7B"))
    canvas.drawString(15 * mm, 6 * mm, "Frigorífico Thoms - relatório da seleção")
    canvas.drawRightString(
        PAGE_SIZE[0] - 15 * mm,
        6 * mm,
        f"Página {canvas.getPageNumber()}",
    )
    canvas.restoreState()


def build_dashboard_pdf(
    *,
    selected_cycles: list[Cycle],
    data: pd.DataFrame,
    ranking: pd.DataFrame,
    main_metric: str,
    bar_metrics: list[str],
    selected_hours: list[str],
    logo_path: Path,
) -> bytes:
    """Generate a branded PDF from the exact current dashboard selection."""
    regular_font, bold_font = _register_fonts(logo_path)
    styles = _styles(regular_font, bold_font)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=13 * mm,
        bottomMargin=15 * mm,
        title="Relatório da seleção - Ciclos Thoms",
        author="Plotter Racks",
    )
    usable_width = PAGE_SIZE[0] - document.leftMargin - document.rightMargin
    story = []

    if logo_path.exists():
        story.append(Image(str(logo_path), width=62 * mm, height=15 * mm))
        story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Relatório da seleção - Ciclos de resfriamento", styles["ThomsTitle"]))
    generated_at = datetime.now().astimezone()
    story.append(
        Paragraph(
            f"Gerado em {generated_at:%d/%m/%Y às %H:%M} | "
            f"Janela: {selected_hours[0]} a {selected_hours[-1]} | "
            f"Gráfico contínuo: {main_metric}",
            styles["ThomsSmall"],
        )
    )
    story.append(
        Paragraph(
            "Variáveis horárias: " + (", ".join(bar_metrics) if bar_metrics else "nenhuma"),
            styles["ThomsSmall"],
        )
    )

    story.append(Paragraph("Leitura da seleção", styles["ThomsHeading"]))
    for insight in selection_insights(data, selected_cycles, ranking):
        story.append(
            Table(
                [[_paragraph(insight, styles["ThomsBody"])]],
                colWidths=[usable_width],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F8FC")),
                        ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT_BLUE),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                ),
            )
        )
        story.append(Spacer(1, 1.5 * mm))
    story.append(
        Paragraph(
            "Síntese descritiva dos dados observados; não estabelece causalidade.",
            styles["ThomsSmall"],
        )
    )

    story.append(Paragraph("Resumo dos ciclos", styles["ThomsHeading"]))
    overview_table, detail_table = _summary_tables(
        selected_cycles,
        data,
        styles,
        regular_font,
        bold_font,
    )
    story.append(overview_table)
    story.append(Spacer(1, 3 * mm))
    story.append(detail_table)

    story.append(PageBreak())
    story.append(
        Paragraph(
            f"{main_metric} - carregamento e resfriamento até a meta",
            styles["ThomsHeading"],
        )
    )
    story.append(
        _chart_image(
            continuous_phase_chart(
                selected_cycles,
                data,
                main_metric,
                selected_hours,
                horizontal=True,
            ),
            usable_width,
            maximum_height=135 * mm,
        )
    )

    for metric in bar_metrics:
        story.append(PageBreak())
        story.append(
            Paragraph(
                f"{metric} - médias horárias do carregamento ao resfriamento até a meta",
                styles["ThomsHeading"],
            )
        )
        story.append(
            _chart_image(
                hourly_metric_chart(
                    selected_cycles,
                    data,
                    metric,
                    selected_hours,
                ),
                usable_width,
                maximum_height=115 * mm,
            )
        )
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Tabela explicativa", styles["ThomsHeading"]))
        story.append(
            _hourly_table(
                selected_cycles,
                data,
                metric,
                selected_hours,
                styles,
                regular_font,
                bold_font,
            )
        )

    story.append(Spacer(1, 4 * mm))
    story.append(
        KeepTogether(
            [
                Paragraph("Critérios de leitura", styles["ThomsHeading"]),
                Paragraph(
                    "C = carregamento; R = resfriamento até a primeira leitura do "
                    "espeto menor ou igual a 7 °C; P = resfriamento pós-meta. "
                    "Horas com menos de 45 minutos de cobertura são parciais. "
                    "O ranking combina, em partes iguais, tempo até 7 °C e perda "
                    "de peso; ciclos sem meta ou com perda negativa ficam fora.",
                    styles["ThomsBody"],
                ),
            ]
        )
    )

    document.build(
        story,
        onFirstPage=lambda canvas, doc: _page_footer(canvas, doc, regular_font),
        onLaterPages=lambda canvas, doc: _page_footer(canvas, doc, regular_font),
    )
    return buffer.getvalue()
