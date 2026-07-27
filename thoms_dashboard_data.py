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

DATA_COMPLETENESS_MIN = 0.95
MAX_CONTINUOUS_GAP_MINUTES = 5
MIN_VALID_WEIGHT_KG = 90
MAX_WEIGHT_AT_TARGET_DELAY_MINUTES = 5
OPERATIONAL_CYCLE_CUTOFF_HOUR = 11
WEEKDAY_ABBREVIATIONS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")


@dataclass(frozen=True)
class Cycle:
    """A cycle that passed the source-data quality rules."""

    start_index: int
    cooling_index: int
    end_index: int
    label: str


def _first_time_at_or_below_7(frame: pd.DataFrame, cooling_start: pd.Timestamp) -> pd.Timestamp | None:
    """Return the first espeto sample at or below 7 C during cooling."""
    espeto = frame[REQUIRED_COLUMNS["Espeto"]]
    reached = frame.loc[(frame["timestamp"] >= cooling_start) & (espeto <= 7), "timestamp"]
    return None if reached.empty else reached.iloc[0]


def _positive_weights(frame: pd.DataFrame) -> pd.Series:
    """Zero or negative weights do not represent a valid scale reading."""
    weight = frame[REQUIRED_COLUMNS["Peso"]]
    return weight.where(weight > 0)


def _initial_loaded_weight(frame: pd.DataFrame) -> pd.Series:
    """The start of the loss calculation is the first weight above 90 kg."""
    return _positive_weights(frame).where(_positive_weights(frame) > MIN_VALID_WEIGHT_KG)


def _weight_at_7_c(frame: pd.DataFrame, reached_7_time: pd.Timestamp) -> float | None:
    """Use the valid scale sample at, or immediately before, the 7 C crossing."""
    valid_weight = _initial_loaded_weight(frame)
    before = valid_weight.where(frame["timestamp"] <= reached_7_time).dropna()
    if not before.empty:
        timestamp = frame.loc[before.index[-1], "timestamp"]
        if reached_7_time - timestamp <= pd.Timedelta(minutes=MAX_WEIGHT_AT_TARGET_DELAY_MINUTES):
            return float(before.iloc[-1])

    after = valid_weight.where(frame["timestamp"] > reached_7_time).dropna()
    if not after.empty:
        timestamp = frame.loc[after.index[0], "timestamp"]
        if timestamp - reached_7_time <= pd.Timedelta(minutes=MAX_WEIGHT_AT_TARGET_DELAY_MINUTES):
            return float(after.iloc[0])
    return None


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

    required = set(REQUIRED_COLUMNS.values()) | {"Carregamento", "Resfriamento"}
    missing_columns = sorted(required - set(data.columns))
    if missing_columns:
        raise ValueError(f"Colunas obrigatorias ausentes: {', '.join(missing_columns)}")

    for column in REQUIRED_COLUMNS.values():
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


def cycle_frame(data: pd.DataFrame, cycle: Cycle, metric: str) -> pd.DataFrame:
    """Return one cycle with phase and hourly labels for a selected dashboard metric."""
    source_column = REQUIRED_COLUMNS[metric]
    frame = data.iloc[cycle.start_index : cycle.end_index + 1].copy()
    start_time = frame["timestamp"].iloc[0]
    cooling_time = data.at[cycle.cooling_index, "timestamp"]
    frame["hours_from_cycle_start"] = (
        frame["timestamp"] - start_time
    ).dt.total_seconds() / 3600
    frame["phase"] = np.where(frame["timestamp"] < cooling_time, "Carregamento", "Resfriamento")
    phase_start = np.where(frame["phase"].eq("Carregamento"), start_time, cooling_time)
    phase_hour = np.floor((frame["timestamp"] - pd.to_datetime(phase_start)).dt.total_seconds() / 3600).astype(int)
    frame["hour_label"] = np.where(frame["phase"].eq("Carregamento"), "C", "H") + phase_hour.astype(str)

    if metric == "Peso":
        valid_weight = _initial_loaded_weight(frame)
        initial_weight_series = valid_weight.dropna()
        initial_weight = initial_weight_series.iloc[0]
        initial_time = initial_weight_series.index[0]
        valid_weight = valid_weight.where(frame.index >= initial_time)
        reached_7_time = _first_time_at_or_below_7(frame, cooling_time)
        if reached_7_time is not None:
            valid_weight = valid_weight.where(frame["timestamp"] <= reached_7_time)
        frame["value"] = (initial_weight - valid_weight) / initial_weight * 100
        frame["unit"] = "% de perda acumulada"
    else:
        frame["value"] = frame[source_column]
        frame["unit"] = {
            "Espeto": "°C",
            "DT_ref": "°C",
            "Umidade": "%",
            "Ventilacao": "%",
            "Glicol": "°C",
            "Retorno de ar": "°C",
        }[metric]

    return frame


def cycle_metrics(data: pd.DataFrame, cycle: Cycle) -> dict[str, float | str]:
    """Calculate the KPI cards using the agreed cycle boundaries."""
    frame = data.iloc[cycle.start_index : cycle.end_index + 1].copy()
    cooling_start = data.at[cycle.cooling_index, "timestamp"]
    weights = _initial_loaded_weight(frame).dropna()
    espeto = frame[REQUIRED_COLUMNS["Espeto"]]
    reached_7_time = _first_time_at_or_below_7(frame, cooling_start)
    initial_espeto = espeto.where(espeto > 35).dropna()

    initial_weight = float(weights.iloc[0])
    final_weight = None
    if reached_7_time is not None:
        final_weight = _weight_at_7_c(frame, reached_7_time)
    return {
        "Duracao carga": (cooling_start - frame["timestamp"].iloc[0]).total_seconds() / 3600,
        "Duracao resfriamento": (frame["timestamp"].iloc[-1] - cooling_start).total_seconds() / 3600,
        "Peso inicial": initial_weight,
        "Peso final": final_weight,
        "Perda": (
            (initial_weight - final_weight) / initial_weight * 100 if final_weight is not None else None
        ),
        "Espeto inicial": float(initial_espeto.iloc[0]) if not initial_espeto.empty else None,
        "Espeto final": float(espeto.dropna().iloc[-1]),
        "Tempo ate 7 C": (
            (reached_7_time - cooling_start).total_seconds() / 3600 if reached_7_time is not None else "Nao atingiu"
        ),
        "DT_ref medio": float(frame[REQUIRED_COLUMNS["DT_ref"]].mean()),
    }
