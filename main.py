import streamlit as st
import pandas as pd
from datetime import datetime
import numpy as np

# Configuração da página
st.set_page_config(
    page_title="Controle de Cobranças",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Função para ler arquivos Excel
def load_excel(file):
    try:
        return pd.read_excel(file, engine='openpyxl')
    except:
        try:
            return pd.read_excel(file, engine='xlrd')
        except Exception as e:
            st.error(f"Erro ao ler o arquivo: {e}")
            return None

# Sessão para armazenar dados
if 'df' not in st.session_state:
    st.session_state.df = None
if 'filtered_df' not in st.session_state:
    st.session_state.filtered_df = None

# Sidebar - Navegação
with st.sidebar:
    st.title("Navegação")
    page = st.radio(
        "Selecione a página:",
        ["📋 Lista de Devedores", "📊 Dashboard", "➕ Cadastrar Novo"]
    )
    
    st.markdown("---")
    st.header("Carregar Planilha")
    uploaded_file = st.file_uploader(
        "Selecione o arquivo Excel",
        type=["xlsx", "xls"],
        key="file_uploader"
    )
    
    if uploaded_file is not None:
        st.session_state.df = load_excel(uploaded_file)
        if st.session_state.df is not None:
            st.success("Arquivo carregado com sucesso!")
            st.session_state.filtered_df = st.session_state.df.copy()

# Função para aplicar filtros avançados
def apply_filters(df, filters):
    filtered = df.copy()
    
    # Filtro por faixa de valores
    if filters['valor_range'][0] > 0 or filters['valor_range'][1] < float('inf'):
        filtered = filtered[
            (filtered['valortotal'] >= filters['valor_range'][0]) & 
            (filtered['valortotal'] <= filters['valor_range'][1])
        ]
    
    # Filtro por dias em atraso
    if filters['dias_range'][0] > 0 or filters['dias_range'][1] < float('inf'):
        filtered = filtered[
            (filtered['atraso'] >= filters['dias_range'][0]) & 
            (filtered['atraso'] <= filters['dias_range'][1])
        ]
    
    # Filtro por categorias de valor
    if filters['valor_categoria'] != "Todos":
        if filters['valor_categoria'] == "Pequenos (até R$ 500)":
            filtered = filtered[filtered['valortotal'] <= 500]
        elif filters['valor_categoria'] == "Médios (R$ 500 - R$ 2.000)":
            filtered = filtered[(filtered['valortotal'] > 500) & (filtered['valortotal'] <= 2000)]
        elif filters['valor_categoria'] == "Grandes (acima de R$ 2.000)":
            filtered = filtered[filtered['valortotal'] > 2000]
    
    # Filtro por status de atraso
    if filters['status_atraso'] != "Todos":
        if filters['status_atraso'] == "Iniciando (1-30 dias)":
            filtered = filtered[filtered['atraso'] <= 30]
        elif filters['status_atraso'] == "Moderado (31-90 dias)":
            filtered = filtered[(filtered['atraso'] > 30) & (filtered['atraso'] <= 90)]
        elif filters['status_atraso'] == "Atrasado (91-180 dias)":
            filtered = filtered[(filtered['atraso'] > 90) & (filtered['atraso'] <= 180)]
        elif filters['status_atraso'] == "Crítico (acima de 180 dias)":
            filtered = filtered[filtered['atraso'] > 180]
    
    # Filtro por nome (busca textual)
    if filters['nome_search']:
        filtered = filtered[
            filtered['nome'].str.contains(filters['nome_search'], case=False, na=False)
        ]
    
    return filtered

# Página 1: Lista de Devedores com Filtros Aprimorados
if page == "📋 Lista de Devedores":
    st.title("📋 Lista de Devedores")
    
    if st.session_state.df is not None:
        required_columns = ['pessoa', 'nome', 'atraso', 'valortotal']
        if all(col in st.session_state.df.columns for col in required_columns):
            # Container de filtros expandível
            with st.expander("🔍 Filtros Avançados", expanded=True):
                # Layout em colunas para organizar os filtros
                col1, col2 = st.columns(2)
                
                with col1:
                    # Filtro por faixa de valores com slider melhorado
                    min_val = float(st.session_state.df['valortotal'].min())
                    max_val = float(st.session_state.df['valortotal'].max())


                    step_val = 10.0 if max_val <= 100 else (100.0 if max_val <= 10000 else 1000.0)  # Note os .0 para float

                    valor_range = st.slider(
                        "Faixa de Valores Devidos (R$)",
                        min_value=min_val,
                        max_value=max_val,
                        value=(min_val, max_val),
                        step=step_val,  # Agora todos são float
                        help="Selecione a faixa de valores desejada"
                    )
                    
                    # Filtro por categorias pré-definidas de valores
                    valor_categoria = st.selectbox(
                        "Categoria por Valor",
                        options=["Todos", "Pequenos (até R$ 500)", "Médios (R$ 500 - R$ 2.000)", "Grandes (acima de R$ 2.000)"],
                        index=0
                    )
                
                with col2:
                    # Filtro por dias em atraso com slider
                    min_dias = int(st.session_state.df['atraso'].min())
                    max_dias = int(st.session_state.df['atraso'].max())
                    
                    dias_range = st.slider(
                        "Dias em Atraso",
                        min_value=min_dias,
                        max_value=max_dias,
                        value=(min_dias, max_dias),
                        help="Selecione a faixa de dias em atraso"
                    )
                    
                    # Filtro por status de atraso
                    status_atraso = st.selectbox(
                        "Status do Atraso",
                        options=["Todos", "Iniciando (1-30 dias)", "Moderado (31-90 dias)", "Atrasado (91-180 dias)", "Crítico (acima de 180 dias)"],
                        index=0
                    )
                
                # Barra de busca por nome
                nome_search = st.text_input(
                    "Buscar por nome",
                    placeholder="Digite parte do nome para filtrar...",
                    help="Filtre os devedores que contém este texto no nome"
                )
            
            # Aplicar filtros
            filters = {
                'valor_range': valor_range,
                'dias_range': dias_range,
                'valor_categoria': valor_categoria,
                'status_atraso': status_atraso,
                'nome_search': nome_search
            }
            
            st.session_state.filtered_df = apply_filters(st.session_state.df, filters)
            
            # Mostrar resumo dos filtros aplicados
            st.info(f"Mostrando {len(st.session_state.filtered_df)} de {len(st.session_state.df)} registros")
            
            # Mostrar tabela com opções de exibição
            st.subheader("Registros Filtrados")
            
            # Opções de paginação
            items_per_page = st.selectbox(
                "Itens por página",
                options=[10, 25, 50, 100, "Todos"],
                index=1
            )
            
            if items_per_page != "Todos":
                page_number = st.number_input(
                    "Página",
                    min_value=1,
                    max_value=int(np.ceil(len(st.session_state.filtered_df)/items_per_page)),
                    value=1
                )
                start_idx = (page_number - 1) * items_per_page
                end_idx = start_idx + items_per_page
                display_df = st.session_state.filtered_df.iloc[start_idx:end_idx]
            else:
                display_df = st.session_state.filtered_df
            
            st.dataframe(
                display_df,
                height=600,
                use_container_width=True,
                column_config={
                    "valortotal": st.column_config.NumberColumn(
                        "Valor Total",
                        format="R$ %.2f"
                    ),
                    "atraso": st.column_config.NumberColumn(
                        "Dias em Atraso",
                        format="%d dias"
                    )
                }
            )
            
            # Botões de ação
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("Exportar para Excel"):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    st.session_state.filtered_df.to_excel(
                        f"devedores_filtrados_{timestamp}.xlsx", 
                        index=False
                    )
                    st.success(f"Arquivo exportado: devedores_filtrados_{timestamp}.xlsx")
            
            with col2:
                if st.button("Limpar Filtros"):
                    st.session_state.filtered_df = st.session_state.df.copy()
                    st.rerun()
            
            with col3:
                st.download_button(
                    label="Baixar Dados Filtrados",
                    data=st.session_state.filtered_df.to_csv(index=False).encode('utf-8'),
                    file_name=f"devedores_filtrados_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime='text/csv'
                )
        else:
            st.error("O arquivo não contém todas as colunas necessárias.")
            st.write("Colunas encontradas:", list(st.session_state.df.columns))
    else:
        st.warning("Por favor, carregue um arquivo Excel na sidebar.")
# Página 2: Dashboard
elif page == "📊 Dashboard":
    st.title("📊 Dashboard de Cobranças")
    
    if st.session_state.filtered_df is not None:
        # Métricas principais
        st.header("Resumo Geral")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Devedores", len(st.session_state.filtered_df))
        col2.metric("Valor Total Devido", 
                   f"R$ {st.session_state.filtered_df['valortotal'].sum():,.2f}")
        col3.metric("Média de Dias em Atraso", 
                   int(st.session_state.filtered_df['atraso'].mean()))
        col4.metric("Maior Valor Devido", 
                   f"R$ {st.session_state.filtered_df['valortotal'].max():,.2f}")
        
        # Gráficos
        st.header("Visualizações")
        
        tab1, tab2 = st.tabs(["Distribuição por Dias", "Distribuição por Valor"])
        
        with tab1:
            st.subheader("Dias em Atraso")
            st.bar_chart(
                st.session_state.filtered_df['atraso'].value_counts().sort_index(),
                height=400
            )
        
        with tab2:
            st.subheader("Valores Devidos")
            st.area_chart(
                st.session_state.filtered_df.groupby('atraso')['valortotal'].sum(),
                height=400
            )
        
        # Top 10 maiores devedores
        st.header("Top 10 Maiores Devedores")
        top_devedores = st.session_state.filtered_df.nlargest(10, 'valortotal')
        st.dataframe(
            top_devedores[['nome', 'atraso', 'valortotal']],
            height=400,
            use_container_width=True
        )
    else:
        st.warning("Nenhum dado disponível. Carregue um arquivo Excel na sidebar.")

# Página 3: Cadastro
elif page == "➕ Cadastrar Novo":
    st.title("➕ Cadastrar Novo Devedor")
    
    with st.form("novo_devedor", clear_on_submit=True):
        st.header("Informações Básicas")
        col1, col2 = st.columns(2)
        
        with col1:
            pessoa = st.text_input("ID da Pessoa*", help="Código único do devedor")
            nome = st.text_input("Nome Completo*")
            telefone = st.text_input("Telefone")
            celular = st.text_input("Celular")
        
        with col2:
            titulos = st.number_input("Número de Títulos*", min_value=1, value=1)
            atraso = st.number_input("Dias em Atraso*", min_value=1, value=30)
            valor = st.number_input("Valor Principal (R$)*", min_value=0.0, value=0.0)
            juros = st.number_input("Juros (R$)", min_value=0.0, value=0.0)
        
        valortotal = valor + juros
        
        st.markdown("**Campos obrigatórios*")
        submitted = st.form_submit_button("Salvar Devedor")
        
        if submitted:
            if pessoa and nome and valor > 0:
                novo_registro = {
                    'pessoa': pessoa,
                    'nome': nome,
                    'telefone': telefone,
                    'celular1': celular,
                    'titulos': titulos,
                    'atraso': atraso,
                    'valor': valor,
                    'juros': juros,
                    'valortotal': valortotal
                }
                
                # Adiciona ao DataFrame
                if st.session_state.df is None:
                    st.session_state.df = pd.DataFrame([novo_registro])
                else:
                    st.session_state.df = pd.concat(
                        [st.session_state.df, pd.DataFrame([novo_registro])],
                        ignore_index=True
                    )
                
                st.session_state.filtered_df = st.session_state.df.copy()
                st.success("Devedor cadastrado com sucesso!")
                
                # Mostra o registro adicionado
                st.dataframe(
                    st.session_state.df.tail(1),
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.error("Preencha os campos obrigatórios: ID, Nome e Valor")