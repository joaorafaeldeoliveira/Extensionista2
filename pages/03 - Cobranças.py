# Cobrancas.py
import streamlit as st
import pandas as pd
from datetime import datetime, date
import calendar # Para o calendário

# --- CONFIGURAÇÃO DA PÁGINA (DEVE SER A PRIMEIRA CHAMADA STREAMLIT) ---
st.set_page_config(
    page_title="Sistema de Cobranças - Agendamento",
    page_icon="🗓️",
    layout="wide",
    initial_sidebar_state="collapsed" # Pode ser collapsed ou expanded
)

from database import init_db, get_session, Devedor, StatusDevedor
from devedores_service import (
    load_devedores_from_db,
    agendar_cobranca_in_db,
    marcar_como_pago_in_db # Pode ser usado aqui também
)

if 'db_engine' not in st.session_state:
    st.session_state.db_engine = init_db()
if 'df_cobrancas' not in st.session_state: # DataFrame específico para cobranças
    st.session_state.df_cobrancas = None
if 'should_reload_df_cobrancas' not in st.session_state:
    st.session_state.should_reload_df_cobrancas = True


def exibir_calendario_cobrancas_tab():
    st.title("🗓 Calendário de Cobranças")

    # Carrega dados do DB na primeira execução ou se a flag `should_reload_df_cobrancas` for True
    if st.session_state.should_reload_df_cobrancas:
        # Carrega o DF completo com as colunas de cobrança
        st.session_state.df_cobrancas = load_devedores_from_db(st.session_state.db_engine)
        st.session_state.should_reload_df_cobrancas = False

    if st.session_state.df_cobrancas.empty:
        st.info("Nenhuma cobrança agendada encontrada no banco de dados.")
        return

    df_agendados = st.session_state.df_cobrancas[
        (st.session_state.df_cobrancas['status'] == StatusDevedor.AGENDADO.value) |
        (st.session_state.df_cobrancas['status'] == StatusDevedor.PENDENTE.value)
    ].copy() # Trabalha apenas com devedores não pagos ou agendados

    # Garante que 'data_cobranca' seja um tipo datetime antes de acessar .dt.date
    if 'data_cobranca' in df_agendados.columns and pd.api.types.is_datetime64_any_dtype(df_agendados['data_cobranca']):
        df_agendados['data_cobranca_display'] = df_agendados['data_cobranca'].dt.date.fillna(pd.NaT)
    else:
        df_agendados['data_cobranca_display'] = pd.Series([pd.NaT] * len(df_agendados)) # Coluna vazia se não for datetime

    st.subheader("Agendar Nova Cobrança / Gerenciar Agendamentos")

    # Seção para agendar/reagendar cobrança
    with st.expander("📝 Agendar/Reagendar Cobrança", expanded=False):
        devedores_pendentes_ou_agendados = df_agendados[
            (df_agendados['status'] == StatusDevedor.PENDENTE.value) |
            (df_agendados['status'] == StatusDevedor.AGENDADO.value)
        ]

        if devedores_pendentes_ou_agendados.empty:
            st.info("Todos os devedores já foram pagos ou não há devedores para agendar.")
        else:
            devedor_options = ["Selecione um devedor"] + [
                f"{row['nome']} (ID: {row['id']}) - Dívida: R$ {row['valortotal']:.2f}"
                for index, row in devedores_pendentes_ou_agendados.iterrows()
            ]
            selected_devedor_info = st.selectbox(
                "Selecione o Devedor para Agendar/Reagendar Cobrança",
                options=devedor_options,
                key="select_devedor_agendamento"
            )

            if selected_devedor_info != "Selecione um devedor":
                devedor_id = int(selected_devedor_info.split("(ID: ")[1].split(")")[0])
                current_devedor = df_agendados[df_agendados['id'] == devedor_id].iloc[0]

                st.write(f"Devedor selecionado: **{current_devedor['nome']}**")
                st.write(f"Status atual: **{current_devedor['status']}**")

                # Se já tiver uma data de cobrança, sugere no seletor
                default_date = current_devedor['data_cobranca_display'] if pd.notna(current_devedor['data_cobranca_display']) else date.today()

                data_programada = st.date_input(
                    "Data para Programar a Cobrança",
                    value=default_date,
                    min_value=date.today(), # Não permite agendar no passado
                    key=f"data_cobranca_input_{devedor_id}"
                )

                if st.button("Agendar Cobrança", key=f"agendar_cobranca_btn_{devedor_id}"):
                    success, message = agendar_cobranca_in_db(st.session_state.db_engine, devedor_id, data_programada)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                    st.session_state.should_reload_df_cobrancas = True
                    st.rerun()

    st.subheader("Próximas Cobranças Agendadas")

    df_proximas_cobrancas = df_agendados[
        (df_agendados['status'] == StatusDevedor.AGENDADO.value) &
        (df_agendados['data_cobranca_display'] >= date.today())
    ].sort_values(by='data_cobranca_display')

    if not df_proximas_cobrancas.empty:
        st.dataframe(
            df_proximas_cobrancas[[
                'nome', 'valortotal', 'atraso', 'telefone', 'data_cobranca_display', 'ultima_cobranca', 'status'
            ]].rename(columns={
                'data_cobranca_display': 'Data Programada',
                'ultima_cobranca': 'Última Cobrança'
            }),
            use_container_width=True,
            column_config={
                "valortotal": st.column_config.NumberColumn(
                    "Valor Total", format="R$ %.2f"
                ),
                "atraso": st.column_config.NumberColumn(
                    "Dias em Atraso", format="%d dias"
                ),
                "Data Programada": st.column_config.DateColumn(
                    "Data Programada", format="DD/MM/YYYY"
                ),
                "Última Cobrança": st.column_config.DateColumn(
                    "Última Cobrança", format="DD/MM/YYYY"
                )
            },
            hide_index=True
        )
    else:
        st.info("Nenhuma cobrança futura agendada.")

    st.subheader("Eventos de Cobrança do Mês")

    selected_month = st.selectbox("Selecione o Mês", range(1, 13), index=datetime.now().month - 1)
    selected_year = st.selectbox("Selecione o Ano", range(datetime.now().year - 1, datetime.now().year + 2), index=1)

    cal = calendar.HTMLCalendar(calendar.SUNDAY)
    month_html = cal.formatmonth(selected_year, selected_month)

    # Adicionar eventos ao calendário
    events = {}
    # Filtra devedores para o mês e ano selecionados que tenham data_cobranca válida
    df_month_events = df_agendados[
        (pd.notna(df_agendados['data_cobranca_display'])) &
        (df_agendados['data_cobranca_display'].apply(lambda x: x.month) == selected_month) &
        (df_agendados['data_cobranca_display'].apply(lambda x: x.year) == selected_year)
    ]


    for index, row in df_month_events.iterrows():
        day = row['data_cobranca_display'].day
        if day not in events:
            events[day] = []
        events[day].append(f"**{row['nome']}** (R$ {row['valortotal']:.2f})")

    for day, day_events in events.items():
        event_html = "<br>".join(day_events)
        month_html = month_html.replace(
            f'<td class="day">{day}</td>',
            f'<td class="day"><b>{day}</b><br><small>{event_html}</small></td>'
        )

    st.markdown(month_html, unsafe_allow_html=True)


if __name__ == "__main__":
    exibir_calendario_cobrancas_tab()