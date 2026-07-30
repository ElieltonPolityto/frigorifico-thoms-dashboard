"""Painel local Streamlit para comparacao de ciclos do Frigorifico Thoms."""

from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from dashboard_charts import (
    CYCLE_COLORS,
    hourly_metric_chart,
    main_cycle_chart,
    weight_loss_comparison_chart,
)
from dashboard_pdf import build_dashboard_pdf
from thoms_dashboard_data import (
    PHASE_ORDER,
    cycle_frame,
    cycle_metrics,
    detect_valid_cycles,
    hourly_phase_summary,
    load_supervision_data,
    rank_cycles,
)


DATA_FOLDER = Path(__file__).parent / "dados_entrada"
BRAND_LOGO = Path(__file__).parent / "static" / "brand" / "plotter-racks-logo-blue.png"
COLORS = CYCLE_COLORS
METRIC_OPTIONS = ["Espeto", "Peso", "DT_ref", "Umidade", "Ventilacao", "Glicol", "Retorno de ar"]
MAIN_METRIC_OPTIONS = ["Retorno de ar", "Espeto", "Ventilacao", "Umidade", "Peso"]
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
      .thoms-table-wrap { width: 100%; overflow-x: auto; margin: .4rem 0 1rem; }
      table.thoms-table { border-collapse: separate; border-spacing: 0; width: max-content; min-width: 100%; table-layout: auto; }
      table.thoms-table th { background: #142B51; color: white; font-weight: 700; white-space: nowrap; }
      table.thoms-table th, table.thoms-table td { padding: .55rem .75rem; border-right: 1px solid #D9E3EE; border-bottom: 1px solid #D9E3EE; white-space: nowrap; text-align: left; }
      table.thoms-table td:first-child, table.thoms-table th:first-child { border-left: 1px solid #D9E3EE; }
      table.thoms-table tr:nth-child(even) td { background: #F7F9FC; }
      table.thoms-table td.period-cell { min-width: 310px; }
      .thoms-insight { border-left: 4px solid #3CAAFB; background: #F3F8FC; padding: .6rem .8rem; margin: .35rem 0; }
      .thoms-note { color: #5D6C7B; font-size: .86rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="Lendo e validando os CSVs...")
def load_dashboard_data(folder: str, folder_mtime: float) -> pd.DataFrame:
    """Cache deterministic file reads while invalidating when a CSV changes."""
    del folder_mtime
    return load_supervision_data(Path(folder))


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


def render_html_table(frame: pd.DataFrame, period_column: str | None = None) -> None:
    """Render a content-sized table with horizontal overflow when needed."""
    headers = "".join(f"<th>{escape(str(column))}</th>" for column in frame.columns)
    body_rows = []
    for _, row in frame.iterrows():
        cells = []
        for column in frame.columns:
            css_class = "period-cell" if column == period_column else ""
            value = "—" if pd.isna(row[column]) else str(row[column])
            cells.append(
                f'<td class="{css_class}">{escape(value)}</td>'
            )
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(
        '<div class="thoms-table-wrap"><table class="thoms-table">'
        f"<thead><tr>{headers}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def phase_strip(selected_cycles, data: pd.DataFrame) -> None:
    """Show the three real phase durations for each selected cycle."""
    st.caption(
        "C = carregamento | R = resfriamento até 7 °C | "
        "P = resfriamento pós-meta"
    )
    for index, cycle in enumerate(selected_cycles):
        metrics = cycle_metrics(data, cycle)
        loading = float(metrics["Duracao carga"])
        to_target = float(metrics["Duracao ate meta"])
        post_target = metrics["Duracao pos meta"]
        post_value = float(post_target) if isinstance(post_target, (int, float)) else 0.0
        total = max(loading + to_target + post_value, 0.01)
        segments = [
            (
                loading / total * 100,
                "#CFEAFB",
                "#142B51",
                f"C {loading:.1f} h",
            ),
            (
                to_target / total * 100,
                "#3CAAFB",
                "white",
                (
                    f"R {to_target:.1f} h"
                    if post_target is not None
                    else f"R {to_target:.1f} h · meta não atingida"
                ),
            ),
        ]
        if post_target is not None:
            segments.append(
                (
                    post_value / total * 100,
                    "#142B51",
                    "white",
                    f"P {post_value:.1f} h",
                )
            )
        segment_html = "".join(
            (
                f'<div style="width:{width:.2f}%;background:{background};'
                f"color:{foreground};padding:4px 7px;font-size:12px;"
                f'min-width:72px;white-space:nowrap;">{escape(label)}</div>'
            )
            for width, background, foreground, label in segments
        )
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:10px;margin:5px 0 10px 0;">
              <span style="min-width:90px;color:{COLORS[index]};font-weight:700;">Ciclo {index + 1}</span>
              <div style="display:flex;flex:1;height:28px;border-radius:5px;overflow:hidden;background:#F3F6FA;">
                {segment_html}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def cycle_summary_frame(selected_cycles, data: pd.DataFrame) -> pd.DataFrame:
    """Build the reconciled summary table used by the app and PDF."""
    def formatted(value, suffix: str, decimals: int = 1) -> str:
        return "—" if value is None or pd.isna(value) else f"{value:.{decimals}f} {suffix}"

    rows = []
    for index, cycle in enumerate(selected_cycles):
        metrics = cycle_metrics(data, cycle)
        time_to_target = metrics["Tempo ate 7 C"]
        reference_weight = metrics.get(
            "Peso referencia",
            metrics.get("Peso inicial"),
        )
        rows.append(
            {
                "Ciclo": f"Ciclo {index + 1}",
                "Período": cycle.label,
                "C": formatted(metrics["Duracao carga"], "h"),
                "R": formatted(metrics["Duracao ate meta"], "h"),
                "P": formatted(metrics["Duracao pos meta"], "h"),
                "Peso de referencia": formatted(reference_weight, "kg"),
                "Peso aos 7 °C": formatted(metrics["Peso final"], "kg"),
                "Perda até 7 °C": formatted(metrics["Perda"], "%", decimals=2),
                "Perda absoluta": formatted(metrics.get("Perda absoluta"), "kg", decimals=2),
                "Espeto inicial": formatted(metrics["Espeto inicial"], "°C"),
                "Até 7 °C": (
                    format_hours(time_to_target)
                    if isinstance(time_to_target, (int, float))
                    else "Meta não atingida"
                ),
                "DT_ref médio": formatted(metrics["DT_ref medio"], "°C"),
            }
        )
    return pd.DataFrame(rows)


def render_cycle_summary_table(selected_cycles, data: pd.DataFrame) -> None:
    st.subheader("Resumo dos ciclos selecionados")
    render_html_table(
        cycle_summary_frame(selected_cycles, data),
        period_column="Período",
    )


def ordered_hour_labels(selected_cycles, data: pd.DataFrame) -> list[str]:
    """Return a common C...R...P phase-hour sequence."""
    ordering: dict[str, tuple[int, int]] = {}
    for cycle in selected_cycles:
        frame = cycle_frame(data, cycle, "Espeto")
        for row in frame[["phase", "phase_hour", "hour_label"]].drop_duplicates().itertuples():
            ordering[row.hour_label] = (PHASE_ORDER.index(row.phase), int(row.phase_hour))
    return sorted(ordering, key=ordering.get)


def explanatory_table_frame(
    selected_cycles,
    data: pd.DataFrame,
    metric: str,
    selected_hours: list[str],
) -> pd.DataFrame:
    """Pivot the chart values into a readable cycle-comparison table."""
    rows: dict[tuple[str, int, str], dict[str, str]] = {}
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
                {
                    "Fase": str(record["phase"]),
                    "Hora": str(record["hour_label"]),
                },
            )
            partial = " · parcial" if bool(record["partial"]) else ""
            row[f"Ciclo {index + 1}"] = (
                f'{float(record["value"]):.2f} {record["unit"]} · '
                f'{float(record["coverage_minutes"]):.0f} min{partial}'
            )

    ordered = sorted(
        rows.items(),
        key=lambda item: (
            PHASE_ORDER.index(item[0][0]),
            item[0][1],
        ),
    )
    columns = ["Fase", "Hora"] + [
        f"Ciclo {index + 1}" for index in range(len(selected_cycles))
    ]
    return pd.DataFrame([row for _, row in ordered], columns=columns).fillna("—")


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
        data_folder_mtime = folder_last_modified(DATA_FOLDER)
        data = load_dashboard_data(str(DATA_FOLDER), data_folder_mtime)
        cycles = detect_valid_cycles(data)
        ranking = rank_cycles(data, cycles)
    except (FileNotFoundError, ValueError) as error:
        st.error(str(error))
        return

    suggested_labels = ranking.head(1)["label"].tolist()
    st.sidebar.header("Seleção")
    selected_labels = st.sidebar.multiselect(
        "Escolha até três ciclos",
        options=[cycle.label for cycle in cycles],
        default=suggested_labels,
        max_selections=3,
        placeholder="Selecione um ciclo",
        help=(
            "A seleção inicial abre o ciclo com melhor equilíbrio entre tempo "
            "até 7 °C e perda de peso, com ponderação de 50% para cada indicador."
        ),
    )
    selected_bar_metrics = st.sidebar.multiselect(
        "Variáveis na comparação horária",
        options=METRIC_OPTIONS,
        default=PDF_BAR_DEFAULTS,
        help="Cada variável selecionada aparece no resumo e em uma aba de comparação individual.",
    )
    visible_main_metrics = st.sidebar.multiselect(
        "Variáveis do gráfico principal",
        options=MAIN_METRIC_OPTIONS,
        default=MAIN_METRIC_OPTIONS,
        help="As faixas usam escalas independentes e permanecem sincronizadas no tempo.",
    )
    st.sidebar.caption(f"{len(cycles)} ciclos válidos encontrados nos CSVs disponíveis.")
    st.sidebar.caption(
        f"{len(ranking)} ciclos elegíveis para o ranking; perdas negativas e "
        "ciclos sem meta ficam fora da sugestão automática."
    )

    if not selected_labels:
        st.info("Selecione um, dois ou três ciclos na barra lateral para iniciar a comparação.")
        return

    cycle_by_label = {cycle.label: cycle for cycle in cycles}
    ranking_position = {
        str(record.label): int(record.rank)
        for record in ranking.itertuples(index=False)
    }
    selected_labels = sorted(
        selected_labels,
        key=lambda label: (ranking_position.get(label, len(cycles) + 1), label),
    )
    selected_cycles = [cycle_by_label[label] for label in selected_labels]
    active_label = st.sidebar.selectbox(
        "Ciclo do gráfico principal",
        options=selected_labels,
        format_func=lambda label: f"Ciclo {selected_labels.index(label) + 1} - {label}",
        help="O Ciclo 1 abre primeiro; a comparação de peso continua mostrando todos os ciclos selecionados.",
    )
    active_cycle = cycle_by_label[active_label]
    render_cycle_summary_table(selected_cycles, data)
    phase_strip(selected_cycles, data)

    hour_options = ordered_hour_labels(selected_cycles, data)
    selected_time_window = st.select_slider(
        "Janela de análise por hora da fase",
        options=hour_options,
        value=(hour_options[0], hour_options[-1]),
        help=(
            "C = carregamento, R = resfriamento até 7 °C e "
            "P = resfriamento pós-meta."
        ),
    )
    start_hour, end_hour = selected_time_window
    selected_hours = hour_options[hour_options.index(start_hour) : hour_options.index(end_hour) + 1]
    st.divider()
    st.altair_chart(
        main_cycle_chart(
            active_cycle,
            selected_cycles,
            data,
            visible_main_metrics,
            selected_hours,
        ),
        width="stretch",
    )

    st.subheader("Perda de peso acumulada")
    st.caption(
        "Comparação minuto a minuto até 7 °C: linha contínua em percentual e tracejada em kg."
    )
    st.altair_chart(
        weight_loss_comparison_chart(selected_cycles, data, selected_hours),
        width="stretch",
    )

    st.subheader("Médias horárias e dados de apoio")
    if not selected_bar_metrics:
        st.info("Selecione pelo menos uma variável para exibir a comparação horária.")
    else:
        st.caption(
            "Cada gráfico reúne carregamento e resfriamento até a meta no mesmo eixo. "
            "O período pós-meta permanece disponível na tabela detalhada."
        )
        def render_hourly_metric(metric: str, *, show_heading: bool, show_detail: bool) -> None:
            display_name = DISPLAY_METRIC_NAMES.get(metric, metric)
            if show_heading:
                st.markdown(f"#### {display_name}")
            st.altair_chart(
                hourly_metric_chart(
                    selected_cycles,
                    data,
                    metric,
                    selected_hours,
                ),
                width="stretch",
            )
            st.caption(
                "Marcas semitransparentes representam horas parciais com menos de "
                "45 minutos de cobertura. A matriz abaixo do eixo mostra os valores por ciclo; "
                "o asterisco identifica uma hora parcial."
            )
            if show_detail:
                with st.expander("Ver tabela detalhada (inclui resfriamento pós-meta)"):
                    render_html_table(
                        explanatory_table_frame(
                            selected_cycles,
                            data,
                            metric,
                            selected_hours,
                        )
                    )
                    st.caption(
                        "Cada célula mostra a média horária, a unidade e a cobertura "
                        "observada. Horas com menos de 45 minutos são marcadas como parciais."
                    )

        tabs = st.tabs(
            ["Resumo"]
            + [DISPLAY_METRIC_NAMES.get(metric, metric) for metric in selected_bar_metrics]
        )
        with tabs[0]:
            for metric in selected_bar_metrics:
                render_hourly_metric(metric, show_heading=True, show_detail=False)
        for tab, metric in zip(tabs[1:], selected_bar_metrics):
            with tab:
                render_hourly_metric(metric, show_heading=False, show_detail=True)

    report_signature = (
        tuple(selected_labels),
        tuple(selected_bar_metrics),
        active_label,
        tuple(visible_main_metrics),
        tuple(selected_hours),
    )
    st.divider()
    st.subheader("Relatório da seleção")
    if st.button("Preparar relatório PDF", type="primary"):
        with st.spinner("Gerando gráficos, tabelas e relatório..."):
            try:
                st.session_state["thoms_pdf"] = build_dashboard_pdf(
                    selected_cycles=selected_cycles,
                    data=data,
                    active_cycle=active_cycle,
                    main_metrics=visible_main_metrics,
                    bar_metrics=selected_bar_metrics,
                    selected_hours=selected_hours,
                    logo_path=BRAND_LOGO,
                )
                st.session_state["thoms_pdf_signature"] = report_signature
            except Exception as error:
                st.session_state.pop("thoms_pdf", None)
                st.session_state.pop("thoms_pdf_signature", None)
                st.error(f"Não foi possível gerar o PDF: {error}")

    if (
        st.session_state.get("thoms_pdf")
        and st.session_state.get("thoms_pdf_signature") == report_signature
    ):
        st.download_button(
            "Baixar relatório PDF",
            data=st.session_state["thoms_pdf"],
            file_name="relatorio_selecao_ciclos_thoms.pdf",
            mime="application/pdf",
        )
        st.caption(
            "O arquivo reproduz os ciclos, a janela de horas e as variáveis "
            "selecionadas neste momento."
        )



if __name__ == "__main__":
    main()
