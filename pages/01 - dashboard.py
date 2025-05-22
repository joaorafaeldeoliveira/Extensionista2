import streamlit as st
import pandas as pd
from datetime import datetime
import numpy as np


if 'df' not in st.session_state:
    st.session_state.df = None
if 'filtered_df' not in st.session_state:
    st.session_state.filtered_df = None

def load_excel(file):
    try:
        return pd.read_excel(file, engine='openpyxl')
    except:
        try:
            return pd.read_excel(file, engine='xlrd')
        except Exception as e:
            st.error(f"Erro ao ler o arquivo: {e}")
            return None

def sidebar():
    st.sidebar.header("Carregar Planilha")
    uploaded_file = st.sidebar.file_uploader(
        "Selecione o arquivo Excel",
        type=["xlsx", "xls"],
        key="file_uploader"
    )
    
    if uploaded_file is not None:
        st.session_state.df = load_excel(uploaded_file)
        if st.session_state.df is not None:
            st.sidebar.success("Arquivo carregado com sucesso!")
            st.session_state.filtered_df = st.session_state.df.copy()

def main():
    st.set_page_config(
        page_title="Sistema de Cobranças",
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.title("📊 Dashboard de Cobranças")
    sidebar()
    
    if st.session_state.filtered_df is not None:
        st.header("Resumo Geral")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Devedores", len(st.session_state.filtered_df))
        col2.metric("Valor Total Devido", 
                   f"R$ {st.session_state.filtered_df['valortotal'].sum():,.2f}")
        col3.metric("Média de Dias em Atraso", 
                   int(st.session_state.filtered_df['atraso'].mean()))
        col4.metric("Maior Valor Devido", 
                   f"R$ {st.session_state.filtered_df['valortotal'].max():,.2f}")
        

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
        
        st.header("Top 10 Maiores Devedores")
        top_devedores = st.session_state.filtered_df.nlargest(10, 'valortotal')
        st.dataframe(
            top_devedores[['nome', 'atraso', 'valortotal']],
            height=400,
            use_container_width=True
        )
    else:
        st.warning("Nenhum dado disponível. Carregue um arquivo Excel na sidebar.")

if __name__ == "__main__":
    main()