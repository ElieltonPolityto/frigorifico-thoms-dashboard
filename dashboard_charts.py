"""Shared Altair charts for the Streamlit dashboard and PDF report."""

from __future__ import annotations

import altair as alt
import pandas as pd

from thoms_dashboard_data import (
    PHASE_LOADING,
    PHASE_TO_TARGET,
    Cycle,
    cycle_frame,
    hourly_phase_summary,
)


CYCLE_COLORS = ["#142B51", "#3CAAFB", "#82C9FD"]
BAR_PHASE_ORDER = (PHASE_LOADING, PHASE_TO_TARGET)
CONTINUOUS_PHASE_ORDER = (PHASE_LOADING, PHASE_TO_TARGET)
LINE_METRICS = frozenset({"Peso", "DT_ref", "Umidade", "Glicol", "Retorno de ar"})
STEP_LINE_METRICS = frozenset({"Ventilacao"})
PHASE_BACKGROUNDS = {
    PHASE_LOADING: "#E5F3FD",
    PHASE_TO_TARGET: "#F5F8FC",
}


def _cycle_name(index: int) -> str:
    return f"Ciclo {index + 1}"


def _phase_background(maximum_x: float, color: str) -> alt.Chart:
    frame = pd.DataFrame({"x0": [0.0], "x1": [max(maximum_x, 1.0)]})
    return (
        alt.Chart(frame)
        .mark_rect(color=color)
        .encode(x=alt.X("x0:Q"), x2="x1:Q")
    )


def _hourly_value_matrix(
    phase_data: pd.DataFrame,
    *,
    hour_order: list[str],
    cycle_short_domain: list[str],
    metric: str,
    unit: str,
    width: int,
) -> alt.LayerChart:
    """Render a compact value grid aligned with the hourly chart categories."""
    grid = pd.MultiIndex.from_product(
        [cycle_short_domain, hour_order],
        names=["Ciclo curto", "hour_label"],
    ).to_frame(index=False)
    value_columns = [
        "Ciclo curto",
        "hour_label",
        "value",
        "partial",
        "coverage_minutes",
    ]
    matrix_data = grid.merge(
        phase_data[value_columns],
        on=["Ciclo curto", "hour_label"],
        how="left",
    )
    matrix_data["partial"] = matrix_data["partial"].astype("boolean").fillna(False)
    precision = 2 if metric == "Peso" else 1
    matrix_data["value_label"] = matrix_data["value"].map(
        lambda value: "" if pd.isna(value) else f"{value:.{precision}f}"
    )
    matrix_data.loc[matrix_data["partial"], "value_label"] += "*"

    x = alt.X("hour_label:O", sort=hour_order, title=None, axis=None)
    y = alt.Y(
        "Ciclo curto:N",
        sort=cycle_short_domain,
        title=None,
        axis=alt.Axis(
            domain=False,
            ticks=False,
            labelColor="#142B51",
            labelFontWeight=600,
            labelPadding=8,
        ),
    )
    tooltip = [
        alt.Tooltip("Ciclo curto:N", title="Ciclo"),
        alt.Tooltip("hour_label:N", title="Hora"),
        alt.Tooltip("value:Q", title=f"Média ({unit})", format=".2f"),
        alt.Tooltip("coverage_minutes:Q", title="Cobertura (min)", format=".0f"),
        alt.Tooltip("partial:N", title="Hora parcial"),
    ]
    cells = (
        alt.Chart(matrix_data)
        .mark_rect(fill="#F7FAFC", stroke="#D9E3EE")
        .encode(x=x, y=y)
    )
    values = (
        alt.Chart(matrix_data)
        .mark_text(color="#263238", fontSize=10, fontWeight=500)
        .encode(
            x=x,
            y=y,
            text="value_label:N",
            opacity=alt.condition(alt.datum.partial, alt.value(0.52), alt.value(0.95)),
            tooltip=tooltip,
        )
    )
    return (cells + values).properties(
        width=width,
        height=max(28, len(cycle_short_domain) * 24),
    )


def continuous_phase_chart(
    selected_cycles: list[Cycle],
    data: pd.DataFrame,
    metric: str,
    selected_hours: list[str],
    *,
    horizontal: bool = False,
):
    """Compare cycles in separate phase-relative line panels."""
    rows: list[pd.DataFrame] = []
    unit = ""
    for index, cycle in enumerate(selected_cycles):
        frame = cycle_frame(data, cycle, metric)
        unit = str(frame["unit"].iloc[0])
        frame = frame[frame["hour_label"].isin(selected_hours)].copy()
        frame["Ciclo"] = _cycle_name(index)
        rows.append(frame)

    chart_data = pd.concat(rows, ignore_index=True)
    cycle_domain = [_cycle_name(index) for index in range(len(selected_cycles))]
    panels: list[alt.Chart] = []

    for phase in CONTINUOUS_PHASE_ORDER:
        phase_data = chart_data[chart_data["phase"].eq(phase)].copy()
        if phase_data.empty:
            continue
        maximum_x = float(phase_data["hours_from_phase_start"].max())
        background = _phase_background(maximum_x, PHASE_BACKGROUNDS[phase])
        lines = (
            alt.Chart(phase_data)
            .mark_line(strokeWidth=2.4)
            .encode(
                x=alt.X(
                    "hours_from_phase_start:Q",
                    title="Horas desde o início da fase",
                    axis=alt.Axis(tickMinStep=1),
                ),
                y=alt.Y("value:Q", title=unit, scale=alt.Scale(zero=False)),
                color=alt.Color(
                    "Ciclo:N",
                    scale=alt.Scale(
                        domain=cycle_domain,
                        range=CYCLE_COLORS[: len(selected_cycles)],
                    ),
                    legend=alt.Legend(orient="top", title=None),
                ),
                tooltip=[
                    alt.Tooltip("Ciclo:N", title="Ciclo"),
                    alt.Tooltip("hour_label:N", title="Hora"),
                    alt.Tooltip(
                        "hours_from_phase_start:Q",
                        title="Hora da fase",
                        format=".2f",
                    ),
                    alt.Tooltip("value:Q", title=metric, format=".2f"),
                ],
            )
        )
        panel: alt.Chart = (background + lines).properties(
            title=phase,
            height=190,
        )
        if metric == "Espeto" and phase == PHASE_TO_TARGET:
            target = alt.Chart(pd.DataFrame({"meta": [7.0]})).mark_rule(
                color="#E4572E",
                strokeDash=[6, 4],
            ).encode(y="meta:Q")
            panel = panel + target
        panels.append(panel)

    if horizontal:
        return (
            alt.hconcat(
                *[
                    panel.properties(width=270, height=255)
                    for panel in panels
                ]
            )
            .resolve_scale(y="independent", color="shared")
        )
    return alt.vconcat(*panels).resolve_scale(y="independent", color="shared")


def hourly_metric_chart(
    selected_cycles: list[Cycle],
    data: pd.DataFrame,
    metric: str,
    selected_hours: list[str],
) -> alt.TopLevelMixin:
    """Render hourly phase comparisons with a form appropriate to each metric."""
    rows: list[pd.DataFrame] = []
    unit = ""
    for index, cycle in enumerate(selected_cycles):
        hourly = hourly_phase_summary(data, cycle, metric)
        if hourly.empty:
            continue
        unit = str(hourly["unit"].iloc[0])
        hourly = hourly[hourly["hour_label"].isin(selected_hours)].copy()
        hourly["Ciclo"] = _cycle_name(index)
        hourly["Ciclo curto"] = f"C{index + 1}"
        rows.append(hourly)

    if not rows:
        return _empty_hourly_chart()

    chart_data = pd.concat(rows, ignore_index=True)
    chart_data = chart_data[chart_data["phase"].isin(BAR_PHASE_ORDER)].copy()
    if chart_data.empty:
        return _empty_hourly_chart()

    cycle_domain = [_cycle_name(index) for index in range(len(selected_cycles))]
    cycle_short_domain = [f"C{index + 1}" for index in range(len(selected_cycles))]
    panels: list[alt.TopLevelMixin] = []

    for phase in BAR_PHASE_ORDER:
        phase_data = chart_data[chart_data["phase"].eq(phase)].copy()
        if phase_data.empty:
            continue
        hour_order = (
            phase_data[["phase_hour", "hour_label"]]
            .drop_duplicates()
            .sort_values("phase_hour")["hour_label"]
            .tolist()
        )
        x = alt.X(
            "hour_label:O",
            sort=hour_order,
            title=None,
            axis=alt.Axis(labelAngle=0, labelPadding=8, labelLimit=44),
        )
        offset = alt.XOffset("Ciclo:N", sort=cycle_domain)
        y_scale = (
            alt.Scale(domain=[92, 100], zero=False)
            if metric == "Umidade"
            else alt.Scale(zero=True)
        )
        y = alt.Y("value:Q", title=f"Média ({unit})", scale=y_scale)
        color = alt.Color(
            "Ciclo:N",
            scale=alt.Scale(
                domain=cycle_domain,
                range=CYCLE_COLORS[: len(selected_cycles)],
            ),
            legend=alt.Legend(orient="top", title=None),
        )
        opacity = alt.condition(
            alt.datum.partial,
            alt.value(0.48),
            alt.value(0.86),
        )
        tooltip = [
            alt.Tooltip("Ciclo:N", title="Ciclo"),
            alt.Tooltip("hour_label:N", title="Hora"),
            alt.Tooltip("value:Q", title=f"Média ({unit})", format=".2f"),
            alt.Tooltip(
                "coverage_minutes:Q",
                title="Cobertura (min)",
                format=".0f",
            ),
            alt.Tooltip("partial:N", title="Hora parcial"),
        ]
        bar_encoding: dict[str, object] = {
            "x": x,
            "xOffset": offset,
            "y": y,
            "color": color,
            "opacity": opacity,
            "tooltip": tooltip,
        }
        if metric == "Umidade":
            bar_encoding["y2"] = alt.datum(92)

        if metric in LINE_METRICS or metric in STEP_LINE_METRICS:
            line_encoding = {
                "x": x,
                "y": y,
                "color": color,
                "detail": "Ciclo:N",
                "tooltip": tooltip,
            }
            line_mark = alt.Chart(phase_data).mark_line(
                strokeWidth=2.6,
                interpolate="step-after" if metric in STEP_LINE_METRICS else "linear",
            )
            lines = (
                line_mark.encode(**line_encoding)
            )
            points = (
                alt.Chart(phase_data)
                .mark_point(
                    size=58,
                    filled=True,
                    shape="square" if metric in STEP_LINE_METRICS else "circle",
                    strokeWidth=1.2,
                )
                .encode(**line_encoding, opacity=opacity)
            )
            chart = lines + points
        else:
            chart = alt.Chart(phase_data).mark_bar(
                cornerRadiusTopLeft=2,
                cornerRadiusTopRight=2,
            ).encode(**bar_encoding)
        panel_width = max(560, min(760, len(hour_order) * 52))
        matrix = _hourly_value_matrix(
            phase_data,
            hour_order=hour_order,
            cycle_short_domain=cycle_short_domain,
            metric=metric,
            unit=unit,
            width=panel_width,
        )
        panels.append(
            alt.vconcat(
                chart.properties(
                    title=phase,
                    width=panel_width,
                    height=235,
                ),
                matrix,
                spacing=2,
            ).resolve_scale(x="shared")
        )

    return alt.vconcat(*panels, spacing=30).resolve_scale(y="shared", color="shared")


def _empty_hourly_chart() -> alt.Chart:
    """Explain why a bar chart is absent when only post-target hours are selected."""
    return (
        alt.Chart(
            pd.DataFrame(
                {
                    "message": [
                        "Barras disponíveis apenas para carregamento e resfriamento até a meta."
                    ]
                }
            )
        )
        .mark_text(align="left", baseline="middle", color="#51606F", fontSize=13)
        .encode(text="message:N")
        .properties(width=620, height=42)
    )
