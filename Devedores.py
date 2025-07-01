# Devedores.py
import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, date

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Sistema de Devedores",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

from database import init_db, get_session, Devedor, StatusDevedor
from devedores_service import (
    load_devedores_from_db,
    add_devedor_to_db,
    remover_devedor_from_db,
    import_excel_to_db,
    export_devedores_to_excel,
    update_devedor_in_db
)

# --- CACHE DE CARREGAMENTO ---
@st.cache_data(show_spinner=False)
def cached_load_devedores(_engine):
    return load_devedores_from_db(_engine)

# --- ESTADO INICIAL ---
def initialize_session_state():
    defaults = {
        'df': None, 'filtered_df': None, 'edited_df_state': None,
        'page_number': 1, 'items_per_page': 25, 'search_term_state': "",
        'should_reload_df': True, 'confirming_delete': False,
        'ids_to_delete': [],
        'valor_categorias_selecionadas_state': ["Todos"],
        'status_atraso_selecionadas_state': ["Todos"]
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if 'db_engine' not in st.session_state:
        st.session_state.db_engine = init_db()

initialize_session_state()

def validate_excel_columns(df: pd.DataFrame, required_cols: list) -> tuple:
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        return False, f"Colunas ausentes no Excel: {', '.join(missing)}"
    return True, ""

def sidebar_content():
    filters = {} 
    with st.sidebar:
        st.header("📂 Gerenciar Dados")

        st.subheader("⬆️ Importar de Excel")
        uploaded_file = st.file_uploader("Selecione o arquivo Excel", type=["xlsx", "xls"])
        if uploaded_file:
            st.info("Processando importacao...")
            success, message = import_excel_to_db(st.session_state.db_engine, uploaded_file)
            if success:
                st.success(message)
                st.session_state.should_reload_df = True
                st.rerun()
            else:
                st.error(message)

        st.subheader("🔽️ Exportar Dados")
        if st.session_state.df is not None and not st.session_state.df.empty:
            excel_data, export_message = export_devedores_to_excel(st.session_state.df)
            if excel_data:
                st.download_button(
                    label="Baixar Todos os Dados",
                    data=excel_data,
                    file_name="devedores_completo.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.info("Nenhum dado para exportar.")

        st.header("🔍 Filtros Avançados")

        filters['search_term'] = st.text_input(
            "Buscar por Nome ou ID", value=st.session_state.search_term_state,
            placeholder="Digite o nome ou ID...", key="search_term_input"
        )
        st.session_state.search_term_state = filters['search_term']

        if st.session_state.df is None or st.session_state.df.empty:
            filters['original_valor_min'], filters['original_valor_max'] = 0.0, 10000.0
            filters['original_dias_min'], filters['original_dias_max'] = 0, 365
        else:
            valortotal_col = st.session_state.df['valortotal'].dropna()
            atraso_col = st.session_state.df['atraso'].dropna()
            filters['original_valor_min'] = float(valortotal_col.min())
            filters['original_valor_max'] = float(valortotal_col.max())
            filters['original_dias_min'] = int(atraso_col.min())
            filters['original_dias_max'] = int(atraso_col.max())

        with st.expander("Filtros por Valor e Atraso"):
            valor_min, valor_max = st.slider(
                "Valor", min_value=filters['original_valor_min'],
                max_value=filters['original_valor_max'],
                value=(filters['original_valor_min'], filters['original_valor_max'])
            )
            filters['valor_range'] = (valor_min, valor_max)

            dias_min, dias_max = st.slider(
                "Dias", min_value=filters['original_dias_min'],
                max_value=filters['original_dias_max'],
                value=(filters['original_dias_min'], filters['original_dias_max'])
            )
            filters['dias_range'] = (dias_min, dias_max)

    return filters

def apply_filters(df, filters):
    if df is None or df.empty:
        return pd.DataFrame()

    filtered = df.copy()
    filtered['valortotal'] = pd.to_numeric(filtered['valortotal'], errors='coerce').fillna(0)
    filtered['atraso'] = pd.to_numeric(filtered['atraso'], errors='coerce').fillna(0)
    filtered['nome'] = filtered['nome'].astype(str).fillna('')
    filtered['pessoa'] = filtered['pessoa'].astype(str).fillna('')

    if filters['search_term']:
        term = filters['search_term'].strip()
        name_match = filtered['nome'].str.contains(term, case=False, na=False)
        id_match = filtered['pessoa'].str.contains(term, case=False, na=False)
        filtered = filtered[name_match | id_match]

    if filters['valor_range'] != (filters['original_valor_min'], filters['original_valor_max']):
        filtered = filtered[(filtered['valortotal'] >= filters['valor_range'][0]) &
                            (filtered['valortotal'] <= filters['valor_range'][1])]

    if filters['dias_range'] != (filters['original_dias_min'], filters['original_dias_max']):
        filtered = filtered[(filtered['atraso'] >= filters['dias_range'][0]) &
                            (filtered['atraso'] <= filters['dias_range'][1])]

    return filtered

def render_data_controls():
    col1, col2 = st.columns([0.3, 1])
    with col1:
        if st.button("🧹 Limpar Filtros", key="clear_filters_btn", use_container_width=True):
            st.session_state.page_number = 1
            st.session_state.search_term_state = ""
            st.session_state.should_reload_df = True
            # Limpa o estado da edição para evitar atualizações indesejadas
            st.session_state.edited_df_state = None 
            st.rerun()

    with col2:
         # Botão para exportar a tabela filtrada
        if not st.session_state.filtered_df.empty:
            excel_data, msg = export_devedores_to_excel(st.session_state.filtered_df)
            st.download_button(
                label="📤 Exportar Tabela Filtrada para Excel",
                data=excel_data,
                file_name=f"devedores_filtrados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                key="export_filtered_excel_btn",
                use_container_width=True
            )

# ### NOVO ### - Função para processar as edições feitas na tabela
def process_table_edits(edited_df, original_df):
    diff_mask = (edited_df != original_df) & ~(edited_df.isna() & original_df.isna())
    rows_with_changes = diff_mask.any(axis=1)
    changed_rows = edited_df[rows_with_changes]

    if changed_rows.empty:
        return

    updates_processed = 0
    for idx in changed_rows.index:
        devedor_id = original_df.loc[idx, 'id']
        changes = {col: edited_df.loc[idx, col] for col in edited_df.columns if edited_df.loc[idx, col] != original_df.loc[idx, col]}

        if 'status' in changes and changes['status'] == StatusDevedor.PAGO.value:
            changes['data_pagamento'] = datetime.now().date()

        success, message = update_devedor_in_db(st.session_state.db_engine, devedor_id, changes)
        if success:
            updates_processed += 1
        else:
            st.error(f"Erro ao atualizar ID {devedor_id}: {message}")

    if updates_processed:
        st.success(f"{updates_processed} registro(s) atualizado(s) com sucesso!")
        st.session_state.should_reload_df = True
        st.rerun()



def show_lista_devedores_tab(filters):

    st.title("📋 Lista de Devedores")


    with st.expander("➕ Adicionar Novo Devedor"):
        with st.form("novo_devedor_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome Completo*", max_chars=100)
            pessoa_id = c2.text_input("ID Pessoa (Opcional)", max_chars=50)
            
            c3, c4, c5 = st.columns(3)
            valor = c3.number_input("Valor Devido (R$)*", min_value=0.01, format="%.2f")
            atraso = c4.number_input("Dias em Atraso*", min_value=0, step=1)
            telefone = c5.text_input("Telefone (Opcional)", max_chars=20)

            if st.form_submit_button("Adicionar Devedor", type="primary"):
                if not nome or valor <= 0:
                    st.error("Por favor, preencha o Nome e o Valor Devido.")
                else:
                    success, message = add_devedor_to_db(st.session_state.db_engine, nome, valor, atraso, telefone, pessoa_id)
                    if success:
                        st.success(message)
                        st.session_state.should_reload_df = True
                        st.rerun()
                    else:
                        st.error(message)


    if st.session_state.should_reload_df:
        st.session_state.df = cached_load_devedores(st.session_state.db_engine)
        if st.session_state.df is not None:
            st.session_state.df = st.session_state.df.sort_values(by=['atraso', 'valortotal'], ascending=[False, False])
        st.session_state.should_reload_df = False
        st.session_state.page_number = 1

    if st.session_state.df is None or st.session_state.df.empty:
        st.info("ℹ️ Nenhum devedor encontrado no banco de dados. Adicione um novo ou importe de um Excel.")
        return

    # Aplica os filtros ao DataFrame.
    st.session_state.filtered_df = apply_filters(st.session_state.df, filters)
    st.markdown("---")
    
    if st.session_state.confirming_delete:
        st.error(f"### Deseja realmente excluir {len(st.session_state.ids_to_delete)} registro(s)?")
        st.warning("Esta ação não pode ser desfeita.")
        
        col1, col2 = st.columns(2)
        if col1.button("Sim, Excluir Agora", type="primary", use_container_width=True):
            sucessos, falhas = 0, 0
            for devedor_id in st.session_state.ids_to_delete:
                success, message = remover_devedor_from_db(st.session_state.db_engine, devedor_id)
                if success:
                    sucessos += 1
                else:
                    falhas += 1
                    st.error(f"Erro ao remover ID {devedor_id}: {message}")
            
            if sucessos > 0:
                st.success(f"{sucessos} registro(s) removido(s) com sucesso!")
            
            # Limpa e recarrega
            st.session_state.confirming_delete = False
            st.session_state.ids_to_delete = []
            st.session_state.should_reload_df = True
            st.rerun()

        if col2.button("Cancelar", use_container_width=True):
            st.session_state.confirming_delete = False
            st.session_state.ids_to_delete = []
            st.rerun()
        return # Impede que o resto da página seja desenhado

    total_registros_original = len(st.session_state.df)
    total_registros_filtrados = len(st.session_state.filtered_df)
    st.info(f"📊 **Total de registros:** {total_registros_filtrados} de {total_registros_original} (filtrados)")

    st.subheader("Registros de Devedores")
    render_data_controls() 

    # Lógica de Paginação (sem alterações)
    items_per_page_options = [10, 25, 50, 100]
    if total_registros_filtrados > 100:
        items_per_page_options.append(total_registros_filtrados)
    
    if st.session_state.items_per_page > total_registros_filtrados and total_registros_filtrados > 0:
        st.session_state.items_per_page = min(items_per_page_options, key=lambda x:abs(x-total_registros_filtrados))
    elif total_registros_filtrados == 0:
        st.session_state.items_per_page = 10

    page_col1, page_col2 = st.columns([0.7, 0.3])
    with page_col2:
        st.session_state.items_per_page = st.selectbox(
            "Itens por página:", options=items_per_page_options,
            index=items_per_page_options.index(st.session_state.items_per_page),
            key="items_per_page_select_main"
        )
    
    items_per_page = st.session_state.items_per_page
    total_pages = max(1, int(np.ceil(total_registros_filtrados / items_per_page)))
    st.session_state.page_number = min(st.session_state.page_number, total_pages)

    start_idx = (st.session_state.page_number - 1) * items_per_page
    end_idx = start_idx + items_per_page
    display_df = st.session_state.filtered_df.iloc[start_idx:end_idx].copy()

    with page_col1:
        nav_cols = st.columns([1, 1, 3])
        if nav_cols[0].button("⏪ Anterior", disabled=(st.session_state.page_number == 1), key="prev_page_main", use_container_width=True):
            st.session_state.page_number -= 1
            st.rerun()
        if nav_cols[1].button("Próxima ⏩", disabled=(st.session_state.page_number >= total_pages), key="next_page_main", use_container_width=True):
            st.session_state.page_number += 1
            st.rerun()
        
        start_item = start_idx + 1 if total_registros_filtrados > 0 else 0
        end_item = min(end_idx, total_registros_filtrados)
        nav_cols[2].markdown(f"**Página {st.session_state.page_number} de {total_pages}** (Itens {start_item}-{end_item})")
    
    
    if not display_df.empty:
        display_df.insert(0, 'Excluir', False)

        status_options = [s.value for s in StatusDevedor]
        display_df['status'] = pd.Categorical(display_df['status'], categories=status_options, ordered=False)

        column_config = {
            "Excluir": st.column_config.CheckboxColumn("Excluir?", default=False, help="Marque para remover o devedor."),
            "pessoa": st.column_config.TextColumn("ID Pessoa", disabled=True),
            "nome": st.column_config.TextColumn("Nome", disabled=True),
            "valortotal": st.column_config.NumberColumn("Valor Total", format="R$ %.2f", disabled=True),
            "atraso": st.column_config.NumberColumn("Dias Atraso", format="%d dias", disabled=True),
            "status": st.column_config.SelectboxColumn("Status Atual", options=status_options, required=True),
            "telefone": st.column_config.TextColumn("Telefone", disabled=True),
            "data_pagamento": st.column_config.DateColumn("Data Pagamento", format="DD/MM/YYYY", disabled=True)
        }
        
        hidden_columns = ['id'] if 'id' in display_df.columns else []

        # Desabilita a edição em todas as colunas, exceto 'status' e a nova 'Excluir'
        disabled_columns = display_df.columns.drop(['status', 'Excluir'])

        edited_df = st.data_editor(
            display_df, height=600, use_container_width=True,
            column_config=column_config,
            hide_index=True,
            disabled=display_df.columns.drop(['status', 'Excluir']),
            key="devedores_editor"
        )
        

        action_col1, action_col2 = st.columns(2)
        
        if action_col1.button("💾 Salvar Alterações de Status", use_container_width=True):
            if 'page_df_before_edit' not in st.session_state or not st.session_state.page_df_before_edit.equals(display_df):
                st.session_state.page_df_before_edit = display_df.copy()
            process_table_edits(edited_df, st.session_state.page_df_before_edit)
        
        # Botão para INICIAR o processo de exclusão
        linhas_para_excluir = edited_df[edited_df['Excluir'] == True]
        if not linhas_para_excluir.empty:
            if action_col2.button(f"🗑️ Excluir {len(linhas_para_excluir)} Registro(s)", type="primary", use_container_width=True):
                st.session_state.confirming_delete = True
                st.session_state.ids_to_delete = linhas_para_excluir['id'].tolist()
                st.rerun()
    else:
        st.warning("Nenhum registro encontrado com os filtros aplicados.")

if __name__ == "__main__":
    active_filters = sidebar_content()
    show_lista_devedores_tab(active_filters)