"""Shared Altair charts for the Streamlit dashboard and PDF report."""

from __future__ import annotations

import math

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
    "DT_atual": "#B65C8A",
}
MAIN_METRIC_LABELS = {
    "Retorno de ar": "Retorno do ar",
    "Espeto": "Espeto",
    "Ventilacao": "Ventilacao",
    "Umidade": "Umidade relativa",
    "Peso": "Peso atual",
    "DT_atual": "DT Atual",
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

    loss = weight_loss_frame(data, cycle)[
        ["timestamp", "loss_kg", "loss_pct", "is_reference", "is_target"]
    ].set_index("timestamp")
    for column in ("loss_kg", "loss_pct", "is_reference", "is_target"):
        result[column] = result["timestamp"].map(loss[column])

    result["weight_trend_kg"] = (
        result["weight_kg"]
        .rolling(window=5, center=True, min_periods=1)
        .median()
        .where(result["weight_kg"].notna())
    )
    result["weight_event_label"] = pd.NA
    reference_mask = result["is_reference"].fillna(False) & result["weight_kg"].notna()
    target_mask = result["is_target"].fillna(False) & result["weight_kg"].notna()
    result.loc[reference_mask, "weight_event_label"] = result.loc[
        reference_mask, "weight_kg"
    ].map(lambda value: f"Referência {value:.1f} kg")
    result.loc[target_mask, "weight_event_label"] = result.loc[
        target_mask, ["weight_kg", "loss_pct"]
    ].apply(
        lambda row: (
            f"Aos 7 °C {row['weight_kg']:.1f} kg · perda {row['loss_pct']:.2f}%"
        ).replace(".", ","),
        axis=1,
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

    chart_metrics = visible + (("DT_atual",) if "Ventilacao" in visible else ())
    series = {
        metric: _main_metric_frame(data, active_cycle, metric).loc[
            lambda frame: frame["hour_label"].isin(selected_hours)
        ].copy()
        for metric in chart_metrics
    }
    tooltip_frame = _main_tooltip_frame(data, active_cycle, chart_metrics, selected_hours)
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
    x_tick_max = max(1, math.ceil(float(base["hours_from_cycle_start"].max())))
    x_domain_max = x_tick_max + 0.75
    x = alt.X(
        "hours_from_cycle_start:Q",
        title="Horas desde o inicio do ciclo",
        axis=alt.Axis(tickMinStep=1, values=list(range(x_tick_max + 1))),
        scale=alt.Scale(domain=[0, x_domain_max], nice=False),
    )
    phase_layer = _phase_background(base)
    marker_layer = _phase_markers(base)
    tooltip_fields = [
        alt.Tooltip("timestamp:T", title="Data e hora", format="%d/%m/%Y %H:%M"),
        alt.Tooltip("phase:N", title="Fase"),
        alt.Tooltip("hour_label:N", title="Hora da fase"),
    ]
    for metric in chart_metrics:
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
        weight_panel_title: str | None = None
        metric_color_scale = (
            alt.Scale(
                domain=[MAIN_METRIC_LABELS[metric] for metric in metrics],
                range=[MAIN_METRIC_COLORS[metric] for metric in metrics],
            )
            if len(metrics) > 1
            else None
        )
        if metrics == ("Ventilacao", "DT_atual"):
            ventilation_data = series["Ventilacao"]
            dt_data = series["DT_atual"]
            layers.extend(
                [
                    (
                        alt.Chart(ventilation_data)
                        .mark_line(strokeWidth=2.4, interpolate="step-after")
                        .encode(
                            x=x,
                            y=alt.Y(
                                "value:Q",
                                title="Ventilacao (%)",
                                scale=alt.Scale(domain=[0, 100], zero=True),
                                axis=alt.Axis(
                                    titleColor=MAIN_METRIC_COLORS["Ventilacao"],
                                    labelColor=MAIN_METRIC_COLORS["Ventilacao"],
                                ),
                            ),
                            color=alt.value(MAIN_METRIC_COLORS["Ventilacao"]),
                            tooltip=[
                                alt.Tooltip("value:Q", title="Ventilacao (%)", format=".2f"),
                                alt.Tooltip(
                                    "timestamp:T",
                                    title="Data e hora",
                                    format="%d/%m/%Y %H:%M",
                                ),
                            ],
                        )
                    ),
                    (
                        alt.Chart(dt_data)
                        .mark_line(strokeWidth=2.2)
                        .encode(
                            x=x,
                            y=alt.Y(
                                "value:Q",
                                title=None,
                                scale=alt.Scale(zero=False, nice=True),
                                axis=alt.Axis(
                                    orient="right",
                                    labelColor=MAIN_METRIC_COLORS["DT_atual"],
                                    labelAlign="right",
                                    labelPadding=-8,
                                    labelExpr="datum.label + ' °C'",
                                ),
                            ),
                            color=alt.Color(
                                "metric_label:N",
                                scale=alt.Scale(
                                    domain=[
                                        MAIN_METRIC_LABELS["Ventilacao"],
                                        MAIN_METRIC_LABELS["DT_atual"],
                                    ],
                                    range=[
                                        MAIN_METRIC_COLORS["Ventilacao"],
                                        MAIN_METRIC_COLORS["DT_atual"],
                                    ],
                                ),
                                legend=alt.Legend(orient="top", title=None),
                            ),
                            tooltip=[
                                alt.Tooltip("value:Q", title="DT Atual (°C)", format=".2f"),
                                alt.Tooltip(
                                    "timestamp:T",
                                    title="Data e hora",
                                    format="%d/%m/%Y %H:%M",
                                ),
                            ],
                        )
                    ),
                ]
            )
        elif metrics == ("Peso",):
            weight_data = series["Peso"]
            reference_data = weight_data[
                weight_data["is_reference"].fillna(False) & weight_data["weight_kg"].notna()
            ].copy()
            target_data = weight_data[
                weight_data["is_target"].fillna(False) & weight_data["weight_kg"].notna()
            ].copy()
            weight_panel_title = "Peso medido até 7 °C (kg) · escala ampliada"
            if not target_data.empty and target_data["loss_kg"].notna().any():
                loss_kg = float(target_data["loss_kg"].dropna().iloc[-1])
                loss_pct = float(target_data["loss_pct"].dropna().iloc[-1])
                loss_label = f"{loss_kg:.2f} kg ({loss_pct:.2f}%)".replace(".", ",")
                weight_panel_title += f" · perda: {loss_label}"
            else:
                weight_panel_title += " · sem peso válido no instante de 7 °C"
            layers.extend(
                [
                    (
                        alt.Chart(weight_data)
                        .mark_line(strokeWidth=1.0, opacity=0.32)
                        .encode(
                            x=x,
                            y=alt.Y(
                                "weight_kg:Q",
                                title="Peso (kg)",
                                axis=alt.Axis(
                                    labelColor=MAIN_METRIC_COLORS["Peso"],
                                    labelPadding=2,
                                    tickCount=5,
                                ),
                                scale=alt.Scale(zero=False, nice=True),
                            ),
                            color=alt.value(MAIN_METRIC_COLORS["Peso"]),
                            tooltip=[
                                alt.Tooltip("weight_kg:Q", title="Peso bruto (kg)", format=".2f"),
                                alt.Tooltip("timestamp:T", title="Data e hora", format="%d/%m/%Y %H:%M"),
                            ],
                        )
                    ),
                    (
                        alt.Chart(weight_data)
                        .mark_line(strokeWidth=2.7)
                        .encode(
                            x=x,
                            y=alt.Y(
                                "weight_trend_kg:Q",
                                title=None,
                                axis=None,
                                scale=alt.Scale(zero=False, nice=True),
                            ),
                            color=alt.value(MAIN_METRIC_COLORS["Peso"]),
                            opacity=(
                                alt.condition(focus, alt.value(1), alt.value(0.22))
                                if focus is not None
                                else alt.value(1)
                            ),
                            tooltip=[
                                alt.Tooltip(
                                    "weight_trend_kg:Q",
                                    title="Tendência 5 min (kg)",
                                    format=".2f",
                                ),
                                alt.Tooltip("timestamp:T", title="Data e hora", format="%d/%m/%Y %H:%M"),
                            ],
                        )
                    ),
                    (
                        alt.Chart(reference_data)
                        .mark_point(
                            size=90,
                            filled=True,
                            color=MAIN_METRIC_COLORS["Retorno de ar"],
                            stroke="white",
                            strokeWidth=1.2,
                        )
                        .encode(
                            x=x,
                            y="weight_kg:Q",
                            tooltip=[
                                alt.Tooltip("weight_event_label:N", title="Marco"),
                                alt.Tooltip("timestamp:T", title="Data e hora", format="%d/%m/%Y %H:%M"),
                            ],
                        )
                    ),
                    (
                        alt.Chart(reference_data)
                        .mark_text(
                            align="left",
                            dx=8,
                            dy=-12,
                            color=MAIN_METRIC_COLORS["Retorno de ar"],
                            fontSize=11,
                        )
                        .encode(x=x, y="weight_kg:Q", text="weight_event_label:N")
                    ),
                    (
                        alt.Chart(target_data)
                        .mark_point(
                            size=90,
                            filled=True,
                            color=MAIN_METRIC_COLORS["Espeto"],
                            stroke="white",
                            strokeWidth=1.2,
                        )
                        .encode(
                            x=x,
                            y="weight_kg:Q",
                            tooltip=[
                                alt.Tooltip("weight_event_label:N", title="Marco"),
                                alt.Tooltip("loss_kg:Q", title="Perda (kg)", format=".2f"),
                                alt.Tooltip("loss_pct:Q", title="Perda (%)", format=".2f"),
                                alt.Tooltip("timestamp:T", title="Data e hora", format="%d/%m/%Y %H:%M"),
                            ],
                        )
                    ),
                    (
                        alt.Chart(target_data)
                        .mark_text(
                            align="right",
                            dx=-8,
                            dy=14,
                            color=MAIN_METRIC_COLORS["Espeto"],
                            fontSize=11,
                        )
                        .encode(x=x, y="weight_kg:Q", text="weight_event_label:N")
                    ),
                ]
            )
            post_target_rows = weight_data[weight_data["phase"].eq(PHASE_POST_TARGET)]
            if not post_target_rows.empty:
                target_hour = float(post_target_rows["hours_from_cycle_start"].min())
                visible_end = float(weight_data["hours_from_cycle_start"].max())
                weight_values = weight_data["weight_kg"].dropna()
                if visible_end > target_hour and not weight_values.empty:
                    post_target_note = pd.DataFrame(
                        {
                            "hours_from_cycle_start": [min(target_hour + 0.6, visible_end)],
                            "weight_kg": [float(weight_values.median())],
                            "label": ["Peso não considerado após 7 °C"],
                        }
                    )
                    layers.append(
                        alt.Chart(post_target_note)
                        .mark_text(
                            align="left",
                            color="#6B7785",
                            fontSize=11,
                            fontStyle="italic",
                        )
                        .encode(x=x, y="weight_kg:Q", text="label:N")
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
                text=weight_panel_title,
                anchor="start",
                color="#51606F",
                fontSize=12,
                fontWeight="normal",
                offset=5,
                subtitle="Linha fina: leitura bruta · linha forte: tendência mediana de 5 min",
                subtitleColor="#6B7785",
                subtitleFontSize=10,
            )
            if weight_panel_title is not None
            else None
        )
        chart = alt.layer(*layers).properties(width=760, height=height)
        if panel_title is not None:
            chart = chart.properties(title=panel_title)
        chart = (
            chart.resolve_scale(color="independent", y="independent")
            if metrics == ("Ventilacao", "DT_atual")
            else chart.resolve_scale(color="independent")
        )
        return chart.add_params(hover, focus) if hover is not None and focus is not None else chart

    panels: list[alt.TopLevelMixin] = []
    temperature_metrics = tuple(metric for metric in ("Retorno de ar", "Espeto") if metric in visible)
    if temperature_metrics:
        panels.append(panel(temperature_metrics, "Temperatura (C)", [-10, 50], 170))
    if "Ventilacao" in visible:
        panels.append(panel(("Ventilacao", "DT_atual"), "Ventilacao (%)", [0, 100], 140))
    if "Umidade" in visible:
        panels.append(panel(("Umidade",), "Umidade relativa (%)", [92, 100], 125))
    if "Peso" in visible:
        panels.append(panel(("Peso",), "Peso atual (kg)", None, 180))

    return alt.vconcat(*panels, spacing=6, padding={"right": 65}).resolve_scale(
        x="shared",
        y="independent",
    )


def weight_loss_comparison_chart(
    selected_cycles: list[Cycle],
    data: pd.DataFrame,
    selected_hours: list[str],
) -> alt.TopLevelMixin:
    """Compare minute-level percentage loss through 7 C."""
    rows: list[pd.DataFrame] = []
    for index, cycle in enumerate(selected_cycles):
        frame = weight_loss_frame(data, cycle)
        frame = frame[frame["hour_label"].isin(selected_hours)].copy()
        frame = frame[frame["loss_pct"].notna()].copy()
        if frame.empty:
            continue
        frame["Ciclo"] = _cycle_name(index)
        frame["cycle_index"] = index
        rows.append(frame)
    if not rows:
        return _empty_main_chart("Nao ha perda de peso disponivel na janela selecionada.")

    chart_data = pd.concat(rows, ignore_index=True)
    max_hour = float(chart_data["hours_from_cycle_start"].max())
    max_loss = max(0.0, float(chart_data["loss_pct"].max()))
    min_loss = min(0.0, float(chart_data["loss_pct"].min()))
    loss_span = max(max_loss - min_loss, 0.1)
    x_domain = [0.0, max_hour + max(0.5, max_hour * 0.03)]
    y_domain = [
        min_loss - loss_span * 0.08 if min_loss < 0 else 0.0,
        max_loss + loss_span * 0.18,
    ]
    cycle_domain = [_cycle_name(index) for index in range(len(selected_cycles))]
    x = alt.X(
        "hours_from_cycle_start:Q",
        title="Horas desde o inicio do ciclo",
        axis=alt.Axis(tickMinStep=1),
        scale=alt.Scale(domain=x_domain, zero=True, nice=False),
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
                scale=alt.Scale(domain=y_domain, zero=True, nice=False),
            ),
            color=color,
            detail="Ciclo:N",
            tooltip=tooltip,
        )
    )

    target_data = chart_data[
        chart_data["is_target"].fillna(False)
        & chart_data["loss_kg"].notna()
        & chart_data["loss_pct"].notna()
    ].copy()
    target_data["end_label"] = target_data.apply(
        lambda row: (
            f"{row['Ciclo']} · {row['loss_pct']:.2f}% ({row['loss_kg']:.2f} kg)"
        ).replace(".", ","),
        axis=1,
    )
    target_points = (
        alt.Chart(target_data)
        .mark_point(size=95, filled=True, stroke="white", strokeWidth=1.2)
        .encode(
            x=x,
            y=alt.Y("loss_pct:Q"),
            color=color,
            tooltip=tooltip,
        )
    )

    label_layers: list[alt.Chart] = []
    centered_offset = (len(selected_cycles) - 1) / 2
    for index, cycle_name in enumerate(cycle_domain):
        cycle_target = target_data[target_data["Ciclo"].eq(cycle_name)]
        if cycle_target.empty:
            continue
        label_layers.append(
            alt.Chart(cycle_target)
            .mark_text(
                align="right",
                baseline="middle",
                dx=-8,
                dy=(
                    -12
                    if len(selected_cycles) == 1
                    else int((index - centered_offset) * 18)
                ),
                fontSize=11,
                fontWeight=500,
            )
            .encode(
                x=x,
                y=alt.Y("loss_pct:Q"),
                text=alt.Text("end_label:N"),
                color=alt.value(CYCLE_COLORS[index]),
            )
        )

    return (
        alt.layer(zero, percentage, target_points, *label_layers)
        .properties(width=850, height=310)
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
