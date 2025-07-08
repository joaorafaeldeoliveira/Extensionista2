import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import calendar
import math

st.set_page_config(page_title="Sistema de Cobranças - Agendamento",
                   page_icon="📈",
                   layout="wide",
                   initial_sidebar_state="collapsed")

try:
    from database import init_db, Devedor, StatusDevedor
    from devedores_service import (
        marcar_cobranca_feita_e_reagendar_in_db, marcar_como_pago_in_db,
        remover_devedor_from_db, get_devedores_para_acoes_count,
        get_devedores_para_acoes_paginated, load_devedores_from_db,
        get_devedores_para_dia_paginated, get_devedores_para_dia_count)
except ImportError as e:
    st.error(
        f"Erro ao importar módulos: {e}. Verifique se os arquivos de serviço e banco de dados estão corretos."
    )
    st.stop()

if 'db_engine' not in st.session_state:
    st.session_state.db_engine = init_db()
if 'selected_date' not in st.session_state:
    st.session_state.selected_date = date.today()
if 'page_num_acoes' not in st.session_state:
    st.session_state.page_num_acoes = 0
if 'page_num_cal' not in st.session_state:
    st.session_state.page_num_cal = 0



def process_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Função auxiliar para processar o DataFrame recebido do banco."""
    if df.empty:
        return df

    if 'fase_cobranca' not in df.columns:
        df['fase_cobranca'] = 1
    else:
        df['fase_cobranca'] = pd.to_numeric(
            df['fase_cobranca'], errors='coerce').fillna(1).astype(int)

    date_cols = [
        'data_cobranca', 'data_pagamento', 'ultima_cobranca', 'datavencimento'
    ]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    return df


def exibir_devedor_card(row, from_calendar=False):
    """Exibe o card do devedor com as ações."""
    devedor_id = int(row['id'])
    fase_atual = int(row.get('fase_cobranca', 1))
    key_suffix = f"{devedor_id}_{'cal' if from_calendar else 'acoes'}"

    with st.container(border=True):
        col_info, col_actions = st.columns([3, 1.2])

        with col_info:
            st.markdown(f"#### {row.get('nome', 'Nome não encontrado')}")
            status_text = row.get('status', 'Status desconhecido')
            data_cobranca_val = pd.to_datetime(row.get('data_cobranca'))

            if pd.notna(data_cobranca_val
                        ) and status_text == StatusDevedor.AGENDADO.value:
                status_text += f" (Próxima: {data_cobranca_val.strftime('%d/%m/%Y')})"

            st.caption(
                f"ID Devedor: {devedor_id} | ID Pessoa: {row.get('pessoa', 'N/A')} | 📞 {row.get('telefone', 'N/A')}"
            )
            st.markdown(f"**Status:** {status_text}")
            st.markdown(f"**Fase da Cobrança:** {fase_atual}/3")

            atraso_str = 'N/A'
            if 'atraso' in row and pd.notna(row['atraso']):
                atraso_str = f"{int(row['atraso'])} dias"
            elif 'datavencimento' in row and pd.notna(
                    row.get('datavencimento')):
                atraso_dias = (datetime.now() -
                               pd.to_datetime(row['datavencimento'])).days
                atraso_str = f"{atraso_dias} dias"

            valor_total = row.get('valortotal', 0)
            st.write(
                f"**Valor Dívida:** R$ {valor_total:,.2f} | **Atraso:** {atraso_str}"
            )

            data_pag_val = pd.to_datetime(row.get('data_pagamento'))
            ultima_cob_val = pd.to_datetime(row.get('ultima_cobranca'))

            data_pag_str = data_pag_val.strftime('%d/%m/%Y') if pd.notna(
                data_pag_val) else 'Não pago'
            ultima_cob_str = ultima_cob_val.strftime('%d/%m/%Y') if pd.notna(
                ultima_cob_val) else 'Nenhuma registrada'
            st.markdown(
                f"**Data Pagamento:** {data_pag_str} | **Última Cobrança:** {ultima_cob_str}"
            )

        with col_actions:
            st.write("")

            def clear_all_caches_and_rerun():
                st.cache_data.clear()
                st.rerun()

            if st.button("➡️ Cobrança Feita",
                         key=f"cobranca_feita_{key_suffix}",
                         use_container_width=True):
                success, msg = marcar_cobranca_feita_e_reagendar_in_db(
                    st.session_state.db_engine, devedor_id)
                st.toast(msg, icon="✅" if success else "❌")
                if success:
                    clear_all_caches_and_rerun()

            if st.button("✅ Marcar como Pago",
                         key=f"pago_{key_suffix}",
                         use_container_width=True,
                         disabled=(str(
                             row.get('status')) == StatusDevedor.PAGO.value)):
                success, msg = marcar_como_pago_in_db(
                    st.session_state.db_engine, devedor_id)
                st.toast(msg, icon="✅" if success else "❌")
                if success:
                    clear_all_caches_and_rerun()
            if st.button("❌ Remover Devedor",
                         key=f"remover_{key_suffix}",
                         use_container_width=True,
                         type="primary"):
                success, msg = remover_devedor_from_db(
                    st.session_state.db_engine, devedor_id)
                st.toast(msg, icon="✅" if success else "❌")
                if success: clear_all_caches_and_rerun()

       
            with st.expander("📅 Agendar Manualmente"):
                min_data = date.today()
                max_data = date.today() + timedelta(days=3650)
                data_atual = row['data_cobranca']
                default_date = data_atual.date() if pd.notna(
                    data_atual) else min_data

                
                if default_date < min_data: default_date = min_data
                if default_date > max_data: default_date = max_data

                nova_data = st.date_input(
                    label="Nova data de cobrança",
                    value=default_date,
                    min_value=min_data,
                    max_value=max_data,
                    key=f"manual_agendamento_data_{key_suffix}")

                if st.button("📌 Agendar",
                             key=f"manual_agendar_{key_suffix}",
                             use_container_width=True):
                    success, msg = marcar_cobranca_feita_e_reagendar_in_db(
                        st.session_state.db_engine, devedor_id, nova_data)
                    st.toast(msg, icon="✅" if success else "❌")
                    if success: clear_all_caches_and_rerun()



def exibir_acoes_cobranca_tab():
    """Exibe a aba 'Ações de Cobrança' com paginação."""
    st.header("🎯 Ações de Cobrança para Hoje")

    PAGE_SIZE = 50

    col1, col2 = st.columns(2)
    with col1:
        filtro_nome = st.text_input("Buscar devedor por nome:",
                                    key="filtro_acoes")
    with col2:
        sort_options = {
            "Data da Próxima Cobrança": ("data_cobranca", True),
            "Fase da Cobrança": ("fase_cobranca", True),
            "Nome (A-Z)": ("nome", True),
            "Valor da Dívida": ("valortotal", False),
            "Dias em Atraso": ("atraso", False),
        }
        sort_by_desc = st.selectbox("Ordenar por:",
                                    options=list(sort_options.keys()),
                                    key="sort_acoes")
        sort_column, ascending = sort_options[sort_by_desc]

    total_items = get_devedores_para_acoes_count(st.session_state.db_engine,
                                                 filtro_nome=filtro_nome)

    if total_items == 0:
        st.info(
            f"Nenhum devedor requer ação imediata hoje ({date.today().strftime('%d/%m/%Y')})."
        )
        return

    total_pages = math.ceil(total_items / PAGE_SIZE)
    st.session_state.page_num_acoes = max(
        0, min(st.session_state.page_num_acoes, total_pages - 1))

    @st.cache_data(show_spinner="Carregando devedores...", ttl=60)
    def cached_get_paginated_data(page, page_size, sort_col, sort_asc, nome):
        df = get_devedores_para_acoes_paginated(st.session_state.db_engine,
                                                page, page_size, sort_col,
                                                sort_asc, nome)
        return process_dataframe(df)

    df_pagina = cached_get_paginated_data(st.session_state.page_num_acoes,
                                          PAGE_SIZE, sort_column, ascending,
                                          filtro_nome)

    st.markdown(
        f"--- \nExibindo **{len(df_pagina)}** de **{total_items}** devedor(es)."
    )

    col_pag_1, col_pag_2, col_pag_3 = st.columns([1, 2, 1])
    if col_pag_1.button("⬅️ Anterior",
                        use_container_width=True,
                        disabled=(st.session_state.page_num_acoes == 0)):
        st.session_state.page_num_acoes -= 1
        st.rerun()
    col_pag_2.write(
        f"<div style='text-align: center;'>Página {st.session_state.page_num_acoes + 1} de {total_pages}</div>",
        unsafe_allow_html=True)
    if col_pag_3.button("Próxima ➡️",
                        use_container_width=True,
                        disabled=(st.session_state.page_num_acoes
                                  >= total_pages - 1)):
        st.session_state.page_num_acoes += 1
        st.rerun()

    st.markdown("---")

    if df_pagina.empty and total_items > 0:
        st.warning(
            "Não foram encontrados resultados para esta página. Tentando voltar para a primeira página..."
        )
        st.session_state.page_num_acoes = 0
        st.rerun()

    for _, row in df_pagina.iterrows():
        exibir_devedor_card(row, from_calendar=False)


def exibir_calendario_cobrancas_tab():
    st.header("🗓️ Calendário e Agendamentos")
    PAGE_SIZE_CAL = 50

    @st.cache_data(show_spinner="Carregando dados para calendário...", ttl=60)
    def load_full_data_for_calendar(_db_engine):
        df = load_devedores_from_db(_db_engine)
        return process_dataframe(df)

    df_completo = load_full_data_for_calendar(st.session_state.db_engine)

    if df_completo.empty:
        st.info("Nenhum devedor encontrado no banco de dados.")
        return

    st.markdown("---")
    df_agendados = df_completo[df_completo['data_cobranca'].notna()].copy()


    col1, col2 = st.columns(2)
    year = col1.selectbox("Ano",
                          range(date.today().year - 2,
                                date.today().year + 3),
                          index=2,
                          key="cal_year")
    month = col2.selectbox("Mês",
                           range(1, 13),
                           format_func=lambda m: calendar.month_name[m],
                           index=date.today().month - 1,
                           key="cal_month")

    cal = calendar.HTMLCalendar(calendar.SUNDAY)
    month_html = cal.formatmonth(year, month)

    if not df_agendados.empty:
        df_agendados['day'] = df_agendados['data_cobranca'].dt.day
        df_agendados['month'] = df_agendados['data_cobranca'].dt.month
        df_agendados['year'] = df_agendados['data_cobranca'].dt.year

        events_this_month = df_agendados[(df_agendados['year'] == year)
                                         & (df_agendados['month'] == month)]
        events_by_day = events_this_month['day'].value_counts().to_dict()

        for day, count in events_by_day.items():
            event_html = f"<div class='event-count'>{count}</div>"
            month_html = month_html.replace(
                f'>{day}</td>',
                f'><div class="day-cell">{day}{event_html}</div></td>', 1)

    if year == date.today().year and month == date.today().month:
        day_str = str(date.today().day)

        month_html = month_html.replace(
            f'<div class="day-cell">{day_str}',
            f'<div class="day-cell today">{day_str}')
    st.markdown(month_html, unsafe_allow_html=True)
    st.markdown(
        """<style> table { width: 100%; border-collapse: collapse; } th { background-color: #f4f4f4; padding: 8px; text-align: center; } td { border: 1px solid #ccc; height: 90px; vertical-align: top; padding: 5px; text-align: right; position: relative; } td.noday { background-color: #f9f9f9; } .day-cell { font-size: 16px; } .event-count { background-color: #0d6efd; color: white; font-size: 12px; padding: 2px 6px; border-radius: 12px; display: inline-block; position: absolute; top: 4px; left: 4px; } .today { background-color: #e8f4ff; border: 2px solid #0d6efd; border-radius: 6px; padding: 2px 6px; display: inline-block; } </style>""",
        unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Ver cobranças para uma data específica")
    selected_date_input = st.date_input("Selecione a data:",
                                        value=st.session_state.selected_date,
                                        key="cal_date_selector")

    if selected_date_input != st.session_state.selected_date:
        st.session_state.selected_date = selected_date_input
        st.session_state.page_num_cal = 0
        st.rerun()

    total_items = get_devedores_para_dia_count(st.session_state.db_engine,
                                               st.session_state.selected_date)

    if total_items == 0:
        st.info(
            f"Nenhuma cobrança agendada para {st.session_state.selected_date.strftime('%d/%m/%Y')}."
        )
    else:
        total_pages = math.ceil(total_items / PAGE_SIZE_CAL)
        st.session_state.page_num_cal = max(
            0, min(st.session_state.page_num_cal, total_pages - 1))

        @st.cache_data(show_spinner="Carregando agendamentos...", ttl=60)
        def cached_get_devedores_dia(s_date, page, page_size):
            df = get_devedores_para_dia_paginated(st.session_state.db_engine,
                                                  s_date, page, page_size)
            return process_dataframe(df)

        df_pagina_cal = cached_get_devedores_dia(
            st.session_state.selected_date, st.session_state.page_num_cal,
            PAGE_SIZE_CAL)

        st.markdown(
            f"Exibindo **{len(df_pagina_cal)}** de **{total_items}** cobrança(s) para **{st.session_state.selected_date.strftime('%d/%m/%Y')}**."
        )

        col_pag_1, col_pag_2, col_pag_3 = st.columns([1, 2, 1])
        if col_pag_1.button("⬅️ Anterior",
                            key="cal_prev",
                            use_container_width=True,
                            disabled=(st.session_state.page_num_cal == 0)):
            st.session_state.page_num_cal -= 1
            st.rerun()
        col_pag_2.write(
            f"<div style='text-align: center;'>Página {st.session_state.page_num_cal + 1} de {total_pages}</div>",
            unsafe_allow_html=True)
        if col_pag_3.button("Próxima ➡️",
                            key="cal_next",
                            use_container_width=True,
                            disabled=(st.session_state.page_num_cal
                                      >= total_pages - 1)):
            st.session_state.page_num_cal += 1
            st.rerun()

        st.markdown("---")
        for _, row in df_pagina_cal.iterrows():
            exibir_devedor_card(row, from_calendar=True)


def main():
    st.title("📈 Sistema de Gestão de Cobranças")
    tab1, tab2 = st.tabs(["Ações de Cobrança", "Calendário e Agendamentos"])

    with tab1:
        exibir_acoes_cobranca_tab()

    with tab2:
        exibir_calendario_cobrancas_tab()


if __name__ == "__main__":
    main()
