# Cobrancas.py
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta # Adicionado timedelta
import calendar # Para a funcionalidade de calendário HTML
import numpy as np # Adicionado para np.ceil para paginação (caso futuro)

# --- CONFIGURAÇÃO DA PÁGINA (DEVE SER A PRIMEIRA CHAMADA STREAMLIT NO SCRIPT) ---
st.set_page_config(
    page_title="Sistema de Cobranças - Agendamento",
    page_icon="📈", # Ícone atualizado
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Importações de Módulos Personalizados ---
try:
    from database import init_db, get_session, Devedor, StatusDevedor
    from devedores_service import (
        load_devedores_from_db,
        marcar_cobranca_feita_e_reagendar_in_db,
        marcar_como_pago_in_db,
        remover_devedor_from_db,
        marcar_cobranca_feita_e_reagendar_in_db # << NOVA FUNÇÃO IMPORTADA
    )
except ImportError as e:
    st.error(f"Erro ao importar módulos: {e}. Verifique se 'database.py' e 'devedores_service.py' estão corretos e no PYTHONPATH.")
    st.info("Certifique-se de que a coluna 'fase_cobranca' existe na tabela 'Devedor' e que a função 'marcar_cobranca_feita_e_reagendar_in_db' está implementada em 'devedores_service.py'.")
    st.stop()


# --- Inicialização da Conexão com o Banco de Dados e Variáveis de Estado ---
if 'db_engine' not in st.session_state:
    st.session_state.db_engine = init_db()
    # st.success("Banco de dados 'cobrancas.db' inicializado!") # Removido para interface mais limpa

if 'df_cobrancas' not in st.session_state:
    st.session_state.df_cobrancas = None

if 'should_reload_df_cobrancas' not in st.session_state:
    st.session_state.should_reload_df_cobrancas = True

# --- Funções Auxiliares de Carregamento de Dados ---
def carregar_dados_devedores():
    """Carrega ou recarrega os dados dos devedores do banco de dados."""
    if st.session_state.should_reload_df_cobrancas or st.session_state.df_cobrancas is None:
        df = load_devedores_from_db(st.session_state.db_engine)
        
        # Garante que 'fase_cobranca' exista, mesmo que temporariamente como fallback.
        # O ideal é que venha corretamente do banco de dados.
        if 'fase_cobranca' not in df.columns:
            df['fase_cobranca'] = 1 # Default para devedores antigos sem essa coluna
            # st.warning("Coluna 'fase_cobranca' não encontrada no DataFrame. Usando valor padrão 1. Verifique 'database.py' e 'devedores_service.py'.")

        # Converte colunas de data para datetime, tratando erros
        date_cols = ['data_cobranca', 'data_pagamento', 'ultima_cobranca', 'datavencimento']
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        st.session_state.df_cobrancas = df
        st.session_state.should_reload_df_cobrancas = False
    return st.session_state.df_cobrancas

# --- ABA: AÇÕES DE COBRANÇA ---
def exibir_acoes_cobranca_tab():
    st.header("🎯 Ações de Cobrança dos Devedores")
    
    df_cobrancas_completo = carregar_dados_devedores()

    if df_cobrancas_completo is None or df_cobrancas_completo.empty:
        st.info("Nenhum devedor encontrado. Adicione devedores para gerenciar as cobranças.")
        return

    # Filtra para devedores que não estão pagos
    df_para_acoes = df_cobrancas_completo[
        df_cobrancas_completo['status'] != StatusDevedor.PAGO.value
    ].copy()

    if df_para_acoes.empty:
        st.success("🎉 Todos os devedores já foram pagos ou não há devedores ativos para cobrança!")
        return

    st.write("Gerencie as cobranças dos devedores abaixo. Ao marcar 'Cobrança Feita', uma nova cobrança será agendada para daqui a 10 dias e a fase da cobrança será avançada (até a fase 3).")

    # Opções de ordenação
    sort_options = {
        "Data da Próxima Cobrança (Mais Próxima)": ("data_cobranca", True),
        "Fase da Cobrança (Menor Primeiro)": ("fase_cobranca", True),
        "Nome (A-Z)": ("nome", True),
        "Valor da Dívida (Maior Primeiro)": ("valortotal", False),
        "Dias em Atraso (Maior Primeiro)": ("atraso", False),
    }
    sort_by_desc = st.selectbox("Ordenar devedores por:", options=list(sort_options.keys()), index=0)
    sort_column, ascending_order = sort_options[sort_by_desc]
    
    # Tratamento especial para ordenação de data com NaT
    if sort_column == "data_cobranca":
        df_para_acoes['data_cobranca_sort'] = df_para_acoes['data_cobranca'].fillna(pd.Timestamp.max if ascending_order else pd.Timestamp.min)
        df_para_acoes = df_para_acoes.sort_values(by='data_cobranca_sort', ascending=ascending_order).drop(columns=['data_cobranca_sort'])
    else:
        df_para_acoes = df_para_acoes.sort_values(by=sort_column, ascending=ascending_order)

    for _, row in df_para_acoes.iterrows():
        devedor_id = int(row['id'])
        fase_atual = int(row.get('fase_cobranca', 1)) # Garante que seja int, default 1

        with st.container(border=True):
            col_info, col_actions = st.columns([3, 1.2]) # Ajuste na proporção das colunas

            with col_info:
                st.markdown(f"#### {row['nome']}")
                
                status_text = row['status']
                data_cob_fmt = "N/A"
                if pd.notna(row['data_cobranca']):
                    data_cob_fmt = row['data_cobranca'].strftime('%d/%m/%Y')
                    if row['status'] == StatusDevedor.AGENDADO.value:
                         status_text += f" (Próxima: {data_cob_fmt})"
                
                st.caption(f"ID Devedor: {devedor_id} | ID Pessoa: {row.get('pessoa', 'N/A')} | 📞 {row.get('telefone', 'N/A')}")
                st.markdown(f"**Status:** {status_text}")
                st.markdown(f"**Fase da Cobrança:** {fase_atual}/3")
                st.write(f"**Valor Dívida:** R$ {row['valortotal']:,.2f} | **Atraso:** {row['atraso']} dias")
                
                data_pag_str = row['data_pagamento'].strftime('%d/%m/%Y') if pd.notna(row['data_pagamento']) else 'Não pago'
                st.markdown(f"**Data Pagamento:** {data_pag_str}")
                
                ultima_cob_registrada_str = row['ultima_cobranca'].strftime('%d/%m/%Y') if pd.notna(row['ultima_cobranca']) else 'Nenhuma registrada'
                st.markdown(f"**Última Cobrança Registrada:** {ultima_cob_registrada_str}")

            with col_actions:
                st.write("") # Espaçador vertical
                # Botão Cobrança Feita
                help_text_cobranca_feita = "Marca a cobrança como realizada, avança a fase e agenda a próxima para 10 dias."
                if fase_atual == 3:
                    help_text_cobranca_feita += " Esta é a última fase de avanço automático."

                if st.button("➡️ Cobrança Feita", key=f"cobranca_feita_btn_{devedor_id}", use_container_width=True, help=help_text_cobranca_feita):
                    success, message = marcar_cobranca_feita_e_reagendar_in_db(st.session_state.db_engine, devedor_id)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                    st.session_state.should_reload_df_cobrancas = True
                    st.rerun()

                # Botão Marcar como Pago
                if st.button("✅ Marcar como Pago", key=f"pago_btn_{devedor_id}_acoes", use_container_width=True, disabled=(row['status'] == StatusDevedor.PAGO.value)):
                    success, message = marcar_como_pago_in_db(st.session_state.db_engine, devedor_id)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                    st.session_state.should_reload_df_cobrancas = True
                    st.rerun()

                # Botão Remover
                if st.button("❌ Remover Devedor", key=f"remover_btn_{devedor_id}_acoes", use_container_width=True):
                    confirm_remove = st.empty() # Placeholder for confirmation, simple for now
                    # Idealmente, adicionar um st.confirm ou modal aqui
                    success, message = remover_devedor_from_db(st.session_state.db_engine, devedor_id)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                    st.session_state.should_reload_df_cobrancas = True
                    st.rerun()
            st.markdown("---")


# --- ABA: CALENDÁRIO DE COBRANÇAS ---
def exibir_calendario_cobrancas_tab():
    st.header("🗓️ Calendário e Agendamentos")

    df_cobrancas_completo = carregar_dados_devedores()

    if df_cobrancas_completo is None or df_cobrancas_completo.empty:
        st.info("Nenhum devedor encontrado no banco de dados.")
        # Opção para adicionar devedores pode ser colocada aqui se houver uma página para isso.
        # st.page_link("Adicionar_Devedor.py", label="Adicionar Novo Devedor")
        return

    # Filtra o DataFrame para incluir apenas devedores PENDENTES ou AGENDADOS (não pagos).
    df_agendados = df_cobrancas_completo[
        (df_cobrancas_completo['status'] == StatusDevedor.AGENDADO.value) |
        (df_cobrancas_completo['status'] == StatusDevedor.PENDENTE.value)
    ].copy()

    # Garante que 'data_cobranca' seja um tipo date para exibição e calendário.
    df_agendados['data_cobranca_display'] = df_agendados['data_cobranca'].dt.date


    with st.expander("📝 Agendar/Reagendar Cobrança Manualmente", expanded=False):
        devedores_para_agendar = df_cobrancas_completo[
            (df_cobrancas_completo['status'] == StatusDevedor.PENDENTE.value) |
            (df_cobrancas_completo['status'] == StatusDevedor.AGENDADO.value)
        ].copy() # Considera todos não pagos para agendamento manual

        if devedores_para_agendar.empty:
            st.info("Todos os devedores já foram pagos ou não há devedores para agendar cobranças.")
        else:
            devedor_options = {
                f"{row['nome']} (ID: {row['id']}) - Dívida: R$ {row['valortotal']:.2f}": int(row['id'])
                for _, row in devedores_para_agendar.iterrows()
            }
            selected_devedor_info = st.selectbox(
                "Selecione o Devedor para Agendar/Reagendar Cobrança",
                options=["Selecione um devedor"] + list(devedor_options.keys()),
                key="select_devedor_agendamento_calendario"
            )

            if selected_devedor_info != "Selecione um devedor":
                devedor_id_selecionado = devedor_options[selected_devedor_info]
                current_devedor = df_para_acoes[df_para_acoes['id'] == devedor_id_selecionado].iloc[0] # type: ignore

                st.write(f"Devedor selecionado: **{current_devedor['nome']}** (Status: **{current_devedor['status']}**)")
                
                default_date_val = current_devedor['data_cobranca'].date() if pd.notna(current_devedor['data_cobranca']) else date.today()

                data_programada = st.date_input(
                    "Data para Programar a Cobrança",
                    value=default_date_val,
                    min_value=date.today(),
                    key=f"data_cobranca_input_calendario_{devedor_id_selecionado}"
                )

                if st.button("Agendar Cobrança", key=f"agendar_cobranca_btn_calendario_{devedor_id_selecionado}"):
                    # Agendar cobrança não altera a fase, apenas a data e status.
                    success, message = marcar_cobranca_feita_e_reagendar_in_db(st.session_state.db_engine, devedor_id_selecionado, data_programada)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                    st.session_state.should_reload_df_cobrancas = True
                    st.rerun()

    st.subheader("📅 Visualização em Calendário")
    # Seletores para o mês e ano do calendário.
    cols_calendario_select = st.columns(2)
    with cols_calendario_select[0]:
        selected_month = st.selectbox("Selecione o Mês", range(1, 13), format_func=lambda x: datetime(2000, x, 1).strftime("%B"), index=datetime.now().month - 1, key="calendar_month_select")
    with cols_calendario_select[1]:
        selected_year = st.selectbox("Selecione o Ano", range(datetime.now().year - 2, datetime.now().year + 3), index=2, key="calendar_year_select")

    # Cria uma instância do calendário HTML.
    cal = calendar.HTMLCalendar(calendar.SUNDAY) # Semana começando no Domingo
    
    # Gera o HTML base do calendário
    # Adiciona classes CSS para melhor estilização (opcional, mas recomendado)
    month_html = cal.formatmonth(selected_year, selected_month)
    month_html = month_html.replace('<table ', '<table class="calendar-table" ')
    month_html = month_html.replace(' class="day"', ' class="calendar-day"')
    month_html = month_html.replace(' class="month"', ' class="calendar-month-name"')
    month_html = month_html.replace(' class="mon"', ' class="calendar-header"') # e assim por diante para tue, wed etc.
    month_html = month_html.replace(' class="tue"', ' class="calendar-header"')
    month_html = month_html.replace(' class="wed"', ' class="calendar-header"')
    month_html = month_html.replace(' class="thu"', ' class="calendar-header"')
    month_html = month_html.replace(' class="fri"', ' class="calendar-header"')
    month_html = month_html.replace(' class="sat"', ' class="calendar-header"')
    month_html = month_html.replace(' class="sun"', ' class="calendar-header"')


    events_by_day = {}
    # Filtra devedores que têm uma data de cobrança válida e estão no mês/ano selecionados.
    df_month_events = df_agendados[
        (pd.notna(df_agendados['data_cobranca_display'])) &
        (df_agendados['data_cobranca_display'].apply(lambda x: x.month == selected_month if pd.notna(x) else False)) &
        (df_agendados['data_cobranca_display'].apply(lambda x: x.year == selected_year if pd.notna(x) else False))
    ]

    for _, row in df_month_events.iterrows():
        day = row['data_cobranca_display'].day
        if day not in events_by_day:
            events_by_day[day] = 0
        events_by_day[day] += 1 # Conta o número de cobranças

    # Injeta a contagem de eventos no HTML do calendário.
    for day, count in events_by_day.items():
        event_text = f"<br><span class='event-count'>{count} cobrança(s)</span>"
        # Regex mais robusto para substituir o dia, lidando com classes existentes
        # Procura por >DAY< onde DAY é o número do dia
        month_html = month_html.replace(
            f'>{day}</td>', # Procura o fechamento da tag anterior e o número do dia
            f'>{day}{event_text}</td>', 1 # Adiciona o texto do evento, substitui apenas 1 vez por segurança
        )
    
    # Adiciona CSS para o calendário e contagem de eventos
    st.markdown("""
    <style>
        .calendar-table { width: 100%; border-collapse: collapse; }
        .calendar-table th, .calendar-table td { border: 1px solid #ddd; text-align: center; padding: 8px; height: 70px; vertical-align: top;}
        .calendar-header { background-color: #f2f2f2; font-weight: bold; }
        .calendar-day {}
        .calendar-month-name { font-size: 1.5em; text-align: center; padding: 10px; }
        .event-count { 
            display: block; 
            margin-top: 5px; 
            font-size: 0.9em; 
            background-color: #add8e6; /* Light blue */
            color: #000;
            padding: 2px 4px; 
            border-radius: 3px; 
            font-weight: bold;
        }
        .calendar-day:has(.event-count) { /* Estiliza dias com eventos */
            background-color: #e6f7ff; /* Um azul ainda mais claro de fundo */
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(month_html, unsafe_allow_html=True)

    st.subheader("Próximas Cobranças Agendadas (Visão Geral)")
    df_proximas_cobrancas = df_agendados[
        (df_agendados['status'] == StatusDevedor.AGENDADO.value) &
        (df_agendados['data_cobranca_display'].apply(lambda x: x >= date.today() if pd.notna(x) else False)) # Checa se é hoje ou no futuro
    ].sort_values(by='data_cobranca_display')

    if not df_proximas_cobrancas.empty:
        st.dataframe(
            df_proximas_cobrancas[[
                'nome', 'valortotal', 'atraso', 'telefone', 'data_cobranca_display', 'fase_cobranca', 'status'
            ]].rename(columns={
                'data_cobranca_display': 'Data Programada',
                'fase_cobranca': 'Fase Cobrança'
            }),
            use_container_width=True,
            column_config={
                "valortotal": st.column_config.NumberColumn("Valor Total", format="R$ %.2f"),
                "atraso": st.column_config.NumberColumn("Dias em Atraso", format="%d dias"),
                "Data Programada": st.column_config.DateColumn("Data Programada", format="DD/MM/YYYY"),
                "Fase Cobrança": st.column_config.NumberColumn("Fase", format="%d/3"),
            },
            hide_index=True
        )
    else:
        st.info("Nenhuma cobrança futura agendada para exibir.")


# --- Ponto de Entrada Principal do Script ---
if __name__ == "__main__":
    st.title("📈 Sistema de Gestão de Cobranças")

    tab1, tab2 = st.tabs(["Ações de Cobrança", "Calendário de Cobranças"])

    with tab1:
        exibir_acoes_cobranca_tab()
    with tab2:
        exibir_calendario_cobrancas_tab()