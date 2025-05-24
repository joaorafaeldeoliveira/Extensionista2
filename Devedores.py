# Devedores.py
import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, date

# --- CONFIGURAÇÃO DA PÁGINA (DEVE SER A PRIMEIRA CHAMADA STREAMLIT NO SCRIPT) ---
# Esta chamada configura a página do Streamlit.
# Page_title: Título que aparece na aba do navegador.
# Page_icon: Ícone que aparece na aba do navegador.
# Layout: Define a largura da página ('wide' usa mais espaço, 'centered' é mais estreito).
# initial_sidebar_state: Define se a barra lateral está expandida ou recolhida inicialmente.
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
    export_devedores_to_excel
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

# Flag para indicar se o DataFrame principal precisa ser recarregado do banco de dados.
# Isso é útil após operações de CRUD (adicionar, remover, importar, pagar).
if 'should_reload_df' not in st.session_state:
    st.session_state.should_reload_df = True

# --- Funções de Renderização da Interface do Usuário ---

# Função para renderizar o conteúdo da barra lateral (filtros e opções de importação/exportação).
def sidebar_content():
    filters = {} # Dicionário para armazenar os valores dos filtros.
    with st.sidebar: # Conteúdo dentro da barra lateral.
        st.header("📂 Gerenciar Dados")
        st.write("Aqui você pode importar novos devedores ou exportar os dados existentes.")

        st.subheader("⬆️ Importar de Excel")
        uploaded_file = st.file_uploader(
            "Selecione o arquivo Excel para importar (adicionar novos devedores)",
            type=["xlsx", "xls"], # Tipos de arquivo permitidos.
            key="file_uploader" # Chave única para o widget.
        )

        if uploaded_file is not None:
            st.info("Processando importação...")
            # Chama a função de serviço para importar os dados.
            success, message = import_excel_to_db(st.session_state.db_engine, uploaded_file)
            if success:
                st.success(message)
                st.session_state.should_reload_df = True # Marca para recarregar o DF.
                st.rerun() # Reinicia o script para refletir as mudanças.
            else:
                st.error(message)

        st.subheader("⬇️ Exportar Dados")
        # Permite exportar todos os dados se o DataFrame principal não estiver vazio.
        if st.session_state.df is not None and not st.session_state.df.empty:
            excel_data, export_message = export_devedores_to_excel(st.session_state.df)
            if excel_data:
                st.download_button(
                    label="Baixar Todos os Dados (Excel)",
                    data=excel_data,
                    file_name="devedores.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_excel_full_db"
                )
            else:
                st.info(export_message)
        else:
            st.info("Nenhum dado no banco de dados para exportar ainda.")

        # --- Filtros Avançados ---
        st.header("🔍 Filtros Avançados")

        # Define os valores min/max padrão para os filtros de valor e atraso.
        # Se o DF estiver vazio, usa valores fixos. Caso contrário, usa os min/max dos dados existentes.
        if st.session_state.df is None or st.session_state.df.empty:
            filters['original_valor_min'] = 0.0
            filters['original_valor_max'] = 10000.0
            filters['original_dias_min'] = 0
            filters['original_dias_max'] = 365
        else:
            valortotal_col = st.session_state.df['valortotal'].dropna()
            atraso_col = st.session_state.df['atraso'].dropna()

            filters['original_valor_min'] = float(valortotal_col.min()) if not valortotal_col.empty else 0.0
            filters['original_valor_max'] = float(valortotal_col.max()) if not valortotal_col.empty else 10000.0
            filters['original_dias_min'] = int(atraso_col.min()) if not atraso_col.empty else 0
            filters['original_dias_max'] = int(atraso_col.max()) if not atraso_col.empty else 365

        # Filtro por faixa de valores devidos.
        st.markdown("**Faixa de Valores Devidos (R$):**")
        valor_min = st.number_input(
            "Valor Mínimo (R$)", min_value=0.0, value=filters['original_valor_min'],
            step=1.0, format="%.2f", key="valor_min_input_filter"
        )
        valor_max = st.number_input(
            "Valor Máximo (R$)", min_value=valor_min, value=filters['original_valor_max'],
            step=1.0, format="%.2f", key="valor_max_input_filter"
        )
        filters['valor_range'] = (valor_min, valor_max)

        # Filtro por categorias de valor (multiselect).
        valor_options = ["Todos", "Pequenos (até R$ 500)", "Médios (R$ 500 - R$ 2.000)", "Grandes (acima de R$ 2.000)"]
        filters['valor_categorias_selecionadas'] = st.multiselect(
            "Categorias por Valor", options=valor_options,
            default=st.session_state.valor_categorias_selecionadas_state, key="valor_categoria_multiselect_filter"
        )
        st.session_state.valor_categorias_selecionadas_state = filters['valor_categorias_selecionadas']

        st.markdown("---") # Separador visual.

        # Filtro por faixa de dias em atraso.
        st.markdown("**Dias em Atraso (faixa personalizada):**")
        dias_min = st.number_input(
            "Mínimo de Dias", min_value=0, value=filters['original_dias_min'],
            step=1, key="dias_min_input_filter"
        )
        dias_max = st.number_input(
            "Máximo de Dias", min_value=dias_min, value=filters['original_dias_max'],
            step=1, key="dias_max_input_filter"
        )
        filters['dias_range'] = (dias_min, dias_max)

        # Filtro por status de atraso (categorias multiselect).
        atraso_options = ["Todos", "Iniciando (1-30 dias)", "Moderado (31-90 dias)", "Atrasado (91-180 dias)", "Crítico (acima de 180 dias)"]
        filters['status_atraso_selecionados'] = st.multiselect(
            "Status do Atraso", options=atraso_options,
            default=st.session_state.status_atraso_selecionadas_state, key="status_atraso_multiselect_filter"
        )
        st.session_state.status_atraso_selecionadas_state = filters['status_atraso_selecionados']

        st.markdown("---")

        # Filtro de busca por nome (texto).
        filters['nome_search'] = st.text_input(
            "Buscar por nome",
            placeholder="Digite parte do nome para filtrar...",
            help="Filtre os devedores que contém este texto no nome",
            key="nome_search_input_filter"
        )

    return filters # Retorna o dicionário de filtros aplicados.

# Função para aplicar os filtros selecionados ao DataFrame.
def apply_filters(df, filters):
    if df is None or df.empty:
        return pd.DataFrame()

    filtered = df.copy()

    # Garantir que as colunas existem e tratar nulos
    if 'valortotal' not in filtered.columns:
        filtered['valortotal'] = 0.0
    else:
        filtered['valortotal'] = pd.to_numeric(filtered['valortotal'], errors='coerce').fillna(0)
    
    if 'atraso' not in filtered.columns:
        filtered['atraso'] = 0
    else:
        filtered['atraso'] = pd.to_numeric(filtered['atraso'], errors='coerce').fillna(0)
    
    if 'nome' not in filtered.columns:
        filtered['nome'] = ''
    else:
        filtered['nome'] = filtered['nome'].astype(str).fillna('')

    # Mapeamentos para as categorias de valor e atraso.
    valor_categorias_map = {
        "Pequenos (até R$ 500)": (None, 500),
        "Médios (R$ 500 - R$ 2.000)": (500, 2000),
        "Grandes (acima de R$ 2.000)": (2000, None)
    }

    atraso_status_map = {
        "Iniciando (1-30 dias)": (None, 30),
        "Moderado (31-90 dias)": (30, 90),
        "Atrasado (91-180 dias)": (90, 180),
        "Crítico (acima de 180 dias)": (180, None)
    }

    # Aplica o filtro por faixa de valor.
    if filters['valor_range'][0] != filters['original_valor_min'] or \
       filters['valor_range'][1] != filters['original_valor_max']:
        filtered = filtered[
            (filtered['valortotal'] >= filters['valor_range'][0]) &
            (filtered['valortotal'] <= filters['valor_range'][1])
        ]

    # Aplica o filtro por faixa de dias em atraso.
    if filters['dias_range'][0] != filters['original_dias_min'] or \
       filters['dias_range'][1] != filters['original_dias_max']:
        filtered = filtered[
            (filtered['atraso'] >= filters['dias_range'][0]) &
            (filtered['atraso'] <= filters['dias_range'][1])
        ]

    # Aplica o filtro por categorias de valor.
    if filters['valor_categorias_selecionadas'] and "Todos" not in filters['valor_categorias_selecionadas']:
        combined_valor_filter = pd.Series([False] * len(filtered), index=filtered.index)
        for categoria in filters['valor_categorias_selecionadas']:
            min_val, max_val = valor_categorias_map.get(categoria, (None, None))
            if min_val is not None and max_val is not None:
                combined_valor_filter |= ((filtered['valortotal'] > min_val) & (filtered['valortotal'] <= max_val))
            elif min_val is not None:
                combined_valor_filter |= (filtered['valortotal'] > min_val)
            elif max_val is not None:
                combined_valor_filter |= (filtered['valortotal'] <= max_val)
        filtered = filtered[combined_valor_filter]

    # Aplica o filtro por status de atraso.
    if filters['status_atraso_selecionados'] and "Todos" not in filters['status_atraso_selecionados']:
        combined_atraso_filter = pd.Series([False] * len(filtered), index=filtered.index)
        for status in filters['status_atraso_selecionados']:
            min_atraso, max_atraso = atraso_status_map.get(status, (None, None))
            if min_atraso is not None and max_atraso is not None:
                combined_atraso_filter |= ((filtered['atraso'] > min_atraso) & (filtered['atraso'] <= max_atraso))
            elif min_atraso is not None:
                combined_atraso_filter |= (filtered['atraso'] > min_atraso)
            elif max_atraso is not None:
                combined_atraso_filter |= (filtered['atraso'] <= max_atraso)
        filtered = filtered[combined_atraso_filter]

    # Aplica o filtro de busca por nome.
    if filters['nome_search']:
        if 'nome' in filtered.columns and pd.api.types.is_string_dtype(filtered['nome']):
            filtered = filtered[
                filtered['nome'].str.contains(
                    filters['nome_search'],
                    case=False, # Ignora maiúsculas/minúsculas.
                    na=False # Trata valores NaN como False.
                )
            ]
        else:
            st.warning("Coluna 'nome' não encontrada ou não é do tipo texto para o filtro de busca.")

    return filtered # Retorna o DataFrame com os filtros aplicados.

# Função para renderizar os controles de dados (limpar filtros, exportar tabela filtrada).
def render_data_controls():

    col1, col2 = st.columns([1, 2]) # Duas colunas para os botões.

    with col1:
        # Botão para limpar todos os filtros.
        if st.button("🧹 Limpar Filtros", key="clear_filters_btn"):
            st.session_state.page_number = 1 # Volta para a primeira página.
            st.session_state.valor_categorias_selecionadas_state = ["Todos"] # Reseta filtros de categoria.
            st.session_state.status_atraso_selecionadas_state = ["Todos"] # Reseta filtros de status.
            st.session_state.should_reload_df = True 
            st.rerun() # Reinicia o script.

    with col2:

        if st.button("📤 Exportar Tabela Filtrada para Excel", key="export_filtered_excel_btn"):
            if st.session_state.filtered_df is not None and not st.session_state.filtered_df.empty:

                excel_data, export_message = export_devedores_to_excel(st.session_state.filtered_df)
                if excel_data:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"devedores_filtrados_{timestamp}.xlsx"
                    st.download_button(
                        label="⬇️ Baixar Arquivo Filtrado",
                        data=excel_data,
                        file_name=filename,
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        key="download_filtered_excel_btn"
                    )
                else:
                    st.warning(export_message)
            else:
                st.warning("Nenhum dado disponível para exportar")

def show_lista_devedores_tab(filters):

    st.title("📋 Lista de Devedores")

    with st.expander("➕ Adicionar Novo Devedor", expanded=False):
        with st.form("novo_devedor_form"): # Formulário Streamlit para agrupamento de widgets.
            pessoa_id = st.text_input("ID Pessoa (Opcional - do seu sistema original, se houver)", max_chars=50, key="new_devedor_pessoa_id_form")
            nome = st.text_input("Nome Completo*", max_chars=100, key="new_devedor_nome_form")
            valor = st.number_input("Valor Devido (R$)*", min_value=0.01, format="%.2f", key="new_devedor_valor_form")
            atraso = st.number_input("Dias em Atraso*", min_value=0, value=0, step=1, key="new_devedor_atraso_form")
            telefone = st.text_input("Telefone (Opcional)", max_chars=20, key="new_devedor_telefone_form")

            # Botão de submit do formulário. O `key` é fundamental para evitar erros com múltiplas instâncias.
            if st.form_submit_button("Adicionar Devedor"):
                if not nome or valor <= 0:
                    st.error("Por favor, preencha o Nome Completo e o Valor Devido.")  # Corrigido "preença" para "preencha"
                else:
                    # Chama a função de serviço para adicionar o devedor ao DB.
                    success, message = add_devedor_to_db(st.session_state.db_engine, nome, valor, atraso, telefone, pessoa_id)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                    st.session_state.should_reload_df = True # Marca para recarregar o DF.
                    st.rerun() # Reinicia o script.

    # Carrega dados do DB na primeira execução da sessão ou se a flag `should_reload_df` for True.
    if st.session_state.should_reload_df:
        st.session_state.df = load_devedores_from_db(st.session_state.db_engine)
        if st.session_state.df is not None and not st.session_state.df.empty:
            # Ordenar por dias em atraso (maior primeiro) e depois por valor (maior primeiro)
            st.session_state.df = st.session_state.df.sort_values(
                by=['atraso', 'valortotal'], 
                ascending=[False, False]
            )
        st.session_state.filtered_df = st.session_state.df.copy() if st.session_state.df is not None else pd.DataFrame()
        st.session_state.should_reload_df = False

    else:
        pd.DataFrame()
        st.session_state.should_reload_df = False

    # Mensagem se o banco de dados estiver vazio.
    if st.session_state.df is not None and st.session_state.df.empty:
        st.info("Nenhum devedor encontrado no banco de dados. Adicione um novo ou importe de um Excel.")
        render_data_controls()
        return

    # Aplica os filtros ao DataFrame.
    st.session_state.filtered_df = apply_filters(st.session_state.df, filters)

    # Informações sobre o total de registros.
    total_registros_original = len(st.session_state.df)
    total_registros_filtrados = len(st.session_state.filtered_df)
    st.info(f"📊 **Total de registros:** {total_registros_filtrados} "
              f"de {total_registros_original} (filtrados)")

    st.subheader("Registros Filtrados")

    # Controles de paginação (itens por página).
    st.session_state.items_per_page = st.selectbox(
        "Itens por página:",
        options=[10, 25, 50, 100, "Todos"],
        index=[10, 25, 50, 100, "Todos"].index(st.session_state.items_per_page),
        key="items_per_page_select_main"
    )

    display_df = pd.DataFrame() # DataFrame que será de fato exibido (após paginação).

    # Lógica de paginação.
    if st.session_state.items_per_page != "Todos" and total_registros_filtrados > 0:
        items_per_page = int(st.session_state.items_per_page)
        total_pages = max(1, int(np.ceil(total_registros_filtrados / items_per_page)))

        pag_col1, pag_col2, pag_col3 = st.columns([1, 1, 4]) # Colunas para botões de navegação.

        with pag_col1:
            if st.button("⏪ Anterior",
                         disabled=(st.session_state.page_number == 1),
                         help="Página anterior",
                         key="prev_page_main"):
                st.session_state.page_number = max(1, st.session_state.page_number - 1)
                st.rerun()

        with pag_col2:
            if st.button("Próxima ⏩",
                         disabled=(st.session_state.page_number >= total_pages),
                         help="Próxima página",
                         key="next_page_main"):
                st.session_state.page_number = min(total_pages, st.session_state.page_number + 1)
                st.rerun()

        with pag_col3:
            start_item = (st.session_state.page_number - 1) * items_per_page + 1
            end_item = min(st.session_state.page_number * items_per_page, total_registros_filtrados)
            if total_registros_filtrados > 0:
                st.markdown(f"**Página {st.session_state.page_number} de {total_pages}** "
                             f"• Itens {start_item}-{end_item} de {total_registros_filtrados}")
            else:
                st.markdown("**Nenhum item para exibir**")

        start_idx = (st.session_state.page_number - 1) * items_per_page
        end_idx = start_idx + items_per_page
        display_df = st.session_state.filtered_df.iloc[start_idx:end_idx] # Seleciona a fatia da página.
    else:
        display_df = st.session_state.filtered_df # Se "Todos" ou poucos itens, mostra tudo.
        if not display_df.empty:
            st.markdown(f"**Mostrando todos os {len(display_df)} itens**")

    # Exibição da tabela principal de devedores.
    if not display_df.empty:
        # Colunas a serem exibidas na tabela principal (sem as de cobrança, que serão para Cobrancas.py).
        columns_to_display = ['pessoa', 'nome', 'valortotal', 'atraso', 'status', 'telefone', 'data_pagamento']
        # Garante que apenas colunas existentes sejam exibidas.
        columns_to_display = [col for col in columns_to_display if col in display_df.columns]

        st.dataframe(
            display_df[columns_to_display],
            height=600,
            use_container_width=True, # Usa a largura total disponível.
            column_config={ # Configurações visuais para colunas específicas.
                "pessoa": "ID Pessoa",
                "nome": "Nome",
                "valortotal": st.column_config.NumberColumn(
                    "Valor Total",
                    format="R$ %.2f"
                ),
                "atraso": st.column_config.NumberColumn(
                    "Dias em Atraso",
                    format="%d dias"
                ),
                "telefone": "Telefone",
                "status": "Status Atual",
                "data_pagamento": st.column_config.DateColumn(
                    "Data Pagamento",
                    format="DD/MM/YYYY"
                )
            },
            hide_index=True # Oculta o índice padrão do Pandas.
        )

        # Seção de Ações por Devedor (cards individuais).
        st.markdown("---")
        st.subheader("Ações por Devedor")
        for idx, row in display_df.iterrows():
            if 'id' not in row or pd.isna(row['id']):
                st.warning(f"Erro: Devedor '{row['nome']}' não possui um ID válido para ações. Pule este registro.")
                continue

            with st.container(border=True): # Cada devedor é exibido em um card com borda.
                cols = st.columns([4, 1]) # Duas colunas para nome/detalhes e botões de ação.

                with cols[0]:
                    st.markdown(f"### {row['nome']}")
                    st.caption(f"ID Pessoa: {row.get('pessoa', 'N/A') if pd.notna(row.get('pessoa')) else 'N/A'} | 📞 {row.get('telefone', 'N/A') if pd.notna(row.get('telefone')) else 'N/A'} | Status: **{row['status']}**")
                    st.write(f"**Valor:** R$ {row['valortotal']:,.2f} | **Atraso:** {row['atraso']} dias")

                    # Formata a data de pagamento para exibição.
                    data_pagamento_str = row['data_pagamento'].strftime('%d/%m/%Y') if pd.notna(row['data_pagamento']) else 'Não pago'
                    st.markdown(f"**Data Pagamento:** {data_pagamento_str}")

                with cols[1]:
                    # Botão para marcar como pago.
                    if st.button("✅ Marcar como Pago", key=f"pago_btn_{row['id']}_main",
                                 disabled=(row['status'] == StatusDevedor.PAGO.value), # Desabilita se já estiver pago.
                                 use_container_width=True):
                        success, message = marcar_como_pago_in_db(st.session_state.db_engine, row['id'])
                        if success:
                            st.success(message)
                        else:
                            st.error(message)
                        st.session_state.should_reload_df = True # Marca para recarregar o DF.
                        st.rerun()

                    # Botão para remover o devedor.
                    if st.button("❌ Remover", key=f"remover_btn_{row['id']}_main", use_container_width=True):
                        success, message = remover_devedor_from_db(st.session_state.db_engine, row['id'])
                        if success:
                            st.success(message)
                        else:
                            st.error(message)
                        st.session_state.should_reload_df = True # Marca para recarregar o DF.
                        st.rerun()
    else:
        st.warning("Nenhum registro encontrado com os filtros aplicados.")

    render_data_controls() # Renderiza os controles de dados após a tabela.

# --- Ponto de Entrada Principal do Script ---
# Esta parte é executada quando o script é iniciado.
if __name__ == "__main__":
    # Carrega e exibe o conteúdo da barra lateral, obtendo os filtros.
    filters_from_sidebar = sidebar_content()
    # Exibe a tab da lista de devedores, aplicando os filtros.
    show_lista_devedores_tab(filters_from_sidebar)