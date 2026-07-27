# Painel de ciclos — Frigorífico Thoms

Painel Streamlit para comparação de ciclos de resfriamento a partir dos CSVs diários de supervisão.

## Uso local

1. Instale as dependências: `pip install -r requirements.txt`.
2. Os CSVs diários ficam em `dados_entrada` e são carregados automaticamente.
3. Execute: `streamlit run app.py`.

## Streamlit Community Cloud

O painel carrega automaticamente os CSVs versionados em `dados_entrada`. Mantenha o repositório privado para que os dados operacionais não fiquem acessíveis pelo GitHub. Configure o arquivo principal como `app.py`; as dependências já estão em `requirements.txt`.
