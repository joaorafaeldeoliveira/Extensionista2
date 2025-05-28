import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import calendar
import numpy as np

st.set_page_config(
    page_title="Sistema de Cobranças - Agendamento",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

try:
    from database import init_db, get_session, Devedor, StatusDevedor
    from devedores_service import (
        load_devedores_from_db,
        marcar_cobranca_feita_e_reagendar_in_db,
        marcar_como_pago_in_db,
        remover_devedor_from_db
    )
except ImportError as e:
    st.error(f"Erro ao importar módulos: {e}. Verifique se 'database.py' e 'devedores_service.py' estão corretos e no PYTHONPATH.")
    st.info("Certifique-se de que a coluna 'fase_cobranca' existe na tabela 'Devedor' e que a função 'marcar_cobranca_feita_e_reagendar_in_db' está implementada em 'devedores_service.py'.")
    st.stop()

if 'db_engine' not in st.session_state:
    st.session_state.db_engine = init_db()

if 'df_cobrancas' not in st.session_state:
    st.session_state.df_cobrancas = None

if 'should_reload_df_cobrancas' not in st.session_state:
    st.session_state.should_reload_df_cobrancas = True

if 'selected_date' not in st.session_state:
    st.session_state.selected_date = date.today()

def carregar_dados_devedores():
    if st.session_state.should_reload_df_cobrancas or st.session_state.df_cobrancas is None:
        df = load_devedores_from_db(st.session_state.db_engine)
        
        if 'fase_cobranca' not in df.columns:
            df['fase_cobranca'] = 1

        date_cols = ['data_cobranca', 'data_pagamento', 'ultima_cobranca', 'datavencimento']
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        st.session_state.df_cobrancas = df
        st.session_state.should_reload_df_cobrancas = False
    return st.session_state.df_cobrancas

def exibir_devedor_card(row, from_calendar=False):
    """Exibe os detalhes de um devedor em um card com ações."""
    devedor_id = int(row['id'])
    fase_atual = int(row.get('fase_cobranca', 1))

    with st.container(border=True):
        col_info, col_actions = st.columns([3, 1.2])

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
            st.write("")
            help_text_cobranca_feita = "Marca a cobrança como realizada, avança a fase e agenda a próxima para 10 dias."
            if fase_atual == 3:
                help_text_cobranca_feita += " Esta é a última fase de avanço automático."

            if st.button("➡️ Cobrança Feita", key=f"cobranca_feita_btn_{devedor_id}_{'cal' if from_calendar else 'acoes'}", use_container_width=True, help=help_text_cobranca_feita):
                success, message = marcar_cobranca_feita_e_reagendar_in_db(st.session_state.db_engine, devedor_id)
                if success:
                    st.success(message)
                else:
                    st.error(message)
                st.session_state.should_reload_df_cobrancas = True
                st.rerun()

            if st.button("✅ Marcar como Pago", key=f"pago_btn_{devedor_id}_{'cal' if from_calendar else 'acoes'}", use_container_width=True, disabled=(row['status'] == StatusDevedor.PAGO.value)):
                success, message = marcar_como_pago_in_db(st.session_state.db_engine, devedor_id)
                if success:
                    st.success(message)
                else:
                    st.error(message)
                st.session_state.should_reload_df_cobrancas = True
                st.rerun()

            if st.button("❌ Remover Devedor", key=f"remover_btn_{devedor_id}_{'cal' if from_calendar else 'acoes'}", use_container_width=True):
                success, message = remover_devedor_from_db(st.session_state.db_engine, devedor_id)
                if success:
                    st.success(message)
                else:
                    st.error(message)
                st.session_state.should_reload_df_cobrancas = True
                st.rerun()
        st.markdown("---")

def exibir_acoes_cobranca_tab():
    st.header("🎯 Ações de Cobrança para Hoje") # Título atualizado
    
    df_cobrancas_completo = carregar_dados_devedores() 

    if df_cobrancas_completo is None or df_cobrancas_completo.empty:
        st.info("Nenhum devedor encontrado no sistema.")
        return

    hoje = date.today()

    # --- FILTRO DE STATUS E DATA ATUALIZADO ---
    # 1. Devedor não pode estar Pago
    condicao_nao_pago = df_cobrancas_completo['status'] != StatusDevedor.PAGO.value
    
    # 2. Condições para aparecer na lista de ações de hoje:
    #    - Ou o status NÃO é 'Agendado' (ex: 'Pendente', 'Atrasado' etc.)
    #    - Ou o status É 'Agendado' E a 'data_cobranca' é hoje.
    
    # Garante que a coluna 'data_cobranca' é tratada como data para comparação
    # A função carregar_dados_devedores já deve converter para datetime.
    # Usamos .dt.date para comparar apenas a parte da data.
    condicao_para_acoes_hoje = (
        (df_cobrancas_completo['status'] != StatusDevedor.AGENDADO.value) |
        (
            (df_cobrancas_completo['status'] == StatusDevedor.AGENDADO.value) &
            (pd.to_datetime(df_cobrancas_completo['data_cobranca']).dt.date == hoje)
        )
    )
    
    df_para_acoes = df_cobrancas_completo[condicao_nao_pago & condicao_para_acoes_hoje].copy()
    # --- FIM DO FILTRO DE STATUS E DATA ---

    if df_para_acoes.empty:
        st.info(f"Nenhum devedor requer ação imediata hoje ({hoje.strftime('%d/%m/%Y')}).")
        st.caption("Isso inclui devedores pendentes ou com cobrança agendada para hoje. Verifique o calendário para agendamentos futuros.")
        return

    # --- Filtro por nome do devedor (mantido da lógica anterior) ---
    filtro_nome_acoes = st.text_input(
        "Buscar devedor por nome na lista abaixo:", # Label atualizado
        key="filtro_nome_devedor_acoes_hoje" # Chave atualizada para evitar conflito se houver outra
    )

    df_filtrado_nome = df_para_acoes 
    if filtro_nome_acoes:
        df_filtrado_nome = df_para_acoes[
            df_para_acoes['nome'].str.contains(filtro_nome_acoes, case=False, na=False)
        ]

    if df_filtrado_nome.empty:
        if filtro_nome_acoes: 
            st.info(f"Nenhum devedor encontrado com o nome '{filtro_nome_acoes}' que requer ação hoje.")
        # Se não há filtro de nome, mas df_para_acoes (após filtro de data/status) já estava vazio,
        # a mensagem anterior ("Nenhum devedor requer ação imediata hoje") já foi exibida.
        return 
    
    st.write("Gerencie as cobranças dos devedores listados abaixo. Estes são os devedores pendentes ou com cobrança agendada para hoje.")

    # Lógica de ordenação (mantida da lógica anterior)
    sort_options = {
        "Data da Próxima Cobrança (Mais Próxima)": ("data_cobranca", True), # Relevante para os agendados de hoje
        "Fase da Cobrança (Menor Primeiro)": ("fase_cobranca", True),
        "Nome (A-Z)": ("nome", True),
        "Valor da Dívida (Maior Primeiro)": ("valortotal", False),
        "Dias em Atraso (Maior Primeiro)": ("atraso", False), 
    }
    sort_by_desc = st.selectbox(
        "Ordenar devedores por:", 
        options=list(sort_options.keys()), 
        index=0, 
        key="selectbox_ordenar_devedores_acoes_hoje" 
    )
    sort_column, ascending_order = sort_options[sort_by_desc]
    
    df_final_para_exibir = df_filtrado_nome.copy()

    if sort_column == "data_cobranca":
        fill_value_for_nat = pd.Timestamp.max 
        if not ascending_order: 
            fill_value_for_nat = pd.Timestamp.min 
        df_final_para_exibir['data_cobranca_sort'] = df_final_para_exibir['data_cobranca'].fillna(fill_value_for_nat)
        df_final_para_exibir = df_final_para_exibir.sort_values(
            by=['data_cobranca_sort', 'nome'], 
            ascending=[ascending_order, True] 
        ).drop(columns=['data_cobranca_sort'])
    elif sort_column == "atraso":
        df_final_para_exibir['atraso_sort'] = pd.to_numeric(df_final_para_exibir['atraso'], errors='coerce').fillna(0)
        df_final_para_exibir = df_final_para_exibir.sort_values(
            by=['atraso_sort', 'nome'], 
            ascending=[ascending_order, True]
        ).drop(columns=['atraso_sort'])
    else:
        df_final_para_exibir = df_final_para_exibir.sort_values(
            by=[sort_column, 'nome'], 
            ascending=[ascending_order, True]
        )
    
    st.markdown(f"--- \nExibindo **{len(df_final_para_exibir)}** devedor(es) para ação hoje.")

    if not df_final_para_exibir.empty:
        for _, row in df_final_para_exibir.iterrows():
            exibir_devedor_card(row, from_calendar=False) 
    elif not filtro_nome_acoes:
        # Esta condição é redundante se a verificação df_para_acoes.empty já ocorreu
        st.info("Não há devedores para exibir com os critérios atuais para hoje.")

def exibir_calendario_cobrancas_tab():
    st.header("🗓️ Calendário e Agendamentos")

    df_cobrancas_completo = carregar_dados_devedores()

    if df_cobrancas_completo is None or df_cobrancas_completo.empty:
        st.info("Nenhum devedor encontrado no banco de dados.")
        return

    df_agendados = df_cobrancas_completo[
        (df_cobrancas_completo['status'] == StatusDevedor.AGENDADO.value) |
        (df_cobrancas_completo['status'] == StatusDevedor.PENDENTE.value)
    ].copy()

    df_agendados['data_cobranca_display'] = df_agendados['data_cobranca'].dt.date

    with st.expander("📝 Agendar/Reagendar Cobrança Manualmente", expanded=True): # Pode deixar expanded=True para melhor UX
        devedores_para_agendar = df_cobrancas_completo[
            (df_cobrancas_completo['status'] == StatusDevedor.PENDENTE.value) |
            (df_cobrancas_completo['status'] == StatusDevedor.AGENDADO.value)
        ].copy()

        if devedores_para_agendar.empty:
            st.info("Todos os devedores já foram pagos ou não há devedores para agendar cobranças.")
        else:
            # Inicializa o estado da sessão para o devedor selecionado e o filtro
            if 'devedor_id_agendamento_selecionado' not in st.session_state:
                st.session_state.devedor_id_agendamento_selecionado = None
            if 'filtro_nome_devedor_agendamento_val' not in st.session_state: # Para controlar o valor do text_input
                st.session_state.filtro_nome_devedor_agendamento_val = ""

            # Campo de texto para filtrar devedores
            # Usamos um valor do session_state para poder limpá-lo programaticamente se necessário
            # No entanto, Streamlit não tem uma forma direta de resetar o widget text_input para "" via código
            # a não ser mudando sua chave, o que pode ter outros efeitos.
            # O usuário geralmente apaga o texto para uma nova busca.
            filtro_nome_devedor = st.text_input(
                "Digite o nome do devedor para buscar:",
                value=st.session_state.filtro_nome_devedor_agendamento_val, # Usar valor do estado se precisar controlar
                key="filtro_nome_devedor_agendamento_input" # Chave única
            )
            # Atualiza o valor no session_state para persistir entre execuções, se necessário
            st.session_state.filtro_nome_devedor_agendamento_val = filtro_nome_devedor

            devedores_filtrados_df = pd.DataFrame() # Inicializa como DataFrame vazio

            if filtro_nome_devedor:
                devedores_filtrados_df = devedores_para_agendar[
                    devedores_para_agendar['nome'].str.contains(filtro_nome_devedor, case=False, na=False)
                ]

                if not devedores_filtrados_df.empty:
                    MAX_DEVEDORES_EXIBIDOS_BOTAO = 7 
                    
                    devedores_para_exibir = devedores_filtrados_df
                    if len(devedores_filtrados_df) > MAX_DEVEDORES_EXIBIDOS_BOTAO:
                        st.info(f"Encontrados {len(devedores_filtrados_df)} devedores. Mostrando os primeiros {MAX_DEVEDORES_EXIBIDOS_BOTAO}. Refine sua busca para ver outros.")
                        devedores_para_exibir = devedores_filtrados_df.head(MAX_DEVEDORES_EXIBIDOS_BOTAO)
                    
                    st.write("Devedores encontrados (clique para selecionar):")
                    cols = st.columns(3) 
                    col_idx = 0
                    for _, row in devedores_para_exibir.iterrows():
                        devedor_label = f"{row['nome']} (ID: {row['id']})" 
      
                        with cols[col_idx % len(cols)]:
                            if st.button(devedor_label, key=f"btn_sel_dev_ag_{row['id']}", use_container_width=True):
                                st.session_state.devedor_id_agendamento_selecionado = int(row['id'])
                                
                                st.rerun()
                        col_idx += 1

                elif len(filtro_nome_devedor) > 0:
                    st.warning(f"Nenhum devedor encontrado com o nome '{filtro_nome_devedor}'.")
                    st.session_state.devedor_id_agendamento_selecionado = None 
            
           
            if not filtro_nome_devedor and st.session_state.devedor_id_agendamento_selecionado is not None:
                 st.session_state.devedor_id_agendamento_selecionado = None
                 st.rerun()


            if not filtro_nome_devedor and st.session_state.devedor_id_agendamento_selecionado is None:
                st.caption("Digite parte do nome do devedor para iniciar a busca.")

            if st.session_state.get('devedor_id_agendamento_selecionado') is not None:
                devedor_id_selecionado_para_agendar = st.session_state.devedor_id_agendamento_selecionado
                
                current_devedor_data = df_cobrancas_completo[df_cobrancas_completo['id'] == devedor_id_selecionado_para_agendar]

                if not current_devedor_data.empty:
                    current_devedor = current_devedor_data.iloc[0]
                    
                    st.markdown("---")
                    st.subheader(f"Agendar para: {current_devedor['nome']}")
                    st.write(f"ID: {current_devedor['id']} | Status Atual: **{current_devedor['status']}** | Dívida: R$ {current_devedor['valortotal']:.2f}")
                    
                    data_cobranca_atual_val = current_devedor['data_cobranca']
                    default_date_val = data_cobranca_atual_val.date() if pd.notna(data_cobranca_atual_val) else date.today()

                    nova_data_programada = st.date_input(
                        "Nova Data para Programar a Cobrança",
                        value=default_date_val,
                        min_value=date.today(),
                        key=f"nova_data_cobranca_cal_{devedor_id_selecionado_para_agendar}"
                    )

                    if st.button("🗓️ Confirmar Agendamento", key=f"confirmar_agendamento_btn_cal_{devedor_id_selecionado_para_agendar}", type="primary"):
                        if isinstance(nova_data_programada, datetime):
                            nova_data_programada = nova_data_programada.date()
                        
                    
                        success, message = marcar_cobranca_feita_e_reagendar_in_db(
                            st.session_state.db_engine, 
                            devedor_id_selecionado_para_agendar,
                            nova_data_programada
                        )
                        if success:
                            st.success(f"Cobrança para {current_devedor['nome']} (re)agendada: {message}")
                            st.session_state.devedor_id_agendamento_selecionado = None 
                            st.session_state.filtro_nome_devedor_agendamento_val = "" 
                        else:
                            st.error(f"Erro ao (re)agendar para {current_devedor['nome']}: {message}")
                        
                        st.session_state.should_reload_df_cobrancas = True
                        st.rerun()
                    
                    if st.button("Cancelar Seleção", key=f"cancelar_sel_dev_ag_{devedor_id_selecionado_para_agendar}"):
                        st.session_state.devedor_id_agendamento_selecionado = None
                        st.rerun()

                else:
                    st.error("Devedor selecionado não encontrado nos dados. Por favor, tente novamente.")
                    st.session_state.devedor_id_agendamento_selecionado = None
                    st.rerun()
      

    st.subheader("📅 Visualização em Calendário")
    cols_calendario_select = st.columns(2)
    with cols_calendario_select[0]:
        selected_month = st.selectbox("Selecione o Mês", range(1, 13), format_func=lambda x: datetime(2000, x, 1).strftime("%B"), index=datetime.now().month - 1, key="calendar_month_select")
    with cols_calendario_select[1]:
        selected_year = st.selectbox("Selecione o Ano", range(datetime.now().year - 2, datetime.now().year + 3), index=2, key="calendar_year_select")

    cal = calendar.HTMLCalendar(calendar.SUNDAY)
    month_html = cal.formatmonth(selected_year, selected_month)

    month_html = month_html.replace('<table border="0" cellpadding="0" cellspacing="0" class="month">', '<table class="calendar-table">')
    month_html = month_html.replace('<thead>', '')
    month_html = month_html.replace('</thead>', '')
    month_html = month_html.replace('<th class="month"', '<th class="calendar-month-name"')
    for day_abbr in ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]:
        month_html = month_html.replace(f'<th class="{day_abbr}">', f'<th class="calendar-header {day_abbr}">')
    month_html = month_html.replace('<td class="', '<td class="calendar-day ')

    events_by_day = {}
    if 'df_agendados' in locals() and df_agendados is not None and 'data_cobranca_display' in df_agendados.columns:
        df_month_events = df_agendados[
            (pd.notna(df_agendados['data_cobranca_display'])) &
            (df_agendados['data_cobranca_display'].apply(lambda x: x.month == selected_month if pd.notna(x) else False)) &
            (df_agendados['data_cobranca_display'].apply(lambda x: x.year == selected_year if pd.notna(x) else False))
        ]

        for _, row in df_month_events.iterrows():
            day = row['data_cobranca_display'].day
            if day not in events_by_day:
                events_by_day[day] = 0
            events_by_day[day] += 1
    else:
        st.warning("DataFrame 'df_agendados' não encontrado ou coluna 'data_cobranca_display' ausente.")
        df_month_events = pd.DataFrame()

    for day, count in events_by_day.items():
        event_text = f"<br><span class='event-count'>{count} cobrança(s)</span>"
        month_html = month_html.replace(
            f'>{day}</td>',
            f'>{day}{event_text}</td>', 1 
        )
        month_html = month_html.replace(
            f'>{day}\n</td>',
            f'>{day}{event_text}\n</td>', 1
        )

    today = date.today()
    if selected_year == today.year and selected_month == today.month:
        day_str_today = str(today.day)
        import re
        month_html = re.sub(
            r'(class="[^"]*")(\s*>\s*' + re.escape(day_str_today) + r'\b)',
            r'\1 current-day"\2',
            month_html,
            count=1
        )

    st.markdown(f"""
    <style>
        .calendar-table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            box-shadow: 0 6px 12px rgba(0,0,0,0.15);
            border-radius: 10px;
            overflow: hidden;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}
        .calendar-month-name {{
            font-size: 1.6em;
            text-align: center;
            padding: 18px 10px;
            font-weight: 600;
            color: #ffffff;
            background-color: #007bff;
            border-bottom: 1px solid #0056b3;
        }}
        .calendar-header {{
            background-color: #f8f9fa;
            color: #495057;
            font-weight: 600;
            font-size: 0.85em;
            text-transform: uppercase;
            padding: 12px 8px;
            border-bottom: 1px solid #dee2e6;
        }}
        .calendar-table td.calendar-day {{
            border: 1px solid #e9ecef;
            text-align: center;
            padding: 8px;
            height: 90px;
            vertical-align: top;
            background-color: #fff;
            transition: background-color 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
            font-size: 0.95em;
            color: #000000;
        }}
        .calendar-table td.calendar-day:hover {{
            background-color: #e9f5ff;
            box-shadow: inset 0 0 5px rgba(0,123,255,0.1);
        }}
        .calendar-table td.noday {{
            background-color: #f8f9fa;
            color: #adb5bd;
        }}
        .calendar-table td.calendar-day.noday:hover {{
            background-color: #f8f9fa;
            box-shadow: none;
        }}
        .calendar-table td.current-day {{
            background-color: #007bff;
            color: #ffffff;
            border: 2px solid #0056b3;
            font-weight: 700;
            position: relative;
        }}
        .calendar-table td.current-day .event-count {{
            background-color: #ffffff;
            color: #007bff;
            border: 1px solid #007bff;
        }}
        .calendar-table td.current-day:hover {{
            background-color: #0069d9;
        }}
        .event-count {{ 
            display: inline-block;
            margin-top: 6px; 
            font-size: 0.8em; 
            background-color: #28a745;
            color: white;
            padding: 3px 7px; 
            border-radius: 12px;
            font-weight: 500;
            line-height: 1.1;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
    </style>
    """, unsafe_allow_html=True)

    st.markdown(month_html, unsafe_allow_html=True)

    st.session_state.selected_date = st.date_input(
        "Selecione uma data para ver as cobranças",
        value=st.session_state.selected_date,
        key="date_picker_for_cobrancas"
    )

    st.subheader(f"📌 Cobranças para {st.session_state.selected_date.strftime('%d/%m/%Y')}")
    
    df_cobrancas_dia = df_agendados[
        (pd.notna(df_agendados['data_cobranca_display'])) &
        (df_agendados['data_cobranca_display'] == st.session_state.selected_date)
    ]
    
    if not df_cobrancas_dia.empty:
        for _, row in df_cobrancas_dia.iterrows():
            exibir_devedor_card(row, from_calendar=True)
    else:
        st.info(f"Nenhuma cobrança agendada para {st.session_state.selected_date.strftime('%d/%m/%Y')}")

if __name__ == "__main__":
    st.title("📈 Sistema de Gestão de Cobranças")

    tab1, tab2 = st.tabs(["Ações de Cobrança", "Calendário de Cobranças"])

    with tab1:
        exibir_acoes_cobranca_tab()
    with tab2:
        exibir_calendario_cobrancas_tab()