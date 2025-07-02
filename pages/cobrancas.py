import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import calendar
import numpy as np

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Sistema de Cobranças - Agendamento",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- IMPORTAÇÕES E VERIFICAÇÕES ---
try:
    from database import init_db, Devedor, StatusDevedor
    from devedores_service import (
        load_devedores_from_db,
        marcar_cobranca_feita_e_reagendar_in_db,
        marcar_como_pago_in_db,
        remover_devedor_from_db
    )
except ImportError as e:
    st.error(f"Erro ao importar módulos: {e}. Verifique se os arquivos de serviço e banco de dados estão corretos.")
    st.stop()

# --- INICIALIZAÇÃO DO ESTADO DA SESSÃO ---
# Agrupa todas as inicializações para maior clareza.
if 'db_engine' not in st.session_state:
    st.session_state.db_engine = init_db()
if 'selected_date' not in st.session_state:
    st.session_state.selected_date = date.today()
if 'agendamento_devedor_id' not in st.session_state:
    st.session_state.agendamento_devedor_id = None


# --- OTIMIZAÇÃO 1: CACHE CENTRALIZADO DE DADOS ---
@st.cache_data(show_spinner="Carregando dados dos devedores...")
def cached_load_data(_db_engine):
    """
    Carrega os dados do banco e realiza o pré-processamento uma única vez.
    O resultado é cacheado para performance máxima.
    """
    df = load_devedores_from_db(_db_engine)
    
    if df.empty:
        return df

    # Garante que a coluna 'fase_cobranca' exista
    if 'fase_cobranca' not in df.columns:
        df['fase_cobranca'] = 1
    else:
        df['fase_cobranca'] = pd.to_numeric(df['fase_cobranca'], errors='coerce').fillna(1).astype(int)

    # Converte colunas de data de forma eficiente
    date_cols = ['data_cobranca', 'data_pagamento', 'ultima_cobranca', 'datavencimento']
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
            
    return df

# --- COMPONENTES REUTILIZÁVEIS DA UI ---
def exibir_devedor_card(row, from_calendar=False):
    """Exibe os detalhes de um devedor em um card com ações. (Função mantida, pois é bem estruturada)."""
    devedor_id = int(row['id'])
    fase_atual = int(row.get('fase_cobranca', 1))

    # OTIMIZAÇÃO: Usar uma chave única e mais simples para os botões.
    key_suffix = f"{devedor_id}_{'cal' if from_calendar else 'acoes'}"

    with st.container(border=True):
        col_info, col_actions = st.columns([3, 1.2])

        with col_info:
            st.markdown(f"#### {row['nome']}")
            status_text = row['status']
            if pd.notna(row['data_cobranca']) and row['status'] == StatusDevedor.AGENDADO.value:
                status_text += f" (Próxima: {row['data_cobranca'].strftime('%d/%m/%Y')})"
            
            st.caption(f"ID Devedor: {devedor_id} | ID Pessoa: {row.get('pessoa', 'N/A')} | 📞 {row.get('telefone', 'N/A')}")
            st.markdown(f"**Status:** {status_text}")
            st.markdown(f"**Fase da Cobrança:** {fase_atual}/3")
            st.write(f"**Valor Dívida:** R$ {row['valortotal']:,.2f} | **Atraso:** {int(row['atraso'])} dias")
            
            data_pag_str = row['data_pagamento'].strftime('%d/%m/%Y') if pd.notna(row['data_pagamento']) else 'Não pago'
            ultima_cob_str = row['ultima_cobranca'].strftime('%d/%m/%Y') if pd.notna(row['ultima_cobranca']) else 'Nenhuma registrada'
            st.markdown(f"**Data Pagamento:** {data_pag_str} | **Última Cobrança:** {ultima_cob_str}")

        with col_actions:
            st.write("") # Espaçamento
            help_text = "Marca a cobrança como feita, avança a fase e agenda a próxima para 10 dias."
            if fase_atual == 3: help_text += " Esta é a última fase de avanço automático."
            
            # OTIMIZAÇÃO 2: Limpeza explícita do cache em cada ação de escrita
            if st.button("➡️ Cobrança Feita", key=f"cobranca_feita_{key_suffix}", use_container_width=True, help=help_text):
                success, msg = marcar_cobranca_feita_e_reagendar_in_db(st.session_state.db_engine, devedor_id)
                st.toast(msg, icon="✅" if success else "❌")
                if success:
                    cached_load_data.clear()
                    st.rerun()

            if st.button("✅ Marcar como Pago", key=f"pago_{key_suffix}", use_container_width=True, disabled=(row['status'] == StatusDevedor.PAGO.value)):
                success, msg = marcar_como_pago_in_db(st.session_state.db_engine, devedor_id)
                st.toast(msg, icon="✅" if success else "❌")
                if success:
                    cached_load_data.clear()
                    st.rerun()

            if st.button("❌ Remover Devedor", key=f"remover_{key_suffix}", use_container_width=True, type="primary"):
                success, msg = remover_devedor_from_db(st.session_state.db_engine, devedor_id)
                st.toast(msg, icon="✅" if success else "❌")
                if success:
                    cached_load_data.clear()
                    st.rerun()

# --- LÓGICA DAS ABAS ---
def exibir_acoes_cobranca_tab(df_completo: pd.DataFrame):
    """Exibe a aba 'Ações de Cobrança'."""
    st.header("🎯 Ações de Cobrança para Hoje")
    
    if df_completo.empty:
        st.info("Nenhum devedor encontrado no sistema.")
        return

    hoje = pd.to_datetime(date.today())

    # Filtros vetorizados do Pandas (muito mais rápido)
    nao_pago = df_completo['status'] != StatusDevedor.PAGO.value
    agendado_para_hoje = (df_completo['status'] == StatusDevedor.AGENDADO.value) & (df_completo['data_cobranca'].dt.date == hoje.date())
    requer_acao_imediata = df_completo['status'] != StatusDevedor.AGENDADO.value
    
    df_para_acoes = df_completo[nao_pago & (agendado_para_hoje | requer_acao_imediata)]

    if df_para_acoes.empty:
        st.info(f"Nenhum devedor requer ação imediata hoje ({hoje.strftime('%d/%m/%Y')}).")
        st.caption("A lista inclui devedores pendentes ou com cobrança agendada para hoje. Verifique o calendário para agendamentos futuros.")
        return

    # Filtro por nome e ordenação
    filtro_nome = st.text_input("Buscar devedor por nome na lista de ações:", key="filtro_acoes")
    df_filtrado = df_para_acoes
    if filtro_nome:
        df_filtrado = df_para_acoes[df_para_acoes['nome'].str.contains(filtro_nome, case=False, na=False)]

    sort_options = {
        "Data da Próxima Cobrança": ("data_cobranca", True),
        "Fase da Cobrança": ("fase_cobranca", True),
        "Nome (A-Z)": ("nome", True),
        "Valor da Dívida": ("valortotal", False),
        "Dias em Atraso": ("atraso", False),
    }
    sort_by_desc = st.selectbox("Ordenar por:", options=list(sort_options.keys()), key="sort_acoes")
    sort_column, ascending = sort_options[sort_by_desc]
    
    df_final = df_filtrado.sort_values(by=sort_column, ascending=ascending)
    
    st.markdown(f"--- \nExibindo **{len(df_final)}** devedor(es) para ação hoje.")
    for _, row in df_final.iterrows():
        exibir_devedor_card(row, from_calendar=False)

def exibir_calendario_cobrancas_tab(df_completo: pd.DataFrame):
    st.header("🗓️ Calendário e Agendamentos")

    if df_completo.empty:
        st.info("Nenhum devedor encontrado no banco de dados.")
        return

    with st.expander("📝 Agendar/Reagendar Cobrança Manualmente", expanded=True):
        devedores_agendaveis = df_completo[df_completo['status'] != StatusDevedor.PAGO.value].sort_values('nome')

        if devedores_agendaveis.empty:
            st.info("Nenhum devedor disponível para agendamento.")
        else:
            opcoes = {f"{row['nome']} (ID: {row['id']})": row['id'] for _, row in devedores_agendaveis.iterrows()}
            opcoes_list = ["Selecione um devedor para agendar..."] + list(opcoes.keys())
            selecao_devedor_label = st.selectbox("Buscar ou selecionar devedor:", options=opcoes_list, index=0)

            if selecao_devedor_label != "Selecione um devedor para agendar...":
                devedor_id = opcoes[selecao_devedor_label]
                devedor_selecionado = devedores_agendaveis[devedores_agendaveis['id'] == devedor_id].iloc[0]
                st.markdown("---")
                st.subheader(f"Agendar para: {devedor_selecionado['nome']}")

                data_atual = devedor_selecionado['data_cobranca']
                default_date = data_atual.date() if pd.notna(data_atual) else date.today()

                nova_data = st.date_input("Nova Data para Cobrança", value=default_date, min_value=date.today(), key=f"data_ag_{devedor_id}")
                if st.button("🗓️ Confirmar Agendamento", type="primary", key=f"conf_ag_{devedor_id}"):
                    success, msg = marcar_cobranca_feita_e_reagendar_in_db(st.session_state.db_engine, devedor_id, nova_data)
                    st.toast(msg, icon="✅" if success else "❌")
                    if success:
                        cached_load_data.clear()
                        st.rerun()

    # Pré-processamento
    df_agendados = df_completo[df_completo['data_cobranca'].notna()].copy()
    df_agendados['day'] = df_agendados['data_cobranca'].dt.day
    df_agendados['month'] = df_agendados['data_cobranca'].dt.month
    df_agendados['year'] = df_agendados['data_cobranca'].dt.year

    col1, col2 = st.columns(2)
    with col1:
        year = st.selectbox("Ano", range(date.today().year - 2, date.today().year + 3), index=2)
    with col2:
        month = st.selectbox("Mês", range(1, 13), format_func=lambda m: calendar.month_name[m], index=date.today().month - 1)

    # Eventos do mês selecionado
    events_this_month = df_agendados[(df_agendados['year'] == year) & (df_agendados['month'] == month)]
    events_by_day = events_this_month['day'].value_counts().to_dict()

    # HTML do calendário
    cal = calendar.HTMLCalendar(calendar.SUNDAY)
    month_html = cal.formatmonth(year, month)

    for day, count in events_by_day.items():
        event_html = f"<div class='event-count'>{count}</div>"
        month_html = month_html.replace(f'>{day}</td>', f'><div class="day-cell">{day}{event_html}</div></td>')

    # Destaque do dia atual
    if year == date.today().year and month == date.today().month:
        day_str = str(date.today().day)
        month_html = month_html.replace(f'>{day_str}</div>', f'><div class="day-cell today">{day_str}</div>')

    # Estilo novo
    st.markdown("""
    <style>
    table { width: 100%; border-collapse: collapse; font-family: sans-serif; }
    th { background-color: #f4f4f4; padding: 8px; text-align: center; }
    td { border: 1px solid #ccc; height: 90px; vertical-align: top; padding: 5px; text-align: right; position: relative; }
    td.noday { background-color: #f9f9f9; }
    .day-cell { font-size: 16px; position: relative; z-index: 1; }
    .event-count {
        background-color: #0d6efd;
        color: white;
        font-size: 12px;
        padding: 2px 6px;
        border-radius: 12px;
        display: inline-block;
        position: absolute;
        top: 4px;
        left: 4px;
        z-index: 2;
    }
    .today {
        background-color: #e8f4ff;
        border: 2px solid #0d6efd;
        border-radius: 6px;
        padding: 2px 6px;
        display: inline-block;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(month_html, unsafe_allow_html=True)

    # Seleção de dia
    st.session_state.selected_date = st.date_input("Ver cobranças para a data:", value=st.session_state.selected_date)
    cobrancas_no_dia = df_agendados[df_agendados['data_cobranca'].dt.date == st.session_state.selected_date]

    st.subheader(f"📌 Cobranças para {st.session_state.selected_date.strftime('%d/%m/%Y')}")
    if not cobrancas_no_dia.empty:
        for _, row in cobrancas_no_dia.iterrows():
            exibir_devedor_card(row, from_calendar=True)
    else:
        st.info("Nenhuma cobrança agendada para esta data.")

# --- PONTO DE ENTRADA PRINCIPAL ---
def main():
    st.title("📈 Sistema de Gestão de Cobranças")

    # OTIMIZAÇÃO 3: Carrega os dados uma única vez no início
    df_completo = cached_load_data(st.session_state.db_engine)

    tab1, tab2 = st.tabs(["Ações de Cobrança", "Calendário de Cobranças"])

    with tab1:
        exibir_acoes_cobranca_tab(df_completo)
    with tab2:
        exibir_calendario_cobrancas_tab(df_completo)

if __name__ == "__main__":
    main()