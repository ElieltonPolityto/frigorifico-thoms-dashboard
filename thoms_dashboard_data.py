"""Leitura e validacao dos ciclos de resfriamento do Frigorifico Thoms."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {
    "Espeto": "Temperatuda espeto",
    "DT_ref": "DT ref",
    "Umidade": "Umidade relativa da camara",
    "Ventilacao": "Saida Y1 - Ventiladores EC",
    "Glicol": "Temp entrada glicol",
    "Peso": "Peso atual",
    "Retorno de ar": "Temp retorno ar",
}
AUXILIARY_COLUMNS = {
    "DT_atual": "DT Atual",
}
METRIC_COLUMNS = {**REQUIRED_COLUMNS, **AUXILIARY_COLUMNS}

DATA_COMPLETENESS_MIN = 0.95
MAX_CONTINUOUS_GAP_MINUTES = 5
MIN_VALID_WEIGHT_KG = 50.0
MAX_VALID_WEIGHT_KG = 300.0
MAX_WEIGHT_STEP_KG_PER_MINUTE = 5.0
OPERATIONAL_CYCLE_CUTOFF_HOUR = 11
WEEKDAY_ABBREVIATIONS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
TARGET_ESPETO_C = 7.0
PARTIAL_HOUR_MINUTES = 45.0
PHASE_LOADING = "Carregamento"
PHASE_TO_TARGET = "Resfriamento até a meta"
PHASE_POST_TARGET = "Resfriamento pós-meta"
PHASE_ORDER = (PHASE_LOADING, PHASE_TO_TARGET, PHASE_POST_TARGET)
PHASE_PREFIX = {
    PHASE_LOADING: "C",
    PHASE_TO_TARGET: "R",
    PHASE_POST_TARGET: "P",
}


@dataclass(frozen=True)
class Cycle:
    """A cycle that passed the source-data quality rules."""

    start_index: int
    cooling_index: int
    end_index: int
    label: str


@dataclass(frozen=True)
class WeightQuality:
    """Quality result for the weight-loss window of one cycle."""

    suspect: bool
    events: tuple[pd.Timestamp, ...]
    max_step_kg: float | None


def _first_time_at_or_below_7(frame: pd.DataFrame, cooling_start: pd.Timestamp) -> pd.Timestamp | None:
    """Return the first espeto sample at or below 7 C during cooling."""
    espeto = frame[REQUIRED_COLUMNS["Espeto"]]
    reached = frame.loc[
        (frame["timestamp"] >= cooling_start) & (espeto <= TARGET_ESPETO_C),
        "timestamp",
    ]
    return None if reached.empty else reached.iloc[0]


def valid_weight_series(frame: pd.DataFrame) -> pd.Series:
    """Return valid process-weight readings without mutating raw data."""
    weight = frame[REQUIRED_COLUMNS["Peso"]]
    return weight.where(
        (weight > MIN_VALID_WEIGHT_KG) & (weight <= MAX_VALID_WEIGHT_KG)
    )


def _initial_loaded_weight(frame: pd.DataFrame) -> pd.Series:
    """Backward-compatible internal alias for valid process-weight readings."""
    return valid_weight_series(frame)


def _weight_reference_after_loading_peak(
    frame: pd.DataFrame,
    cooling_start: pd.Timestamp,
) -> tuple[pd.Timestamp, float] | None:
    """Use the valid weight exactly five minutes after the loading-phase peak."""
    valid_weight = _initial_loaded_weight(frame)
    loading_weights = valid_weight.where(frame["timestamp"] < cooling_start).dropna()
    if loading_weights.empty:
        return None

    peak_index = loading_weights.idxmax()
    reference_time = frame.at[peak_index, "timestamp"] + pd.Timedelta(minutes=5)
    reference = valid_weight.where(frame["timestamp"] == reference_time).dropna()
    if reference.empty:
        return None
    return reference_time, float(reference.iloc[0])


def _weight_at_7_c(frame: pd.DataFrame, reached_7_time: pd.Timestamp) -> float | None:
    """Return the valid scale sample at the first espeto reading at or below 7 C."""
    valid_weight = _initial_loaded_weight(frame)
    at_target = valid_weight.where(frame["timestamp"] == reached_7_time).dropna()
    return None if at_target.empty else float(at_target.iloc[0])


def _read_daily_csv(path: Path) -> pd.DataFrame:
    """Read one BOSS/Full Gauge daily export, whose header starts on line six."""
    last_error: UnicodeDecodeError | None = None
    for encoding in ("cp1252", "latin1", "utf-8-sig"):
        try:
            frame = pd.read_csv(path, sep=";", skiprows=5, encoding=encoding)
            break
        except UnicodeDecodeError as error:
            last_error = error
    else:
        raise last_error or ValueError(f"Unable to read {path.name}")

    frame = frame.iloc[:, :15].copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    frame = frame.rename(columns={frame.columns[0]: "timestamp"})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame["_source_mtime"] = path.stat().st_mtime
    return frame.dropna(subset=["timestamp"])


def _bridge_short_off_periods(values: pd.Series, timestamps: pd.Series) -> pd.Series:
    """Treat OFF interruptions of up to five minutes between ON states as noise."""
    result = values.to_numpy(dtype=bool).copy()
    time_values = timestamps.to_numpy()
    position = 0

    while position < len(result):
        if result[position]:
            position += 1
            continue

        end = position
        while end < len(result) and not result[end]:
            end += 1

        if position > 0 and end < len(result) and result[position - 1] and result[end]:
            duration = pd.Timestamp(time_values[end - 1]) - pd.Timestamp(time_values[position])
            if duration <= pd.Timedelta(minutes=MAX_CONTINUOUS_GAP_MINUTES):
                result[position:end] = True
        position = end

    return pd.Series(result, index=values.index)


def load_supervision_data(data_folder: Path) -> pd.DataFrame:
    """Consolidate daily CSVs, preferring the most recently modified duplicate."""
    csv_files = sorted(data_folder.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"Nenhum CSV encontrado em {data_folder}")

    frames = [_read_daily_csv(path) for path in csv_files]
    data = pd.concat(frames, ignore_index=True)
    data = (
        data.sort_values(["timestamp", "_source_mtime"])
        .drop_duplicates(subset="timestamp", keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    required = set(METRIC_COLUMNS.values()) | {"Carregamento", "Resfriamento"}
    missing_columns = sorted(required - set(data.columns))
    if missing_columns:
        raise ValueError(f"Colunas obrigatorias ausentes: {', '.join(missing_columns)}")

    for column in METRIC_COLUMNS.values():
        data[column] = pd.to_numeric(
            data[column]
            .astype(str)
            .str.strip()
            .replace({"---": np.nan, "": np.nan})
            .str.replace(",", ".", regex=False),
            errors="coerce",
        )

    for state_column in ("Carregamento", "Resfriamento"):
        raw_state = data[state_column].astype(str).str.strip().str.upper().eq("ON")
        data[f"{state_column}_active"] = _bridge_short_off_periods(raw_state, data["timestamp"])

    return data




def _cycle_is_valid(frame: pd.DataFrame, cooling_index: int, end_index: int) -> bool:
    """Apply the agreed completeness and boundary checks to one candidate cycle."""
    cadence = frame["timestamp"].diff().dropna().median()
    max_gap = frame["timestamp"].diff().max()
    allowed_gap = max(pd.Timedelta(minutes=MAX_CONTINUOUS_GAP_MINUTES), cadence * 5)
    if pd.isna(cadence) or max_gap > allowed_gap:
        return False

    if frame[list(REQUIRED_COLUMNS.values())].notna().mean().min() < DATA_COMPLETENESS_MIN:
        return False

    weights = _initial_loaded_weight(frame).dropna()
    if weights.empty:
        return False

    return cooling_index > 0 and end_index > cooling_index


def detect_valid_cycles(data: pd.DataFrame) -> list[Cycle]:
    """Detect Monday-Friday complete cycles from loading-to-next-loading windows."""
    loading = data["Carregamento_active"]
    starts = data.index[loading & ~loading.shift(fill_value=False)].tolist()
    cycles: list[Cycle] = []

    for start_index, next_start_index in zip(starts, starts[1:]):
        start_time = data.at[start_index, "timestamp"]
        if start_time.weekday() >= 5:
            continue

        next_start_time = data.at[next_start_index, "timestamp"]
        operational_cutoff = start_time.normalize() + pd.Timedelta(days=1, hours=OPERATIONAL_CYCLE_CUTOFF_HOUR)
        if next_start_time > operational_cutoff:
            eligible_end = data.index[(data["timestamp"] <= operational_cutoff) & (data.index >= start_index)]
            if len(eligible_end) == 0:
                continue
            end_index = int(eligible_end[-1])
        else:
            end_index = next_start_index - 1

        candidate = data.iloc[start_index : end_index + 1].copy()
        cooling_rows = candidate.index[candidate["Resfriamento_active"]]
        if cooling_rows.empty:
            continue

        cooling_index = int(cooling_rows[0])
        if cooling_index <= start_index or end_index <= cooling_index:
            continue
        if not _cycle_is_valid(candidate, cooling_index - start_index, end_index - start_index):
            continue

        end_time = data.at[end_index, "timestamp"]
        label = (
            f"{start_time:%d/%m/%Y} ({WEEKDAY_ABBREVIATIONS[start_time.weekday()]})"
            f" - {end_time:%d/%m/%Y} ({WEEKDAY_ABBREVIATIONS[end_time.weekday()]})"
        )
        cycles.append(Cycle(start_index, cooling_index, end_index, label))

    return cycles


def _cycle_base_frame(data: pd.DataFrame, cycle: Cycle) -> pd.DataFrame:
    """Return one cycle annotated with elapsed time and its three phases."""
    frame = data.iloc[cycle.start_index : cycle.end_index + 1].copy()
    start_time = frame["timestamp"].iloc[0]
    cooling_time = data.at[cycle.cooling_index, "timestamp"]
    reached_7_time = _first_time_at_or_below_7(frame, cooling_time)
    frame["hours_from_cycle_start"] = (
        frame["timestamp"] - start_time
    ).dt.total_seconds() / 3600
    frame["phase"] = PHASE_TO_TARGET
    frame.loc[frame["timestamp"] < cooling_time, "phase"] = PHASE_LOADING
    if reached_7_time is not None:
        frame.loc[frame["timestamp"] >= reached_7_time, "phase"] = PHASE_POST_TARGET

    phase_starts = {
        PHASE_LOADING: start_time,
        PHASE_TO_TARGET: cooling_time,
        PHASE_POST_TARGET: reached_7_time,
    }
    frame["phase_start"] = frame["phase"].map(phase_starts)
    frame["hours_from_phase_start"] = (
        frame["timestamp"] - pd.to_datetime(frame["phase_start"])
    ).dt.total_seconds() / 3600
    frame["phase_hour"] = np.floor(frame["hours_from_phase_start"]).astype(int)
    frame["hour_label"] = (
        frame["phase"].map(PHASE_PREFIX) + frame["phase_hour"].astype(str)
    )

    return frame


def weight_loss_frame(data: pd.DataFrame, cycle: Cycle) -> pd.DataFrame:
    """Return minute-level weight loss from the reference sample through 7 C."""
    frame = _cycle_base_frame(data, cycle)
    cooling_time = data.at[cycle.cooling_index, "timestamp"]
    reached_7_time = _first_time_at_or_below_7(frame, cooling_time)
    reference = _weight_reference_after_loading_peak(frame, cooling_time)

    frame["weight_kg"] = np.nan
    frame["loss_kg"] = np.nan
    frame["loss_pct"] = np.nan
    frame["is_reference"] = False
    frame["is_target"] = False

    if reference is None or reached_7_time is None:
        return frame

    reference_time, reference_weight = reference
    valid_weight = _initial_loaded_weight(frame)
    within_loss_window = frame["timestamp"].between(reference_time, reached_7_time)
    frame["weight_kg"] = valid_weight.where(within_loss_window)
    frame["loss_kg"] = reference_weight - frame["weight_kg"]
    frame["loss_pct"] = frame["loss_kg"] / reference_weight * 100
    frame["is_reference"] = frame["timestamp"].eq(reference_time)
    frame["is_target"] = frame["timestamp"].eq(reached_7_time)
    return frame


def cycle_weight_quality(data: pd.DataFrame, cycle: Cycle) -> WeightQuality:
    """Flag abrupt consecutive-minute weight changes in the loss window."""
    loss_frame = weight_loss_frame(data, cycle)
    valid = loss_frame.dropna(subset=["weight_kg"])[["timestamp", "weight_kg"]].copy()
    if valid.empty:
        return WeightQuality(False, (), None)

    steps = valid["weight_kg"].diff().abs()
    consecutive_minutes = valid["timestamp"].diff().eq(pd.Timedelta(minutes=1))
    abrupt = consecutive_minutes & steps.gt(MAX_WEIGHT_STEP_KG_PER_MINUTE)
    events = tuple(pd.Timestamp(value) for value in valid.loc[abrupt, "timestamp"])
    max_step = steps[consecutive_minutes].max()
    return WeightQuality(
        suspect=bool(events),
        events=events,
        max_step_kg=None if pd.isna(max_step) else float(max_step),
    )


def cycle_frame(data: pd.DataFrame, cycle: Cycle, metric: str) -> pd.DataFrame:
    """Return one cycle with phase and hourly labels for a selected dashboard metric."""
    source_column = METRIC_COLUMNS[metric]
    frame = _cycle_base_frame(data, cycle)

    if metric == "Peso":
        loss_frame = weight_loss_frame(data, cycle)
        frame["value"] = loss_frame["loss_pct"]
        frame["unit"] = "% de perda acumulada"
    else:
        frame["value"] = frame[source_column]
        frame["unit"] = {
            "Espeto": "°C",
            "DT_ref": "°C",
            "DT_atual": "°C",
            "Umidade": "%",
            "Ventilacao": "%",
            "Glicol": "°C",
            "Retorno de ar": "°C",
        }[metric]

    return frame


def hourly_phase_summary(
    data: pd.DataFrame,
    cycle: Cycle,
    metric: str,
) -> pd.DataFrame:
    """Aggregate one metric by phase-relative hour with observed coverage."""
    frame = cycle_frame(data, cycle, metric).dropna(subset=["value"]).copy()
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "phase",
                "phase_order",
                "phase_hour",
                "hour_label",
                "value",
                "coverage_minutes",
                "partial",
                "unit",
            ]
        )

    cadence = frame["timestamp"].diff().dropna().median()
    cadence_minutes = (
        cadence.total_seconds() / 60
        if pd.notna(cadence) and cadence > pd.Timedelta(0)
        else 1.0
    )

    rows: list[dict[str, object]] = []
    grouped = frame.groupby(["phase", "phase_hour", "hour_label"], sort=False)
    for (phase, phase_hour, hour_label), group in grouped:
        observed_span = (
            group["timestamp"].max() - group["timestamp"].min()
        ).total_seconds() / 60
        coverage_minutes = min(60.0, observed_span + cadence_minutes)
        rows.append(
            {
                "phase": phase,
                "phase_order": PHASE_ORDER.index(phase),
                "phase_hour": int(phase_hour),
                "hour_label": hour_label,
                "value": float(group["value"].mean()),
                "coverage_minutes": coverage_minutes,
                "partial": coverage_minutes < PARTIAL_HOUR_MINUTES,
                "unit": str(group["unit"].iloc[0]),
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values(["phase_order", "phase_hour"])
        .reset_index(drop=True)
    )


def cycle_metrics(
    data: pd.DataFrame,
    cycle: Cycle,
) -> dict[str, float | str | bool | None]:
    """Calculate KPIs from the technical weight-reference rule."""
    frame = data.iloc[cycle.start_index : cycle.end_index + 1].copy()
    cooling_start = data.at[cycle.cooling_index, "timestamp"]
    espeto = frame[REQUIRED_COLUMNS["Espeto"]]
    reached_7_time = _first_time_at_or_below_7(frame, cooling_start)
    initial_espeto = espeto.where(espeto > 35).dropna()

    reference = _weight_reference_after_loading_peak(frame, cooling_start)
    initial_weight = reference[1] if reference is not None else None
    final_weight = None
    if reached_7_time is not None:
        final_weight = _weight_at_7_c(frame, reached_7_time)
    cooling_duration = (
        frame["timestamp"].iloc[-1] - cooling_start
    ).total_seconds() / 3600
    cooling_to_target_duration = (
        (reached_7_time - cooling_start).total_seconds() / 3600
        if reached_7_time is not None
        else cooling_duration
    )
    post_target_duration = (
        (frame["timestamp"].iloc[-1] - reached_7_time).total_seconds() / 3600
        if reached_7_time is not None
        else None
    )
    loss = (
        (initial_weight - final_weight) / initial_weight * 100
        if initial_weight is not None and final_weight is not None
        else None
    )
    loss_kg = (
        initial_weight - final_weight
        if initial_weight is not None and final_weight is not None
        else None
    )
    weight_quality = cycle_weight_quality(data, cycle)
    return {
        "Duracao carga": (cooling_start - frame["timestamp"].iloc[0]).total_seconds() / 3600,
        "Duracao resfriamento": cooling_duration,
        "Duracao ate meta": cooling_to_target_duration,
        "Duracao pos meta": post_target_duration,
        "Peso referencia": initial_weight,
        "Peso inicial": initial_weight,
        "Hora referencia peso": reference[0] if reference is not None else None,
        "Peso final": final_weight,
        "Perda": loss,
        "Perda absoluta": loss_kg,
        "Peso suspeito": weight_quality.suspect,
        "Eventos peso suspeito": len(weight_quality.events),
        "Maior salto peso": weight_quality.max_step_kg,
        "Espeto inicial": float(initial_espeto.iloc[0]) if not initial_espeto.empty else None,
        "Espeto final": float(espeto.dropna().iloc[-1]),
        "Tempo ate 7 C": (
            (reached_7_time - cooling_start).total_seconds() / 3600 if reached_7_time is not None else "Nao atingiu"
        ),
        "DT_ref medio": float(frame[REQUIRED_COLUMNS["DT_ref"]].mean()),
    }


def rank_cycles(
    data: pd.DataFrame,
    cycles: list[Cycle],
) -> pd.DataFrame:
    """Rank eligible cycles by equal-weight normalized time and weight loss."""
    rows: list[dict[str, object]] = []
    for cycle in cycles:
        metrics = cycle_metrics(data, cycle)
        time_to_target = metrics["Tempo ate 7 C"]
        loss = metrics["Perda"]
        if (
            not isinstance(time_to_target, (int, float))
            or loss is None
            or pd.isna(loss)
            or loss < 0
            or bool(metrics["Peso suspeito"])
        ):
            continue
        rows.append(
            {
                "label": cycle.label,
                "time_to_target": float(time_to_target),
                "weight_loss": float(loss),
            }
        )

    ranking = pd.DataFrame(rows)
    if ranking.empty:
        return ranking.assign(score=pd.Series(dtype=float), rank=pd.Series(dtype=int))

    def normalized(series: pd.Series) -> pd.Series:
        span = series.max() - series.min()
        if span == 0:
            return pd.Series(0.0, index=series.index)
        return (series - series.min()) / span

    ranking["time_score"] = normalized(ranking["time_to_target"])
    ranking["loss_score"] = normalized(ranking["weight_loss"])
    ranking["score"] = (ranking["time_score"] + ranking["loss_score"]) / 2
    ranking = ranking.sort_values(
        ["score", "time_to_target", "weight_loss", "label"]
    ).reset_index(drop=True)
    ranking["rank"] = ranking.index + 1
    return ranking


def selection_insights(
    data: pd.DataFrame,
    selected_cycles: list[Cycle],
    ranking: pd.DataFrame,
) -> list[str]:
    """Return deterministic, non-causal observations for the selected cycles."""
    records: list[dict[str, object]] = []
    for index, cycle in enumerate(selected_cycles):
        metrics = cycle_metrics(data, cycle)
        records.append(
            {
                "name": f"Ciclo {index + 1}",
                "label": cycle.label,
                **metrics,
            }
        )

    insights: list[str] = []
    reached = [
        record
        for record in records
        if isinstance(record["Tempo ate 7 C"], (int, float))
    ]
    valid_loss = [
        record
        for record in records
        if (
            isinstance(record["Perda"], (int, float))
            and record["Perda"] >= 0
            and not bool(record["Peso suspeito"])
        )
    ]

    if reached:
        fastest = min(reached, key=lambda record: float(record["Tempo ate 7 C"]))
        insights.append(
            f'{fastest["name"]} atingiu 7 °C mais rapidamente '
            f'({float(fastest["Tempo ate 7 C"]):.1f} h).'
        )
    if valid_loss:
        lowest_loss = min(valid_loss, key=lambda record: float(record["Perda"]))
        insights.append(
            f'{lowest_loss["name"]} apresentou a menor perda de peso válida '
            f'({float(lowest_loss["Perda"]):.2f}%).'
        )

    selected_labels = {cycle.label for cycle in selected_cycles}
    selected_ranking = ranking[ranking["label"].isin(selected_labels)]
    if not selected_ranking.empty:
        best_label = str(selected_ranking.iloc[0]["label"])
        best_index = next(
            index
            for index, cycle in enumerate(selected_cycles)
            if cycle.label == best_label
        )
        insights.append(
            f"Ciclo {best_index + 1} teve o melhor equilíbrio 50/50 "
            "entre tempo até 7 °C e perda de peso."
        )

    for metric_key, label in (
        ("Duracao carga", "carregamento"),
        ("Duracao ate meta", "resfriamento até a meta"),
        ("Duracao pos meta", "resfriamento pós-meta"),
    ):
        values = [
            float(record[metric_key])
            for record in records
            if isinstance(record[metric_key], (int, float))
        ]
        if len(values) >= 2 and max(values) - min(values) >= 1:
            insights.append(
                f"A duração de {label} variou {max(values) - min(values):.1f} h "
                "entre os ciclos selecionados."
            )

    invalid_loss_names = [
        str(record["name"])
        for record in records
        if isinstance(record["Perda"], (int, float)) and record["Perda"] < 0
    ]
    if invalid_loss_names:
        insights.append(
            "Perda de peso negativa em "
            + ", ".join(invalid_loss_names)
            + "; esses valores permanecem visíveis, mas não entram no ranking."
        )

    suspicious_weight_names = [
        str(record["name"])
        for record in records
        if bool(record["Peso suspeito"])
    ]
    if suspicious_weight_names:
        insights.append(
            "Qualidade de peso requer revisao em "
            + ", ".join(suspicious_weight_names)
            + "; esses ciclos permanecem visiveis, mas ficam fora do ranking de perda."
        )

    return insights
