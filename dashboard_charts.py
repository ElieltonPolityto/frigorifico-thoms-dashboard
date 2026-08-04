"""Shared Altair charts for the Streamlit dashboard and PDF report."""

from __future__ import annotations

import altair as alt
import pandas as pd

from thoms_dashboard_data import (
    PHASE_LOADING,
    PHASE_POST_TARGET,
    PHASE_TO_TARGET,
    Cycle,
    cycle_frame,
    hourly_phase_summary,
    valid_weight_series,
    weight_loss_frame,
)


CYCLE_COLORS = ["#142B51", "#D55E00", "#00796B"]
CYCLE_DASHES = [[1, 0], [7, 3], [2, 2]]
CYCLE_SHAPES = ["circle", "triangle-up", "square"]
MAIN_METRIC_COLORS = {
    "Retorno de ar": "#142B51",
    "Espeto": "#D55E00",
    "Ventilacao": "#0072B2",
    "Umidade": "#00796B",
    "Peso": "#6F4C9B",
}
MAIN_METRIC_LABELS = {
    "Retorno de ar": "Retorno do ar",
    "Espeto": "Espeto",
    "Ventilacao": "Ventilacao",
    "Umidade": "Umidade relativa",
    "Peso": "Peso atual",
}
MAIN_METRIC_ORDER = ("Retorno de ar", "Espeto", "Ventilacao", "Umidade", "Peso")
BAR_PHASE_ORDER = (PHASE_LOADING, PHASE_TO_TARGET)
CONTINUOUS_PHASE_ORDER = (PHASE_LOADING, PHASE_TO_TARGET)
LINE_METRICS = frozenset({"Peso", "DT_ref", "Umidade", "Glicol", "Retorno de ar"})
STEP_LINE_METRICS = frozenset({"Ventilacao"})


def _cycle_name(index: int) -> str:
    return f"Ciclo {index + 1}"


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
    """Compare loading and cooling-to-target together on one elapsed-time axis."""
    rows: list[pd.DataFrame] = []
    unit = ""
    for index, cycle in enumerate(selected_cycles):
        frame = cycle_frame(data, cycle, metric)
        unit = str(frame["unit"].iloc[0])
        frame = frame[frame["hour_label"].isin(selected_hours)].copy()
        frame = frame[frame["phase"].isin(CONTINUOUS_PHASE_ORDER)].copy()
        frame["Ciclo"] = _cycle_name(index)
        rows.append(frame)

    if not rows:
        return _empty_hourly_chart()

    chart_data = pd.concat(rows, ignore_index=True)
    if chart_data.empty:
        return _empty_hourly_chart()
    cycle_domain = [_cycle_name(index) for index in range(len(selected_cycles))]
    lines = (
        alt.Chart(chart_data)
        .mark_line(strokeWidth=2.4)
        .encode(
            x=alt.X(
                "hours_from_cycle_start:Q",
                title="Horas desde o início do ciclo",
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
            strokeDash=alt.StrokeDash(
                "Ciclo:N",
                scale=alt.Scale(
                    domain=cycle_domain,
                    range=CYCLE_DASHES[: len(selected_cycles)],
                ),
                legend=None,
            ),
            detail="Ciclo:N",
            tooltip=[
                alt.Tooltip("Ciclo:N", title="Ciclo"),
                alt.Tooltip("phase:N", title="Fase"),
                alt.Tooltip("hour_label:N", title="Hora"),
                alt.Tooltip(
                    "hours_from_cycle_start:Q",
                    title="Hora do ciclo",
                    format=".2f",
                ),
                alt.Tooltip("value:Q", title=metric, format=".2f"),
            ],
        )
    )
    chart: alt.TopLevelMixin = lines.properties(height=255 if horizontal else 260)
    if metric == "Espeto":
        target = alt.Chart(pd.DataFrame({"meta": [7.0]})).mark_rule(
            color="#E4572E",
            strokeDash=[6, 4],
        ).encode(y="meta:Q")
        chart = chart + target
    return chart.properties(width=560 if horizontal else 760)


def _phase_intervals(frame: pd.DataFrame) -> pd.DataFrame:
    """Return one visual interval per cycle phase on the elapsed-time axis."""
    if frame.empty:
        return pd.DataFrame(columns=["phase", "start", "end"])

    cadence = frame["hours_from_cycle_start"].diff().dropna().median()
    extension = float(cadence) if pd.notna(cadence) and cadence > 0 else 1 / 60
    rows = []
    for phase in (PHASE_LOADING, PHASE_TO_TARGET, PHASE_POST_TARGET):
        phase_frame = frame[frame["phase"].eq(phase)]
        if not phase_frame.empty:
            rows.append(
                {
                    "phase": phase,
                    "start": float(phase_frame["hours_from_cycle_start"].min()),
                    "end": float(phase_frame["hours_from_cycle_start"].max()) + extension,
                }
            )
    return pd.DataFrame(rows)


def _phase_background(frame: pd.DataFrame) -> alt.Chart:
    """Render low-contrast phase context without competing with series colors."""
    intervals = _phase_intervals(frame)
    return (
        alt.Chart(intervals)
        .mark_rect(opacity=0.18)
        .encode(
            x=alt.X("start:Q", title="Horas desde o inicio do ciclo"),
            x2="end:Q",
            color=alt.Color(
                "phase:N",
                scale=alt.Scale(
                    domain=[PHASE_LOADING, PHASE_TO_TARGET, PHASE_POST_TARGET],
                    range=["#82C9FD", "#F3F6FA", "#E5F3FD"],
                ),
                legend=None,
            ),
        )
    )


def _phase_markers(frame: pd.DataFrame) -> alt.LayerChart | alt.Chart:
    """Mark cooling start and the first 7 C sample when it exists."""
    rows = []
    cooling = frame[frame["phase"].eq(PHASE_TO_TARGET)]
    if not cooling.empty:
        rows.append(
            {
                "event": "Inicio do resfriamento",
                "marker_color": "#3CAAFB",
                "hours_from_cycle_start": float(cooling["hours_from_cycle_start"].min()),
            }
        )
    target = frame[frame["phase"].eq(PHASE_POST_TARGET)]
    if not target.empty:
        rows.append(
            {
                "event": "Espeto atingiu 7 C",
                "marker_color": "#D55E00",
                "hours_from_cycle_start": float(target["hours_from_cycle_start"].min()),
            }
        )
    if not rows:
        return alt.Chart(pd.DataFrame({"hours_from_cycle_start": []})).mark_rule()
    return (
        alt.Chart(pd.DataFrame(rows))
        .mark_rule(strokeWidth=1.3, strokeDash=[5, 4])
        .encode(
            x="hours_from_cycle_start:Q",
            color=alt.Color(
                "marker_color:N",
                scale=None,
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("event:N", title="Marco"),
                alt.Tooltip(
                    "hours_from_cycle_start:Q",
                    title="Hora do ciclo",
                    format=".2f",
                ),
            ],
        )
    )


def _main_metric_frame(data: pd.DataFrame, cycle: Cycle, metric: str) -> pd.DataFrame:
    """Return one main-chart series; weight is raw valid kg, not loss percent."""
    if metric == "Peso":
        result = _main_weight_frame(data, cycle)
        result["value"] = result["weight_kg"]
        result["unit"] = "kg"
        result["metric"] = metric
        result["metric_label"] = MAIN_METRIC_LABELS[metric]
        return result

    base = cycle_frame(data, cycle, "Espeto")
    result = base[
        [
            "timestamp",
            "hours_from_cycle_start",
            "phase",
            "hour_label",
        ]
    ].copy()
    metric_frame = cycle_frame(data, cycle, metric)
    result["value"] = metric_frame["value"]
    result["unit"] = str(metric_frame["unit"].iloc[0])
    result["metric"] = metric
    result["metric_label"] = MAIN_METRIC_LABELS[metric]
    return result


def _main_weight_frame(data: pd.DataFrame, cycle: Cycle) -> pd.DataFrame:
    """Return valid actual weight only through the first 7 C probe reading."""
    base = cycle_frame(data, cycle, "Espeto")
    result = base[
        ["timestamp", "hours_from_cycle_start", "phase", "hour_label"]
    ].copy()
    result["weight_kg"] = valid_weight_series(base)

    target_rows = base[base["phase"].eq(PHASE_POST_TARGET)]
    if not target_rows.empty:
        target_timestamp = target_rows["timestamp"].min()
        result.loc[result["timestamp"].gt(target_timestamp), "weight_kg"] = pd.NA

    loss = weight_loss_frame(data, cycle)[["timestamp", "loss_pct"]]
    result["loss_pct"] = result["timestamp"].map(loss.set_index("timestamp")["loss_pct"])
    result["is_hourly_loss"] = False
    hourly_rows = result.dropna(subset=["loss_pct"]).groupby("hour_label", sort=False).tail(1)
    result.loc[hourly_rows.index, "is_hourly_loss"] = True

    # O percentual horario aparece no mesmo painel, mas sem criar um segundo
    # eixo Y concorrente. A coordenada abaixo e apenas visual: ela reserva uma
    # faixa baixa do grafico de peso; o valor percentual real permanece no
    # tooltip dos pontos azuis.
    result["loss_display_kg"] = pd.NA
    weight_values = result["weight_kg"].dropna()
    loss_values = result["loss_pct"].dropna()
    if not weight_values.empty and not loss_values.empty:
        weight_low = float(weight_values.min())
        weight_span = max(float(weight_values.max()) - weight_low, 1.0)
        band_low = weight_low + (weight_span * 0.08)
        band_high = weight_low + (weight_span * 0.34)
        loss_low = float(loss_values.min())
        loss_span = max(float(loss_values.max()) - loss_low, 0.01)
        result["loss_display_kg"] = band_low + (
            (result["loss_pct"] - loss_low) / loss_span * (band_high - band_low)
        )
    return result


def _main_tooltip_frame(
    data: pd.DataFrame,
    cycle: Cycle,
    visible_metrics: tuple[str, ...],
    selected_hours: list[str],
) -> pd.DataFrame:
    """Pivot visible main-chart variables for one synchronized tooltip."""
    base = cycle_frame(data, cycle, "Espeto")
    base = base[base["hour_label"].isin(selected_hours)].copy()
    tooltip = base[["timestamp", "hours_from_cycle_start", "phase", "hour_label"]].copy()
    for metric in visible_metrics:
        series = _main_metric_frame(data, cycle, metric)
        series = series[series["hour_label"].isin(selected_hours)]
        tooltip[MAIN_METRIC_LABELS[metric]] = series["value"].to_numpy()
        if metric == "Peso":
            tooltip["loss_pct"] = series["loss_pct"].to_numpy()
    return tooltip


def main_cycle_chart(
    active_cycle: Cycle,
    selected_cycles: list[Cycle],
    data: pd.DataFrame,
    visible_metrics: list[str],
    selected_hours: list[str],
    *,
    interactive: bool = True,
) -> alt.TopLevelMixin:
    """Render the primary four-band, single-cycle analysis chart."""
    visible = tuple(metric for metric in MAIN_METRIC_ORDER if metric in visible_metrics)
    if not visible:
        return _empty_main_chart("Selecione ao menos uma variavel para o grafico principal.")

    base = cycle_frame(data, active_cycle, "Espeto")
    base = base[base["hour_label"].isin(selected_hours)].copy()
    if base.empty:
        return _empty_main_chart("A janela selecionada nao possui dados para o ciclo ativo.")

    series = {
        metric: _main_metric_frame(data, active_cycle, metric).loc[
            lambda frame: frame["hour_label"].isin(selected_hours)
        ].copy()
        for metric in visible
    }
    tooltip_frame = _main_tooltip_frame(data, active_cycle, visible, selected_hours)
    hover = (
        alt.selection_point(
            name="hover_main_cycle",
            nearest=True,
            on="pointermove",
            fields=["hours_from_cycle_start"],
            empty=False,
            clear="mouseout",
        )
        if interactive
        else None
    )
    focus = (
        alt.selection_point(
            name="focus_main_metric",
            fields=["metric"],
            on="click",
            clear="dblclick",
            empty=True,
        )
        if interactive
        else None
    )
    x = alt.X(
        "hours_from_cycle_start:Q",
        title="Horas desde o inicio do ciclo",
        axis=alt.Axis(tickMinStep=1),
    )
    phase_layer = _phase_background(base)
    marker_layer = _phase_markers(base)
    tooltip_fields = [
        alt.Tooltip("timestamp:T", title="Data e hora", format="%d/%m/%Y %H:%M"),
        alt.Tooltip("phase:N", title="Fase"),
        alt.Tooltip("hour_label:N", title="Hora da fase"),
    ]
    for metric in visible:
        tooltip_fields.append(
            alt.Tooltip(
                f"{MAIN_METRIC_LABELS[metric]}:Q",
                title=MAIN_METRIC_LABELS[metric],
                format=".2f",
            )
        )
    if "Peso" in visible:
        tooltip_fields.append(
            alt.Tooltip("loss_pct:Q", title="Perda acumulada (%)", format=".2f")
        )

    def panel(metrics: tuple[str, ...], title: str, domain: list[float] | None, height: int):
        layers: list[alt.TopLevelMixin] = [phase_layer, marker_layer]
        metric_color_scale = (
            alt.Scale(
                domain=[MAIN_METRIC_LABELS[metric] for metric in metrics],
                range=[MAIN_METRIC_COLORS[metric] for metric in metrics],
            )
            if len(metrics) > 1
            else None
        )
        if metrics == ("Peso",):
            weight_data = series["Peso"]
            loss_data = weight_data[weight_data["is_hourly_loss"]].copy()
            weight_data["weight_plot_kg"] = weight_data["value"]
            loss_data["weight_plot_kg"] = loss_data["loss_display_kg"]
            loss_data["metric"] = "Perda acumulada (%)"
            loss_data["metric_label"] = "Perda acumulada (%)"
            layers.extend(
                [
                    (
                        alt.Chart(weight_data)
                        .mark_line(strokeWidth=2.5)
                        .encode(
                            x=x,
                            y=alt.Y(
                                "weight_plot_kg:Q",
                                title="",
                                axis=alt.Axis(
                                    labelColor=MAIN_METRIC_COLORS["Peso"],
                                    labelPadding=2,
                                    tickCount=4,
                                ),
                                scale=alt.Scale(zero=False, nice=True),
                            ),
                            color=alt.value(MAIN_METRIC_COLORS["Peso"]),
                            detail="metric:N",
                            opacity=(
                                alt.condition(focus, alt.value(1), alt.value(0.22))
                                if focus is not None
                                else alt.value(1)
                            ),
                            tooltip=[
                                alt.Tooltip("value:Q", title="Peso atual (kg)", format=".2f"),
                                alt.Tooltip("timestamp:T", title="Data e hora", format="%d/%m/%Y %H:%M"),
                            ],
                        )
                    ),
                    (
                        alt.Chart(loss_data)
                        .mark_line(strokeWidth=2.1, strokeDash=[5, 3])
                        .encode(
                            x=x,
                            y=alt.Y(
                                "weight_plot_kg:Q",
                                title=None,
                                scale=alt.Scale(zero=False, nice=True),
                            ),
                            color=alt.value("#3CAAFB"),
                            detail="metric:N",
                            opacity=(
                                alt.condition(focus, alt.value(1), alt.value(0.22))
                                if focus is not None
                                else alt.value(1)
                            ),
                            tooltip=[
                                alt.Tooltip("loss_pct:Q", title="Perda acumulada (%)", format=".2f"),
                                alt.Tooltip("hour_label:N", title="Hora da fase"),
                            ],
                        )
                    ),
                    (
                        alt.Chart(loss_data)
                        .mark_point(size=48, filled=True, color="#3CAAFB", stroke="white", strokeWidth=0.8)
                        .encode(
                            x=x,
                            y="weight_plot_kg:Q",
                            tooltip=[
                                alt.Tooltip("loss_pct:Q", title="Perda acumulada (%)", format=".2f"),
                                alt.Tooltip("hour_label:N", title="Hora da fase"),
                            ],
                        )
                    ),
                ]
            )
        else:
            if len(metrics) > 1:
                metric_data = pd.concat([series[metric] for metric in metrics], ignore_index=True)
                layers.append(
                    alt.Chart(metric_data)
                    .mark_line()
                    .encode(
                        x=x,
                        y=alt.Y(
                            "value:Q",
                            title=title,
                            scale=alt.Scale(domain=domain, zero=False)
                            if domain
                            else alt.Scale(zero=False),
                        ),
                        color=alt.Color(
                            "metric_label:N",
                            scale=metric_color_scale,
                            legend=alt.Legend(orient="top", title=None),
                        ),
                        detail="metric:N",
                        strokeWidth=alt.StrokeWidth(
                            "metric:N",
                            scale=alt.Scale(
                                domain=list(metrics),
                                range=[3.3 if metric == "Espeto" else 2.4 for metric in metrics],
                            ),
                            legend=None,
                        ),
                        opacity=(
                            alt.condition(focus, alt.value(1), alt.value(0.22))
                            if focus is not None
                            else alt.value(1)
                        ),
                        tooltip=[
                            alt.Tooltip("metric_label:N", title="Variavel"),
                            alt.Tooltip("value:Q", title=title, format=".2f"),
                            alt.Tooltip(
                                "timestamp:T",
                                title="Data e hora",
                                format="%d/%m/%Y %H:%M",
                            ),
                        ],
                    )
                )
            else:
                metric = metrics[0]
                metric_data = series[metric]
                line = (
                    alt.Chart(metric_data)
                    .mark_line(
                        strokeWidth=3.3 if metric == "Espeto" else 2.4,
                        interpolate="step-after" if metric == "Ventilacao" else "linear",
                    )
                    .encode(
                        x=x,
                        y=alt.Y(
                            "value:Q",
                            title=title,
                            scale=alt.Scale(domain=domain, zero=False) if domain else alt.Scale(zero=False),
                        ),
                        color=alt.value(MAIN_METRIC_COLORS[metric]),
                        detail="metric:N",
                        opacity=(
                            alt.condition(focus, alt.value(1), alt.value(0.22))
                            if focus is not None
                            else alt.value(1)
                        ),
                        tooltip=[
                            alt.Tooltip("metric_label:N", title="Variavel"),
                            alt.Tooltip("value:Q", title=MAIN_METRIC_LABELS[metric], format=".2f"),
                            alt.Tooltip("timestamp:T", title="Data e hora", format="%d/%m/%Y %H:%M"),
                        ],
                    )
                )
                layers.append(line)

        if hover is not None:
            layers.append(
                alt.Chart(tooltip_frame)
                .mark_rule(color="#3CAAFB", strokeWidth=1.1)
                .encode(
                    x=x,
                    opacity=alt.condition(hover, alt.value(0.9), alt.value(0)),
                    tooltip=tooltip_fields,
                )
            )
        panel_title = (
            alt.TitleParams(
                text="Peso até 7 °C (kg) · pontos azuis: perda acumulada por hora (%)",
                anchor="start",
                color="#51606F",
                fontSize=12,
                fontWeight="normal",
                offset=5,
            )
            if metrics == ("Peso",)
            else None
        )
        chart = alt.layer(*layers).properties(width=850, height=height)
        if panel_title is not None:
            chart = chart.properties(title=panel_title)
        chart = chart.resolve_scale(color="independent")
        return chart.add_params(hover, focus) if hover is not None and focus is not None else chart

    panels: list[alt.TopLevelMixin] = []
    temperature_metrics = tuple(metric for metric in ("Retorno de ar", "Espeto") if metric in visible)
    if temperature_metrics:
        panels.append(panel(temperature_metrics, "Temperatura (C)", [-10, 50], 170))
    if "Ventilacao" in visible:
        panels.append(panel(("Ventilacao",), "Ventilacao (%)", [0, 100], 125))
    if "Umidade" in visible:
        panels.append(panel(("Umidade",), "Umidade relativa (%)", [92, 100], 125))
    if "Peso" in visible:
        panels.append(panel(("Peso",), "Peso atual (kg)", None, 155))

    return alt.vconcat(*panels, spacing=6).resolve_scale(x="shared", y="independent")


def weight_loss_comparison_chart(
    selected_cycles: list[Cycle],
    data: pd.DataFrame,
    selected_hours: list[str],
) -> alt.TopLevelMixin:
    """Compare minute-level absolute and percentage loss through 7 C."""
    rows: list[pd.DataFrame] = []
    for index, cycle in enumerate(selected_cycles):
        frame = weight_loss_frame(data, cycle)
        frame = frame[frame["hour_label"].isin(selected_hours)].copy()
        if frame["weight_kg"].notna().sum() == 0:
            continue
        frame["Ciclo"] = _cycle_name(index)
        frame["cycle_index"] = index
        rows.append(frame)
    if not rows:
        return _empty_main_chart("Nao ha perda de peso disponivel na janela selecionada.")

    chart_data = pd.concat(rows, ignore_index=True)
    cycle_domain = [_cycle_name(index) for index in range(len(selected_cycles))]
    x = alt.X(
        "hours_from_cycle_start:Q",
        title="Horas desde o inicio do ciclo",
        axis=alt.Axis(tickMinStep=1),
    )
    color = alt.Color(
        "Ciclo:N",
        scale=alt.Scale(domain=cycle_domain, range=CYCLE_COLORS[: len(selected_cycles)]),
        legend=alt.Legend(orient="top", title=None),
    )
    tooltip = [
        alt.Tooltip("Ciclo:N", title="Ciclo"),
        alt.Tooltip("timestamp:T", title="Data e hora", format="%d/%m/%Y %H:%M"),
        alt.Tooltip("phase:N", title="Fase"),
        alt.Tooltip("hour_label:N", title="Hora da fase"),
        alt.Tooltip("weight_kg:Q", title="Peso atual (kg)", format=".2f"),
        alt.Tooltip("loss_kg:Q", title="Perda acumulada (kg)", format=".2f"),
        alt.Tooltip("loss_pct:Q", title="Perda acumulada (%)", format=".2f"),
    ]

    zero = alt.Chart(pd.DataFrame({"zero": [0]})).mark_rule(
        color="#5D6C7B", strokeWidth=1, strokeDash=[4, 3]
    ).encode(y=alt.Y("zero:Q", axis=None))
    percentage = (
        alt.Chart(chart_data)
        .mark_line(strokeWidth=2.6)
        .encode(
            x=x,
            y=alt.Y(
                "loss_pct:Q",
                title="Perda acumulada (%)",
                axis=alt.Axis(titleColor="#142B51"),
                scale=alt.Scale(zero=False, nice=True),
            ),
            color=color,
            detail="Ciclo:N",
            tooltip=tooltip,
        )
    )
    absolute = (
        alt.Chart(chart_data)
        .mark_line(strokeWidth=2.0, strokeDash=[6, 3])
        .encode(
            x=x,
            y=alt.Y(
                "loss_kg:Q",
                title="Perda acumulada (kg)",
                axis=alt.Axis(orient="right", titleColor="#6F4C9B"),
                scale=alt.Scale(zero=False, nice=True),
            ),
            color=color,
            detail="Ciclo:N",
            tooltip=tooltip,
        )
    )
    return (
        alt.layer(zero, percentage, absolute)
        .properties(width=850, height=310)
        .resolve_scale(y="independent")
    )


def _empty_main_chart(message: str) -> alt.Chart:
    return (
        alt.Chart(pd.DataFrame({"message": [message]}))
        .mark_text(align="left", baseline="middle", color="#51606F", fontSize=13)
        .encode(text="message:N")
        .properties(width=760, height=52)
    )


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
    hour_order = (
        chart_data[["phase_order", "phase_hour", "hour_label"]]
        .drop_duplicates()
        .sort_values(["phase_order", "phase_hour"])["hour_label"]
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
    stroke_dash = alt.StrokeDash(
        "Ciclo:N",
        scale=alt.Scale(
            domain=cycle_domain,
            range=CYCLE_DASHES[: len(selected_cycles)],
        ),
        legend=None,
    )
    shape = alt.Shape(
        "Ciclo:N",
        scale=alt.Scale(
            domain=cycle_domain,
            range=CYCLE_SHAPES[: len(selected_cycles)],
        ),
        legend=None,
    )
    opacity = alt.condition(
        alt.datum.partial,
        alt.value(0.48),
        alt.value(0.86),
    )
    tooltip = [
        alt.Tooltip("Ciclo:N", title="Ciclo"),
        alt.Tooltip("phase:N", title="Fase"),
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
            "strokeDash": stroke_dash,
            "detail": "Ciclo:N",
            "tooltip": tooltip,
        }
        line_mark = alt.Chart(chart_data).mark_line(
            strokeWidth=2.6,
            interpolate="step-after" if metric in STEP_LINE_METRICS else "linear",
        )
        lines = line_mark.encode(**line_encoding)
        points = (
            alt.Chart(chart_data)
            .mark_point(
                size=58,
                filled=True,
                strokeWidth=1.2,
            )
            .encode(**line_encoding, shape=shape, opacity=opacity)
        )
        chart = lines + points
    else:
        chart = alt.Chart(chart_data).mark_bar(
            cornerRadiusTopLeft=2,
            cornerRadiusTopRight=2,
        ).encode(**bar_encoding)

    panel_width = max(560, min(880, len(hour_order) * 52))
    matrix = _hourly_value_matrix(
        chart_data,
        hour_order=hour_order,
        cycle_short_domain=cycle_short_domain,
        metric=metric,
        unit=unit,
        width=panel_width,
    )
    return alt.vconcat(
        chart.properties(width=panel_width, height=255),
        matrix,
        spacing=2,
    ).resolve_scale(x="shared")


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
