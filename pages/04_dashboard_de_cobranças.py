import plotly.express as px
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from database import Devedor, get_session, init_db
from sqlalchemy.orm import Session


# --- Inicializar banco ---
engine = init_db()
session: Session = get_session(engine)


# --- Carregar dados dos devedores ---
def carregar_dados_devedores():
    devedores = session.query(Devedor).all()
    df = pd.DataFrame([{
        "id": d.id,
        "pessoa": d.pessoa,
        "nome": d.nome,
        "valortotal": d.valortotal,
        "atraso": d.atraso,
        "telefone": d.telefone,
        "data_cobranca": d.data_cobranca,
        "ultima_cobranca": d.ultima_cobranca,
        "status": d.status.value,
        "data_pagamento": d.data_pagamento,
        "fase_cobranca": d.fase_cobranca
    } for d in devedores])
    
    return df


# --- Função principal da aba ---
def exibir_dashboard_estatisticas_tab():
    st.header("📊 Dashboard de Estatísticas de Cobranças")
    
    df = carregar_dados_devedores()
    if df.empty:
        st.info("Nenhum devedor encontrado no sistema para gerar estatísticas.")
        return

    # --- Filtros ---
    st.subheader("🔍 Filtros")
    col1, col2, col3 = st.columns(3)

    with col1:
        status_options = ["Todos"] + sorted(df['status'].dropna().unique())
        selected_status = st.selectbox("Status", options=status_options)

    with col2:
        min_date = df['data_cobranca'].min().date() if pd.notna(df['data_cobranca'].min()) else date.today() - timedelta(days=180)
        max_date = df['data_cobranca'].max().date() if pd.notna(df['data_cobranca'].max()) else date.today()
        date_range = st.date_input("Período (Data da próxima cobrança)", [min_date, max_date])

    with col3:
        fases = sorted(df['fase_cobranca'].dropna().unique())
        fase_options = ["Todas"] + fases
        selected_fase = st.selectbox("Fase de Cobrança", options=fase_options)

    # --- Aplicar Filtros ---
    df_filtrado = df.copy()

    if selected_status != "Todos":
        df_filtrado = df_filtrado[df_filtrado['status'] == selected_status]

    if len(date_range) == 2:
        start_date, end_date = date_range
        df_filtrado = df_filtrado[
            df_filtrado['data_cobranca'].notna() &
            (df_filtrado['data_cobranca'].dt.date >= start_date) &
            (df_filtrado['data_cobranca'].dt.date <= end_date)
        ]

    if selected_fase != "Todas":
        df_filtrado = df_filtrado[df_filtrado['fase_cobranca'] == selected_fase]

    # --- Métricas ---
    st.subheader("📈 Métricas Principais")
    total_devedores = len(df_filtrado)
    total_valor = df_filtrado['valortotal'].sum()
    media_atraso = df_filtrado['atraso'].mean()
    taxa_pagamento = (df_filtrado['status'] == "PAGO").mean() * 100

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total de Cobranças agendadas", total_devedores)
    with col2:
        st.metric("Valor Total Devido", f"R$ {total_valor:,.2f}")
    with col3:
        st.metric("Média de Atraso", f"{media_atraso:.1f} dias" if not pd.isna(media_atraso) else "N/A")
    with col4:
        st.metric("Taxa de Pagamento", f"{taxa_pagamento:.1f}%")

    st.subheader("📊 Visualizações")
    tab1, tab2, tab3 = st.tabs(["Status", "Evolução Temporal", "Distribuição"])

    with tab1:
        status_counts = df_filtrado['status'].value_counts().reset_index()
        status_counts.columns = ['Status', 'Quantidade']
        fig_status = px.pie(
            status_counts, 
            values='Quantidade', 
            names='Status', 
            title='Distribuição por Status', 
            hole=0.4
        )
        st.plotly_chart(fig_status, use_container_width=True)

    with tab2:
        if df_filtrado['data_cobranca'].notna().any():
            df_temporal = df_filtrado.copy()
            df_temporal['mes_ano'] = df_temporal['data_cobranca'].dt.to_period("M").astype(str)
            evolucao = df_temporal.groupby(['mes_ano', 'status']).size().unstack().fillna(0)
            fig_evolucao = px.line(
                evolucao,
                labels={"value": "Quantidade", "mes_ano": "Mês/Ano"},
                title="Evolução por Status e Mês"
            )
            st.plotly_chart(fig_evolucao, use_container_width=True)
        else:
            st.warning("Sem dados suficientes de 'data_cobranca' para exibir a evolução temporal.")

    with tab3:
        col1, col2 = st.columns(2)

        with col1:
            fig_valores = px.histogram(
                df_filtrado,
                x="valortotal",
                nbins=20,
                title="Distribuição de Valores Devidos",
                labels={"valortotal": "Valor (R$)"}
            )
            st.plotly_chart(fig_valores, use_container_width=True)

        with col2:
            fase_counts = df_filtrado['fase_cobranca'].value_counts().reset_index()
            fase_counts.columns = ['Fase', 'Quantidade']
            fig_fase = px.bar(
                fase_counts,
                x='Fase',
                y='Quantidade',
                title="Distribuição por Fase de Cobrança"
            )
            st.plotly_chart(fig_fase, use_container_width=True)

    # --- Tabela Detalhada ---
    st.subheader("📋 Tabela de Devedores")
    cols = ['id', 'nome', 'status', 'fase_cobranca', 'valortotal', 'atraso', 'data_cobranca', 'ultima_cobranca']
    df_exibicao = df_filtrado[cols].copy()

    for col in ['data_cobranca', 'ultima_cobranca']:
        df_exibicao[col] = df_exibicao[col].dt.strftime('%d/%m/%Y')

    df_exibicao['valortotal'] = df_exibicao['valortotal'].apply(lambda x: f"R$ {x:,.2f}")

    st.dataframe(
        df_exibicao,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": "ID",
            "nome": "Nome",
            "status": "Status",
            "fase_cobranca": "Fase",
            "valortotal": "Valor",
            "atraso": "Atraso (dias)",
            "data_cobranca": "Próx. Cobrança",
            "ultima_cobranca": "Últ. Cobrança"
        }
    )


# --- Execução principal ---
if __name__ == "__main__":
    st.set_page_config(page_title="Dashboard de Cobranças", layout="wide")
    st.title("📈 Sistema de Gestão de Cobranças")
    exibir_dashboard_estatisticas_tab()
