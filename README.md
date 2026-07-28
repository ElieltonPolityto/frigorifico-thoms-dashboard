# Painel de ciclos — Frigorífico Thoms

Painel Streamlit para comparação de ciclos de resfriamento a partir dos CSVs diários de supervisão.

## Uso local

1. Crie um ambiente local: `python -m venv .venv`.
2. Instale as dependências: `.venv\Scripts\python.exe -m pip install -r requirements.txt`.
3. Os CSVs diários ficam em `dados_entrada` e são carregados automaticamente.
4. Execute `iniciar_painel.bat` ou `.venv\Scripts\python.exe -m streamlit run app.py`.

## Recursos principais

- Sugestão automática dos três ciclos com melhor equilíbrio entre tempo até 7 °C e perda de peso.
- Comparação por carregamento, resfriamento até a meta e resfriamento pós-meta.
- Médias horárias com identificação de horas parciais.
- Tabelas explicativas reconciliadas com os gráficos.
- Geração de relatório PDF conforme os filtros selecionados.

## Streamlit Community Cloud

O painel carrega automaticamente os CSVs versionados em `dados_entrada`. Configure o arquivo principal como `app.py`; as dependências já estão em `requirements.txt`.
