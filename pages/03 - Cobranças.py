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
        remover_devedor_from_db,
        marcar_cobranca_feita_e_reagendar_in_db
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

def exibir_acoes_cobranca_tab():
    st.header("🎯 Ações de Cobrança dos Devedores")
    
    df_cobrancas_completo = carregar_dados_devedores()

    if df_cobrancas_completo is None or df_cobrancas_completo.empty:
        st.info("Nenhum devedor encontrado. Adicione devedores para gerenciar as cobranças.")
        return

    df_para_acoes = df_cobrancas_completo[
        df_cobrancas_completo['status'] != StatusDevedor.PAGO.value
    ].copy()

    if df_para_acoes.empty:
        st.success("🎉 Todos os devedores já foram pagos ou não há devedores ativos para cobrança!")
        return

    st.write("Gerencie as cobranças dos devedores abaixo. Ao marcar 'Cobrança Feita', uma nova cobrança será agendada para daqui a 10 dias e a fase da cobrança será avançada (até a fase 3).")

    sort_options = {
        "Data da Próxima Cobrança (Mais Próxima)": ("data_cobranca", True),
        "Fase da Cobrança (Menor Primeiro)": ("fase_cobranca", True),
        "Nome (A-Z)": ("nome", True),
        "Valor da Dívida (Maior Primeiro)": ("valortotal", False),
        "Dias em Atraso (Maior Primeiro)": ("atraso", False),
    }
    sort_by_desc = st.selectbox("Ordenar devedores por:", options=list(sort_options.keys()), index=0)
    sort_column, ascending_order = sort_options[sort_by_desc]
    
    if sort_column == "data_cobranca":
        df_para_acoes['data_cobranca_sort'] = df_para_acoes['data_cobranca'].fillna(pd.Timestamp.max if ascending_order else pd.Timestamp.min)
        df_para_acoes = df_para_acoes.sort_values(by='data_cobranca_sort', ascending=ascending_order).drop(columns=['data_cobranca_sort'])
    else:
        df_para_acoes = df_para_acoes.sort_values(by=sort_column, ascending=ascending_order)

    for _, row in df_para_acoes.iterrows():
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

                if st.button("➡️ Cobrança Feita", key=f"cobranca_feita_btn_{devedor_id}", use_container_width=True, help=help_text_cobranca_feita):
                    success, message = marcar_cobranca_feita_e_reagendar_in_db(st.session_state.db_engine, devedor_id)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                    st.session_state.should_reload_df_cobrancas = True
                    st.rerun()

                if st.button("✅ Marcar como Pago", key=f"pago_btn_{devedor_id}_acoes", use_container_width=True, disabled=(row['status'] == StatusDevedor.PAGO.value)):
                    success, message = marcar_como_pago_in_db(st.session_state.db_engine, devedor_id)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                    st.session_state.should_reload_df_cobrancas = True
                    st.rerun()

                if st.button("❌ Remover Devedor", key=f"remover_btn_{devedor_id}_acoes", use_container_width=True):
                    confirm_remove = st.empty()
                    success, message = remover_devedor_from_db(st.session_state.db_engine, devedor_id)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                    st.session_state.should_reload_df_cobrancas = True
                    st.rerun()
            st.markdown("---")

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

    with st.expander("📝 Agendar/Reagendar Cobrança Manualmente", expanded=False):
        devedores_para_agendar = df_cobrancas_completo[
            (df_cobrancas_completo['status'] == StatusDevedor.PENDENTE.value) |
            (df_cobrancas_completo['status'] == StatusDevedor.AGENDADO.value)
        ].copy()

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
                current_devedor = df_agendados[df_agendados['id'] == devedor_id_selecionado].iloc[0]

                st.write(f"Devedor selecionado: **{current_devedor['nome']}** (Status: **{current_devedor['status']}**)")
                
                default_date_val = current_devedor['data_cobranca'].date() if pd.notna(current_devedor['data_cobranca']) else date.today()

                data_programada = st.date_input(
                    "Data para Programar a Cobrança",
                    value=default_date_val,
                    min_value=date.today(),
                    key=f"data_cobranca_input_calendario_{devedor_id_selecionado}"
                )

                if st.button("Agendar Cobrança", key=f"agendar_cobranca_btn_calendario_{devedor_id_selecionado}"):

                    if isinstance(data_programada, datetime):
                        data_programada = data_programada.date()
                    
                    success, message = marcar_cobranca_feita_e_reagendar_in_db(
                        st.session_state.db_engine, 
                        devedor_id_selecionado,
                        data_programada  # Passando a data selecionada no calendário
                    )
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                    st.session_state.should_reload_df_cobrancas = True
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

    st.subheader("Próximas Cobranças Agendadas (Visão Geral)")
    df_proximas_cobrancas = df_agendados[
        (df_agendados['status'] == StatusDevedor.AGENDADO.value) &
        (df_agendados['data_cobranca_display'].apply(lambda x: x >= date.today() if pd.notna(x) else False))
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

if __name__ == "__main__":
    st.title("📈 Sistema de Gestão de Cobranças")

    tab1, tab2 = st.tabs(["Ações de Cobrança", "Calendário de Cobranças"])

    with tab1:
        exibir_acoes_cobranca_tab()
    with tab2:
        exibir_calendario_cobrancas_tab()