"""Painel local Streamlit para comparacao de ciclos do Frigorifico Thoms."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from thoms_dashboard_data import (
    cycle_frame,
    cycle_metrics,
    detect_valid_cycles,
    load_supervision_data,
)


DATA_FOLDER = Path(__file__).parent / "dados_entrada"
PRIVATE_DATA_REPOSITORY = "ElieltonPolityto/resfriamento-carcacas-app"
PRIVATE_DATA_BRANCH = "streamlit/thoms-dashboard"
BRAND_LOGO = Path(__file__).parent / "static" / "brand" / "plotter-racks-logo-blue.png"
COLORS = ["#142B51", "#3CAAFB", "#82C9FD"]
METRIC_OPTIONS = ["Espeto", "Peso", "DT_ref", "Umidade", "Ventilacao", "Glicol", "Retorno de ar"]
PDF_BAR_DEFAULTS = ["Espeto", "Peso", "DT_ref", "Umidade", "Ventilacao"]
DISPLAY_METRIC_NAMES = {"Umidade": "Umidade Relativa"}

st.set_page_config(page_title="Thoms | Ciclos", page_icon="❄️", layout="wide")

st.markdown(
    """
    <style>
      [data-testid="stSidebar"] { background: #F3F6FA; border-right: 1px solid #D9E3EE; }
      [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
      [data-testid="stSidebar"] h3 { color: #142B51; }
      .plotter-header { border-bottom: 3px solid #3CAAFB; padding: 0.15rem 0 1rem; margin-bottom: 1rem; }
      .plotter-header h1 { color: #142B51; margin: 0; font-weight: 900; }
      .plotter-header p { color: #5D6C7B; margin: 0.3rem 0 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="Lendo e validando os CSVs...")
def load_dashboard_data(folder: str, folder_mtime: float) -> pd.DataFrame:
    """Cache deterministic file reads while invalidating when a CSV changes."""
    del folder_mtime
    return load_supervision_data(Path(folder))


@st.cache_data(show_spinner="Carregando a base de supervisão...")
def load_private_repository_data() -> pd.DataFrame:
    """Read CSVs server-side from the private data repository on Streamlit Cloud."""
    token = st.secrets.get("GITHUB_DATA_TOKEN", "")
    if not token:
        raise FileNotFoundError("A base privada não foi configurada no Streamlit Cloud.")

    headers = {
        "Accept": "application/vnd.github.raw+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    listing_url = (
        f"https://api.github.com/repos/{PRIVATE_DATA_REPOSITORY}/contents/dados_entrada"
        f"?ref={PRIVATE_DATA_BRANCH}"
    )
    try:
        with urlopen(Request(listing_url, headers=headers), timeout=30) as response:
            entries = json.load(response)
    except (HTTPError, URLError, json.JSONDecodeError) as error:
        raise FileNotFoundError("Não foi possível carregar a base privada de supervisão.") from error

    csv_entries = [entry for entry in entries if entry.get("name", "").lower().endswith(".csv")]
    if not csv_entries:
        raise FileNotFoundError("Nenhum CSV foi encontrado na base privada de supervisão.")

    with TemporaryDirectory(prefix="thoms_supervisao_") as temporary_folder:
        folder = Path(temporary_folder)
        for entry in csv_entries:
            request = Request(entry["url"], headers=headers)
            with urlopen(request, timeout=30) as response:
                (folder / entry["name"]).write_bytes(response.read())
        return load_supervision_data(folder)


def folder_last_modified(folder: Path) -> float:
    files = list(folder.glob("*.csv"))
    return max((file.stat().st_mtime for file in files), default=0.0)


def format_hours(value: float | str) -> str:
    if isinstance(value, str):
        return value
    return f"{value:.1f} h"


def enable_sidebar_autohide(timeout_seconds: int = 15) -> None:
    """Hide the sidebar after inactivity and reveal it from the left screen edge."""
    timeout_ms = timeout_seconds * 1000
    components.html(
        f"""
        <script>
        (() => {{
          const parentWindow = window.parent;
          const documentRoot = parentWindow.document.documentElement;
          const state = parentWindow.__thomsSidebarAutohide || {{}};
          state.timeoutMs = {timeout_ms};
          state.lastActivity = Date.now();

          const showSidebar = () => documentRoot.removeAttribute("data-thoms-sidebar-hidden");
          const hideSidebar = () => documentRoot.setAttribute("data-thoms-sidebar-hidden", "true");
          const isHidden = () => documentRoot.getAttribute("data-thoms-sidebar-hidden") === "true";

          if (!state.installed) {{
            const style = parentWindow.document.createElement("style");
            style.id = "thoms-sidebar-autohide-style";
            style.textContent = `
              [data-testid="stSidebar"] {{
                transition: width .22s ease, min-width .22s ease, flex-basis .22s ease, transform .22s ease;
              }}
              html[data-thoms-sidebar-hidden="true"] [data-testid="stSidebar"] {{
                width: 0 !important;
                min-width: 0 !important;
                flex-basis: 0 !important;
                transform: translateX(-100%);
                overflow: hidden;
                border-right: 0 !important;
              }}
              #thoms-sidebar-reveal {{
                display: none;
                position: fixed;
                z-index: 1000000;
                left: 0;
                top: 30%;
                width: 12px;
                height: 140px;
                border-radius: 0 8px 8px 0;
                background: rgba(20, 43, 81, .32);
                cursor: pointer;
              }}
              html[data-thoms-sidebar-hidden="true"] #thoms-sidebar-reveal {{ display: block; }}
            `;
            parentWindow.document.head.appendChild(style);

            const revealControl = parentWindow.document.createElement("div");
            revealControl.id = "thoms-sidebar-reveal";
            revealControl.title = "Mostrar filtros";
            revealControl.addEventListener("mouseenter", showSidebar);
            revealControl.addEventListener("click", showSidebar);
            parentWindow.document.body.appendChild(revealControl);

            const registerActivity = (event) => {{
              if (isHidden() && event.type === "pointermove" && event.clientX > 24) return;
              state.lastActivity = Date.now();
              if (!isHidden() || event.type !== "pointermove" || event.clientX <= 24) showSidebar();
            }};
            ["pointermove", "pointerdown", "keydown", "touchstart", "wheel"].forEach((eventName) =>
              parentWindow.document.addEventListener(eventName, registerActivity, {{ passive: true }})
            );
            state.installed = true;
          }}

          if (!state.timer) {{
            state.timer = parentWindow.setInterval(() => {{
              if (!isHidden() && Date.now() - state.lastActivity >= state.timeoutMs) hideSidebar();
            }}, 1000);
          }}
          parentWindow.__thomsSidebarAutohide = state;
        }})();
        </script>
        """,
        height=0,
    )


def phase_strip(selected_cycles, data: pd.DataFrame) -> None:
    """Show loading and cooling without adding negative hours to the chart axis."""
    st.caption("Fases: C0, C1... = carregamento | H0, H1... = resfriamento")
    for index, cycle in enumerate(selected_cycles):
        metrics = cycle_metrics(data, cycle)
        loading = metrics["Duracao carga"]
        cooling = metrics["Duracao resfriamento"]
        total = loading + cooling
        loading_width = loading / total * 100
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:10px;margin:5px 0 10px 0;">
              <span style="min-width:180px;color:{COLORS[index]};font-weight:600;">Ciclo {index + 1}</span>
              <div style="display:flex;flex:1;height:25px;border-radius:5px;overflow:hidden;background:#f3f4f6;">
                <div style="width:{loading_width:.2f}%;background:#9ca3af;color:white;padding:3px 8px;font-size:12px;white-space:nowrap;">Carga {loading:.1f} h</div>
                <div style="flex:1;background:{COLORS[index]};color:white;padding:3px 8px;font-size:12px;white-space:nowrap;">Resfriamento {cooling:.1f} h</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_cycle_summary_table(selected_cycles, data: pd.DataFrame) -> None:
    """Render one compact comparison table instead of repeated metric cards."""
    def formatted(value, suffix: str, decimals: int = 1) -> str:
        return "—" if value is None or pd.isna(value) else f"{value:.{decimals}f} {suffix}"

    rows = []
    for index, cycle in enumerate(selected_cycles):
        metrics = cycle_metrics(data, cycle)
        rows.append(
            {
                "Ciclo": f"Ciclo {index + 1}",
                "Período": cycle.label,
                "Carga": formatted(metrics["Duracao carga"], "h"),
                "Resfriamento": formatted(metrics["Duracao resfriamento"], "h"),
                "Peso inicial": formatted(metrics["Peso inicial"], "kg"),
                "Peso aos 7 °C": formatted(metrics["Peso final"], "kg"),
                "Perda até 7 °C": formatted(metrics["Perda"], "%", decimals=2),
                "Espeto inicial": formatted(metrics["Espeto inicial"], "°C"),
                "Até 7 °C": format_hours(metrics["Tempo ate 7 C"]) if metrics["Tempo ate 7 C"] is not None else "—",
                "DT_ref médio": formatted(metrics["DT_ref medio"], "°C"),
            }
        )

    st.subheader("Resumo dos ciclos selecionados")
    st.dataframe(
        pd.DataFrame(rows),
        column_config={
            "Ciclo": st.column_config.TextColumn(width="small"),
            "Período": st.column_config.TextColumn(width="medium"),
            "Carga": st.column_config.TextColumn(width="small"),
            "Resfriamento": st.column_config.TextColumn(width="small"),
            "Peso inicial": st.column_config.TextColumn(width="small"),
            "Peso aos 7 °C": st.column_config.TextColumn(width="small"),
            "Perda até 7 °C": st.column_config.TextColumn(width="small"),
            "Espeto inicial": st.column_config.TextColumn(width="small"),
            "Até 7 °C": st.column_config.TextColumn(width="small"),
            "DT_ref médio": st.column_config.TextColumn(width="small"),
        },
        hide_index=True,
        width="stretch",
        height=35 * (len(rows) + 1) + 4,
    )


def ordered_hour_labels(selected_cycles, data: pd.DataFrame) -> list[str]:
    """Return a common C0...Hn timeline for the selected cycles."""
    labels: set[str] = set()
    for cycle in selected_cycles:
        labels.update(cycle_frame(data, cycle, "Espeto")["hour_label"].unique())
    return sorted(labels, key=lambda label: (0 if label.startswith("C") else 1, int(label[1:])))


def hourly_chart(
    selected_cycles, data: pd.DataFrame, metric: str, selected_hours: list[str]
) -> alt.Chart:
    """Create one labelled hourly bar panel, styled after the PDF reference."""
    rows: list[pd.DataFrame] = []
    unit = ""
    hour_order = selected_hours

    for index, cycle in enumerate(selected_cycles):
        frame = cycle_frame(data, cycle, metric)
        unit = frame["unit"].iloc[0]
        frame = frame[frame["hour_label"].isin(selected_hours)]
        if frame.empty:
            continue
        hourly = (
            frame.groupby("hour_label", sort=False)["value"]
            .mean()
            .reset_index()
            .rename(columns={"hour_label": "Hora", "value": "Valor"})
        )
        hourly["Ciclo"] = f"Ciclo {index + 1}"
        rows.append(hourly)

    chart_data = pd.concat(rows, ignore_index=True)
    if metric == "Umidade":
        chart_data = chart_data[chart_data["Valor"] >= 92].copy()
    cycle_domain = [f"Ciclo {index + 1}" for index in range(len(selected_cycles))]
    x = alt.X("Hora:O", sort=hour_order, title=None, axis=alt.Axis(labelAngle=0, labelPadding=7))
    y_scale = alt.Scale(domain=[92, 100], zero=False) if metric == "Umidade" else alt.Scale(zero=True)
    y = alt.Y("Valor:Q", title=f"Média ({unit})", scale=y_scale)
    show_value_labels = len(selected_cycles) == 1
    color = alt.Color(
        "Ciclo:N",
        scale=alt.Scale(domain=cycle_domain, range=COLORS[: len(selected_cycles)]),
        legend=None if show_value_labels else alt.Legend(orient="top", title=None),
    )
    offset = alt.XOffset("Ciclo:N", sort=cycle_domain)

    bar_encoding = {
        "x": x,
        "xOffset": offset,
        "y": y,
        "color": color,
        "tooltip": [
            alt.Tooltip("Ciclo:N", title="Ciclo"),
            alt.Tooltip("Hora:O", title="Hora"),
            alt.Tooltip("Valor:Q", title=f"Média ({unit})", format=".1f"),
        ],
    }
    if metric == "Umidade":
        # A barra deve nascer no limite operacional de 92%, não no zero oculto.
        bar_encoding["y2"] = alt.datum(92)
    bars = alt.Chart(chart_data).mark_bar(opacity=0.82).encode(**bar_encoding)
    labels = alt.Chart(chart_data).mark_text(
        dy=-8, font="Gotham", fontSize=14, fontWeight="bold", color="#263238"
    ).encode(x=x, xOffset=offset, y=y, text=alt.Text("Valor:Q", format=".1f"), detail="Ciclo:N")
    display_metric = DISPLAY_METRIC_NAMES.get(metric, metric)
    chart = bars + labels if show_value_labels else bars
    return chart.properties(title=f"{display_metric} - média por hora", height=245)


def main() -> None:
    enable_sidebar_autohide()
    st.image(str(BRAND_LOGO), width=360)
    st.markdown(
        """
        <div class="plotter-header">
          <h1>Ciclos de resfriamento | Frigorífico Thoms</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        if list(DATA_FOLDER.glob("*.csv")):
            data = load_dashboard_data(str(DATA_FOLDER), folder_last_modified(DATA_FOLDER))
        else:
            data = load_private_repository_data()
        cycles = detect_valid_cycles(data)
    except (FileNotFoundError, ValueError) as error:
        st.error(str(error))
        return

    st.sidebar.header("Seleção")
    selected_labels = st.sidebar.multiselect(
        "Escolha até três ciclos",
        options=[cycle.label for cycle in cycles],
        max_selections=3,
        placeholder="Nenhum ciclo selecionado",
    )
    selected_bar_metrics = st.sidebar.multiselect(
        "Variáveis nas barras horárias",
        options=METRIC_OPTIONS,
        default=PDF_BAR_DEFAULTS,
        help="Cada variável selecionada aparece em um painel de barras, como no PDF de referência.",
    )
    main_metric = st.sidebar.selectbox(
        "Variável do gráfico contínuo",
        options=selected_bar_metrics or METRIC_OPTIONS,
        index=0,
    )
    st.sidebar.caption(f"{len(cycles)} ciclos válidos encontrados nos CSVs disponíveis.")

    if not selected_labels:
        st.info("Selecione um, dois ou três ciclos na barra lateral para iniciar a comparação.")
        return

    cycle_by_label = {cycle.label: cycle for cycle in cycles}
    selected_cycles = [cycle_by_label[label] for label in selected_labels]
    render_cycle_summary_table(selected_cycles, data)

    hour_options = ordered_hour_labels(selected_cycles, data)
    selected_time_window = st.select_slider(
        "Janela de análise por hora do ciclo",
        options=hour_options,
        value=(hour_options[0], hour_options[-1]),
        help="Exemplo: escolha C0 até H7 para mostrar apenas esse trecho em todos os gráficos.",
    )
    start_hour, end_hour = selected_time_window
    selected_hours = hour_options[hour_options.index(start_hour) : hour_options.index(end_hour) + 1]
    st.divider()
    st.subheader(f"{main_metric} ao longo do ciclo")
    phase_strip(selected_cycles, data)

    line_series = []
    unit = ""
    for index, cycle in enumerate(selected_cycles):
        frame = cycle_frame(data, cycle, main_metric)
        unit = frame["unit"].iloc[0]
        frame = frame[frame["hour_label"].isin(selected_hours)]
        name = f"Ciclo {index + 1}"
        line_series.append(frame[["hours_from_cycle_start", "value"]].rename(columns={"value": name}))

    line_data = line_series[0]
    for series in line_series[1:]:
        line_data = line_data.merge(series, on="hours_from_cycle_start", how="outer")
    line_data = line_data.sort_values("hours_from_cycle_start")
    st.line_chart(
        line_data,
        x="hours_from_cycle_start",
        y=[f"Ciclo {index + 1}" for index in range(len(selected_cycles))],
        color=COLORS[: len(selected_cycles)],
        x_label="Horas desde o início do carregamento",
        y_label=unit,
        height=360,
    )

    st.subheader("Médias horárias por variável")
    if not selected_bar_metrics:
        st.info("Selecione pelo menos uma variável para exibir as barras horárias.")
    if selected_bar_metrics:
        charts = [hourly_chart(selected_cycles, data, metric, selected_hours) for metric in selected_bar_metrics]
        bar_dashboard = (
            alt.vconcat(*charts)
            .resolve_scale(x="shared")
            .configure_axis(labelFont="Gotham", titleFont="Gotham")
            .configure_title(font="Gotham")
        )
        st.altair_chart(bar_dashboard, width="stretch")
    st.caption("C0, C1... representam carregamento; H0, H1... representam resfriamento.")



if __name__ == "__main__":
    main()
