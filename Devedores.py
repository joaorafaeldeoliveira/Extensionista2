import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime


if 'df' not in st.session_state:
    st.session_state.df = None
if 'filtered_df' not in st.session_state:
    st.session_state.filtered_df = None
if 'page_number' not in st.session_state:
    st.session_state.page_number = 1
if 'items_per_page' not in st.session_state:
    st.session_state.items_per_page = 25


if 'valor_categorias_selecionadas_state' not in st.session_state:
    st.session_state.valor_categorias_selecionadas_state = ["Todos"]
if 'status_atraso_selecionados_state' not in st.session_state:
    st.session_state.status_atraso_selecionados_state = ["Todos"]



def load_excel(file):

    try:
        df = pd.read_excel(file, engine='openpyxl')
        return df
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        return None


def sidebar():
    filters = render_filters_sidebar()
    return filters 
def apply_filters(df, filters):
    if df is None or df.empty:
        return pd.DataFrame()

    filtered = df.copy()
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

    if filters['valor_range'][0] != filters['original_valor_min'] or \
       filters['valor_range'][1] != filters['original_valor_max']:
        filtered = filtered[
            (filtered['valortotal'] >= filters['valor_range'][0]) &
            (filtered['valortotal'] <= filters['valor_range'][1])
        ]

    if filters['dias_range'][0] != filters['original_dias_min'] or \
       filters['dias_range'][1] != filters['original_dias_max']:
        filtered = filtered[
            (filtered['atraso'] >= filters['dias_range'][0]) &
            (filtered['atraso'] <= filters['dias_range'][1])
        ]

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


    if filters['nome_search']:
        if 'nome' in filtered.columns and pd.api.types.is_string_dtype(filtered['nome']):
            filtered = filtered[
                filtered['nome'].str.contains(
                    filters['nome_search'],
                    case=False,
                    na=False     
                )
            ]
        else:
            st.warning("Coluna 'nome' não encontrada ou não é do tipo texto para o filtro de busca.")


    return filtered


def render_filters_sidebar():
    filters = {}
    st.sidebar.header("🔍 Filtros Avançados")
    if st.session_state.df is None:
        filters['original_valor_min'] = 0.0
        filters['original_valor_max'] = 10000.0
        filters['original_dias_min'] = 0
        filters['original_dias_max'] = 365
    else:
        filters['original_valor_min'] = float(st.session_state.df['valortotal'].min()) if 'valortotal' in st.session_state.df.columns else 0.0
        filters['original_valor_max'] = float(st.session_state.df['valortotal'].max()) if 'valortotal' in st.session_state.df.columns else 10000.0
        filters['original_dias_min'] = int(st.session_state.df['atraso'].min()) if 'atraso' in st.session_state.df.columns else 0
        filters['original_dias_max'] = int(st.session_state.df['atraso'].max()) if 'atraso' in st.session_state.df.columns else 365


    
    st.sidebar.markdown("**Faixa de Valores Devidos (R$):**")
    valor_min = st.sidebar.number_input(
        "Valor Mínimo (R$)",
        min_value=0.0,
        value=filters['original_valor_min'],
        step=1.0,
        format="%.2f",
        key="valor_min_input"
    )
    valor_max = st.sidebar.number_input(
        "Valor Máximo (R$)",
        min_value=valor_min,
        value=filters['original_valor_max'],
        step=1.0,
        format="%.2f",
        key="valor_max_input"
    )
    filters['valor_range'] = (valor_min, valor_max)

    
    valor_options = ["Todos", "Pequenos (até R$ 500)", "Médios (R$ 500 - R$ 2.000)", "Grandes (acima de R$ 2.000)"]
    filters['valor_categorias_selecionadas'] = st.sidebar.multiselect(
        "Categorias por Valor",
        options=valor_options,
        default=st.session_state.valor_categorias_selecionadas_state,
        key="valor_categoria_multiselect"
    )
    
    st.session_state.valor_categorias_selecionadas_state = filters['valor_categorias_selecionadas']
    st.sidebar.markdown("---") 
    st.sidebar.markdown("**Dias em Atraso (faixa personalizada):**")
    dias_min = st.sidebar.number_input(
        "Mínimo de Dias",
        min_value=0,
        value=filters['original_dias_min'],
        step=1,
        key="dias_min_input"
    )
    dias_max = st.sidebar.number_input(
        "Máximo de Dias",
        min_value=dias_min,
        value=filters['original_dias_max'],
        step=1,
        key="dias_max_input"
    )
    filters['dias_range'] = (dias_min, dias_max)

    atraso_options = ["Todos", "Iniciando (1-30 dias)", "Moderado (31-90 dias)", "Atrasado (91-180 dias)", "Crítico (acima de 180 dias)"]
    filters['status_atraso_selecionados'] = st.sidebar.multiselect(
        "Status do Atraso",
        options=atraso_options,
        default=st.session_state.status_atraso_selecionados_state,
        key="status_atraso_multiselect"
    )
   
    st.session_state.status_atraso_selecionados_state = filters['status_atraso_selecionados']

    st.sidebar.markdown("---")

    filters['nome_search'] = st.sidebar.text_input(
        "Buscar por nome",
        placeholder="Digite parte do nome para filtrar...",
        help="Filtre os devedores que contém este texto no nome",
        key="nome_search_input"
    )

    return filters
def render_data_controls():
    
    col1, col2 = st.columns([1, 2])

    with col1:
        if st.button("🧹 Limpar Filtros"):
            if st.session_state.df is not None:
                st.session_state.filtered_df = st.session_state.df.copy()
                st.session_state.page_number = 1
                st.session_state.valor_categorias_selecionadas_state = ["Todos"]
                st.session_state.status_atraso_selecionados_state = ["Todos"]
                st.rerun()

    with col2:
        if st.button("📤 Exportar para Excel"):
            if st.session_state.filtered_df is not None and not st.session_state.filtered_df.empty:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"devedores_filtrados_{timestamp}.xlsx"
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    st.session_state.filtered_df.to_excel(writer, index=False, sheet_name='Devedores')
                output.seek(0)

                st.download_button(
                    label="⬇️ Baixar Arquivo Filtrado",
                    data=output.getvalue(), 
                    file_name=filename,
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
            else:
                st.warning("Nenhum dado disponível para exportar")

def show_lista_devedores():
    
    st.title("📋 Lista de Devedores")

    if st.session_state.df is None:
        st.info("Por favor, carregue um arquivo Excel na barra lateral para começar.")
        return

    required_columns = ['pessoa', 'nome', 'atraso', 'valortotal']
    if not all(col in st.session_state.df.columns for col in required_columns):
        st.error(
            f"O arquivo Excel carregado não contém todas as colunas necessárias. "
            f"As colunas esperadas são: **{', '.join(required_columns)}**."
        )
        st.write("Colunas encontradas:", list(st.session_state.df.columns))
        return

    filters = sidebar()

    st.session_state.filtered_df = apply_filters(st.session_state.df, filters)
    total_registros_original = len(st.session_state.df)
    total_registros_filtrados = len(st.session_state.filtered_df)
    st.info(f"📊 **Total de registros:** {total_registros_filtrados} "
            f"de {total_registros_original} (filtrados)")

    st.subheader("Registros Filtrados")


    st.session_state.items_per_page = st.selectbox(
        "Itens por página:",
        options=[10, 25, 50, 100, "Todos"],
        index=[10, 25, 50, 100, "Todos"].index(st.session_state.items_per_page),
        key="items_per_page_select"
    )

    display_df = pd.DataFrame()

    if st.session_state.items_per_page != "Todos" and total_registros_filtrados > 0:
        items_per_page = int(st.session_state.items_per_page)
        total_pages = max(1, int(np.ceil(total_registros_filtrados / items_per_page)))

        pag_col1, pag_col2, pag_col3 = st.columns([1, 1, 4])

        with pag_col1:
            if st.button("⏪ Anterior",
                         disabled=(st.session_state.page_number == 1),
                         help="Página anterior",
                         key="prev_page"):
                st.session_state.page_number = max(1, st.session_state.page_number - 1)
                st.rerun()

        with pag_col2:
            if st.button("Próxima ⏩",
                         disabled=(st.session_state.page_number >= total_pages),
                         help="Próxima página",
                         key="next_page"):
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
        display_df = st.session_state.filtered_df.iloc[start_idx:end_idx]
    else:
        display_df = st.session_state.filtered_df
        st.markdown(f"**Mostrando todos os {len(display_df)} itens**")


    if not display_df.empty:
        st.dataframe(
            display_df,
            height=600,
            use_container_width=True,
            column_config={
                "pessoa": "ID Pessoa",
                "nome": "Nome",
                "valortotal": st.column_config.NumberColumn(
                    "Valor Total",
                    format="R$ %.2f"
                ),
                "atraso": st.column_config.NumberColumn(
                    "Dias em Atraso",
                    format="%d dias"
                )
            },
            hide_index=True
        )
    else:
        st.warning("Nenhum registro encontrado com os filtros aplicados.")

    
    render_data_controls()


def main():
  
    st.set_page_config(
        page_title="Sistema de Cobranças",
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    show_lista_devedores() 
if __name__ == "__main__":
    main()