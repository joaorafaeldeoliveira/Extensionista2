# Devedores.py
import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, date

# --- CONFIGURAÇÃO DA PÁGINA (DEVE SER A PRIMEIRA CHAMADA STREAMLIT NO SCRIPT) ---
st.set_page_config(
    page_title="Sistema de Devedores",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Importações de Módulos Personalizados ---
# Importa as funções e classes do seu database.py
from database import init_db, get_session, Devedor, StatusDevedor
# Importa as funções de serviço de devedores_service.py
from devedores_service import (
    load_devedores_from_db,
    add_devedor_to_db,
    marcar_como_pago_in_db,
    remover_devedor_from_db,
    import_excel_to_db,
    export_devedores_to_excel,
    update_devedor_in_db  # ### NOVO ### - Função para atualizar um devedor
)

# --- Inicialização da Conexão com o Banco de Dados e Variáveis de Estado ---
# As variáveis de estado (st.session_state) persistem os dados entre as interações do usuário.

# Inicializa o motor do banco de dados uma única vez na sessão.
if 'db_engine' not in st.session_state:
    st.session_state.db_engine = init_db()
    st.success("Banco de dados 'cobrancas.db' inicializado!") # Mensagem de sucesso na primeira inicialização.

# DataFrame principal que guarda todos os devedores carregados do DB.
if 'df' not in st.session_state:
    st.session_state.df = None

# DataFrame filtrado, usado para exibição após a aplicação dos filtros.
if 'filtered_df' not in st.session_state:
    st.session_state.filtered_df = None
    
# ### NOVO ### - Armazena o estado do data_editor para detectar mudanças
if 'edited_df_state' not in st.session_state:
    st.session_state.edited_df_state = None

# Controle de paginação: número da página atual.
if 'page_number' not in st.session_state:
    st.session_state.page_number = 1

# Controle de paginação: quantidade de itens a serem exibidos por página.
if 'items_per_page' not in st.session_state:
    st.session_state.items_per_page = 25

# Estados dos filtros para persistir as seleções do usuário na barra lateral.
if 'valor_categorias_selecionadas_state' not in st.session_state:
    st.session_state.valor_categorias_selecionadas_state = ["Todos"]
if 'status_atraso_selecionados_state' not in st.session_state:
    st.session_state.status_atraso_selecionadas_state = ["Todos"]
if 'search_term_state' not in st.session_state: # ### NOVO ###
    st.session_state.search_term_state = ""


# Flag para indicar se o DataFrame principal precisa ser recarregado do banco de dados.
if 'should_reload_df' not in st.session_state:
    st.session_state.should_reload_df = True

# --- Funções de Renderização da Interface do Usuário ---

# Função para renderizar o conteúdo da barra lateral (filtros e opções de importação/exportação).
def sidebar_content():
    filters = {} # Dicionário para armazenar os valores dos filtros.
    with st.sidebar:
        st.header("📂 Gerenciar Dados")
        st.write("Aqui você pode importar novos devedores ou exportar os dados existentes.")

        st.subheader("⬆️ Importar de Excel")
        uploaded_file = st.file_uploader(
            "Selecione o arquivo Excel para importar",
            type=["xlsx", "xls"],
            key="file_uploader"
        )
        if uploaded_file is not None:
            st.info("Processando importação...")
            success, message = import_excel_to_db(st.session_state.db_engine, uploaded_file)
            if success:
                st.success(message)
                st.session_state.should_reload_df = True
                st.rerun()
            else:
                st.error(message)

        st.subheader("⬇️ Exportar Dados")
        if st.session_state.df is not None and not st.session_state.df.empty:
            excel_data, export_message = export_devedores_to_excel(st.session_state.df)
            if excel_data:
                st.download_button(
                    label="Baixar Todos os Dados (Excel)",
                    data=excel_data,
                    file_name="devedores_completo.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_excel_full_db"
                )
        else:
            st.info("Nenhum dado para exportar.")

        # --- Filtros Avançados ---
        st.header("🔍 Filtros Avançados")

        # ### ALTERADO ### - Filtro de busca unificado por nome ou ID.
        filters['search_term'] = st.text_input(
            "Buscar por Nome ou ID",
            value=st.session_state.search_term_state,
            placeholder="Digite o nome ou ID do devedor...",
            help="Filtra devedores cujo nome ou ID contenha o texto digitado.",
            key="search_term_input"
        )
        st.session_state.search_term_state = filters['search_term']


        # Define os valores min/max padrão para os filtros.
        if st.session_state.df is None or st.session_state.df.empty:
            filters['original_valor_min'], filters['original_valor_max'] = 0.0, 10000.0
            filters['original_dias_min'], filters['original_dias_max'] = 0, 365
        else:
            valortotal_col = st.session_state.df['valortotal'].dropna()
            atraso_col = st.session_state.df['atraso'].dropna()
            filters['original_valor_min'] = float(valortotal_col.min()) if not valortotal_col.empty else 0.0
            filters['original_valor_max'] = float(valortotal_col.max()) if not valortotal_col.empty else 10000.0
            filters['original_dias_min'] = int(atraso_col.min()) if not atraso_col.empty else 0
            filters['original_dias_max'] = int(atraso_col.max()) if not atraso_col.empty else 365

        # Filtros de valor e dias
        with st.expander("Filtros por Valor e Atraso"):
            st.markdown("**Faixa de Valores Devidos (R$):**")
            valor_min, valor_max = st.slider(
                "Valor",
                min_value=filters['original_valor_min'],
                max_value=filters['original_valor_max'],
                value=(filters['original_valor_min'], filters['original_valor_max']),
                key="valor_slider_filter"
            )
            filters['valor_range'] = (valor_min, valor_max)

            st.markdown("**Faixa de Dias em Atraso:**")
            dias_min, dias_max = st.slider(
                "Dias",
                min_value=filters['original_dias_min'],
                max_value=filters['original_dias_max'],
                value=(filters['original_dias_min'], filters['original_dias_max']),
                key="dias_slider_filter"
            )
            filters['dias_range'] = (dias_min, dias_max)

    return filters

# ### ALTERADO ### - Função de filtros aprimorada
def apply_filters(df, filters):
    if df is None or df.empty:
        return pd.DataFrame()

    filtered = df.copy()

    # Garantir tipos de dados corretos para filtragem
    filtered['valortotal'] = pd.to_numeric(filtered['valortotal'], errors='coerce').fillna(0)
    filtered['atraso'] = pd.to_numeric(filtered['atraso'], errors='coerce').fillna(0)
    filtered['nome'] = filtered['nome'].astype(str).fillna('')
    # 'pessoa' é o ID, convertido para string para a busca funcionar com 'contains'
    filtered['pessoa'] = filtered['pessoa'].astype(str).fillna('')

    # ### NOVO ### - Lógica de busca unificada (Nome ou ID)
    if filters['search_term']:
        term = filters['search_term'].strip()
        # Busca case-insensitive no nome OU no ID (pessoa)
        name_match = filtered['nome'].str.contains(term, case=False, na=False)
        id_match = filtered['pessoa'].str.contains(term, case=False, na=False)
        filtered = filtered[name_match | id_match]

    # Aplica o filtro por faixa de valor.
    if filters['valor_range'] != (filters['original_valor_min'], filters['original_valor_max']):
        filtered = filtered[
            (filtered['valortotal'] >= filters['valor_range'][0]) &
            (filtered['valortotal'] <= filters['valor_range'][1])
        ]

    # Aplica o filtro por faixa de dias em atraso.
    if filters['dias_range'] != (filters['original_dias_min'], filters['original_dias_max']):
        filtered = filtered[
            (filtered['atraso'] >= filters['dias_range'][0]) &
            (filtered['atraso'] <= filters['dias_range'][1])
        ]

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
    """Compara o DataFrame editado com o original e atualiza o banco de dados."""
    if edited_df.equals(original_df):
        return # Sem mudanças, não faz nada

    # Encontra as diferenças
    diff = original_df.compare(edited_df)
    
    updates_processed = 0
    for idx in diff.index:
        devedor_id = original_df.loc[idx, 'id'] # Assume que a coluna de ID se chama 'id'
        changes = {}
        
        # Itera sobre as colunas que mudaram para este índice (idx)
        for col in diff.columns.levels[0]:
            old_val = diff.loc[idx, (col, 'self')]
            new_val = diff.loc[idx, (col, 'other')]
            
            # Checa se a mudança é real (compare() pode mostrar NaNs)
            if pd.notna(new_val) and new_val != old_val:
                changes[col] = new_val
        
        if changes:
            # Se o status mudou para 'Pago', atualiza a data de pagamento
            if 'status' in changes and changes['status'] == StatusDevedor.PAGO.value:
                changes['data_pagamento'] = datetime.now().date()

            # Chama a função de serviço para atualizar o DB
            success, message = update_devedor_in_db(st.session_state.db_engine, devedor_id, changes)
            if success:
                updates_processed += 1
            else:
                st.error(f"Erro ao atualizar devedor ID {devedor_id}: {message}")

    if updates_processed > 0:
        st.success(f"{updates_processed} registro(s) atualizado(s) com sucesso!")
        st.session_state.should_reload_df = True # Marca para recarregar os dados
        st.rerun()


def show_lista_devedores_tab(filters):
    st.title("📋 Lista de Devedores")

    # Carrega dados do DB se necessário
    if st.session_state.should_reload_df:
        st.session_state.df = load_devedores_from_db(st.session_state.db_engine)
        if st.session_state.df is not None:
            st.session_state.df = st.session_state.df.sort_values(by=['atraso', 'valortotal'], ascending=[False, False])
        st.session_state.should_reload_df = False
        st.session_state.page_number = 1 # Reseta a página ao recarregar

    if st.session_state.df is None or st.session_state.df.empty:
        st.info("ℹ️ Nenhum devedor encontrado no banco de dados. Adicione um novo ou importe de um Excel.")
        return

    # Aplica os filtros ao DataFrame.
    st.session_state.filtered_df = apply_filters(st.session_state.df, filters)

    total_registros_original = len(st.session_state.df)
    total_registros_filtrados = len(st.session_state.filtered_df)
    st.info(f"📊 **Total de registros:** {total_registros_filtrados} de {total_registros_original} (filtrados)")

    st.subheader("Registros de Devedores")
    render_data_controls() # Adiciona controles de limpar/exportar

    # Paginação
    items_per_page_options = [10, 25, 50, 100]
    if total_registros_filtrados > 100:
        items_per_page_options.append(total_registros_filtrados)
    
    if st.session_state.items_per_page > total_registros_filtrados:
        st.session_state.items_per_page = 25 # Reseta se for maior que o total

    page_col1, page_col2 = st.columns([0.7, 0.3])
    with page_col2:
        st.session_state.items_per_page = st.selectbox(
            "Itens por página:",
            options=items_per_page_options,
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
        # Controles de navegação da página
        nav_cols = st.columns([1, 1, 3])
        if nav_cols[0].button("⏪ Anterior", disabled=(st.session_state.page_number == 1), key="prev_page_main", use_container_width=True):
            st.session_state.page_number -= 1
            st.rerun()
        if nav_cols[1].button("Próxima ⏩", disabled=(st.session_state.page_number >= total_pages), key="next_page_main", use_container_width=True):
            st.session_state.page_number += 1
            st.rerun()
        
        start_item = start_idx + 1
        end_item = min(end_idx, total_registros_filtrados)
        nav_cols[2].markdown(f"**Página {st.session_state.page_number} de {total_pages}** (Itens {start_item}-{end_item})")
    
    # ### ALTERADO ### - Usando st.data_editor para permitir edições
    if not display_df.empty:
        # Garante que a coluna de status seja do tipo Categoria para o Selectbox funcionar bem
        status_options = [s.value for s in StatusDevedor]
        display_df['status'] = pd.Categorical(display_df['status'], categories=status_options, ordered=False)

        # Colunas visíveis e suas configurações
        columns_to_display = {
            "pessoa": st.column_config.TextColumn("ID Pessoa", disabled=True),
            "nome": st.column_config.TextColumn("Nome", disabled=True),
            "valortotal": st.column_config.NumberColumn("Valor Total", format="R$ %.2f", disabled=True),
            "atraso": st.column_config.NumberColumn("Dias Atraso", format="%d dias", disabled=True),
            "status": st.column_config.SelectboxColumn(
                "Status Atual",
                options=status_options,
                required=True,
            ),
            "telefone": st.column_config.TextColumn("Telefone", disabled=True),
            "data_pagamento": st.column_config.DateColumn("Data Pagamento", format="DD/MM/YYYY", disabled=True)
        }
        
        # Precisamos do ID para fazer o update, mas não precisamos exibi-lo se 'pessoa' já for o ID.
        # Se 'id' for diferente de 'pessoa', podemos ocultá-lo.
        hidden_columns = ['id'] if 'id' in display_df.columns else []

        edited_df = st.data_editor(
            display_df,
            height=600,
            use_container_width=True,
            column_config=columns_to_display,
            hide_index=True,
            num_rows="dynamic", # Permite adicionar/remover linhas, mas desabilitamos para focar na edição
            disabled=display_df.columns.drop('status'), # Desabilita edição em todas as colunas exceto 'status'
            key="devedores_editor"
        )
        
        # ### NOVO ### - Compara o estado anterior com o atual para salvar as mudanças
        # Usamos uma cópia do dataframe da página atual para comparação
        if 'page_df_before_edit' not in st.session_state or not st.session_state.page_df_before_edit.equals(display_df):
             st.session_state.page_df_before_edit = display_df.copy()

        if st.button("💾 Salvar Alterações", key="save_changes_btn"):
             process_table_edits(edited_df, st.session_state.page_df_before_edit)

    else:
        st.warning("Nenhum registro encontrado com os filtros aplicados.")


if __name__ == "__main__":
    active_filters = sidebar_content()
    show_lista_devedores_tab(active_filters)