import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

# Configuração inicial
if 'df' not in st.session_state:
    st.session_state.df = None
if 'filtered_df' not in st.session_state:
    st.session_state.filtered_df = None

# Função para carregar dados
def load_excel(file):
    try:
        df = pd.read_excel(file, engine='openpyxl')
        # Garantir que as colunas necessárias existam
        if 'data_cobranca' not in df.columns:
            df['data_cobranca'] = pd.NaT
        if 'status' not in df.columns:
            df['status'] = 'Pendente'
        return df
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        return None

def sidebar():
    with st.sidebar:
        st.header("📂 Carregar Planilha")
        uploaded_file = st.file_uploader(
            "Selecione o arquivo de devedores",
            type=["xlsx", "xls"],
            key="file_uploader"
        )
        
        if uploaded_file is not None:
            df = load_excel(uploaded_file)
            if df is not None:
                st.session_state.df = df
                st.session_state.filtered_df = df.copy()
                st.success("Dados carregados com sucesso!")

def atualizar_cobranca(index):
    hoje = datetime.now()
    nova_data = hoje + timedelta(days=10)
    st.session_state.filtered_df.at[index, 'data_cobranca'] = nova_data
    st.session_state.filtered_df.at[index, 'ultima_cobranca'] = hoje.strftime('%d/%m/%Y')
    st.rerun()

def marcar_como_pago(index):
    st.session_state.filtered_df.at[index, 'status'] = 'Pago'
    st.session_state.filtered_df.at[index, 'data_pagamento'] = datetime.now().strftime('%d/%m/%Y')
    st.rerun()

def remover_devedor(index):
    st.session_state.filtered_df = st.session_state.filtered_df.drop(index)
    st.rerun()

def exibir_devedores():
    st.title("📋 Controle de Cobranças")
    
    if st.session_state.df is None:
        st.warning("Por favor, carregue um arquivo Excel na sidebar")
        return
    
    # Filtros
    with st.expander("🔍 Filtros", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            filtro_status = st.selectbox(
                "Status",
                options=["Todos", "Pendente", "Pago"],
                index=0
            )
        with col2:
            ordenar_por = st.selectbox(
                "Ordenar por",
                options=["Data de Cobrança", "Valor Devido", "Dias em Atraso"],
                index=0
            )
    
    # Aplicar filtros
    df_filtrado = st.session_state.df.copy()
    
    if filtro_status != "Todos":
        df_filtrado = df_filtrado[df_filtrado['status'] == filtro_status]
    
    if ordenar_por == "Data de Cobrança":
        df_filtrado = df_filtrado.sort_values('data_cobranca', ascending=True)
    elif ordenar_por == "Valor Devido":
        df_filtrado = df_filtrado.sort_values('valortotal', ascending=False)
    else:
        df_filtrado = df_filtrado.sort_values('atraso', ascending=False)
    
    st.session_state.filtered_df = df_filtrado
    
    # Exibir cards
    st.subheader(f"📌 {len(df_filtrado)} devedores encontrados")
    
    for index, row in df_filtrado.iterrows():
        with st.container(border=True):
            cols = st.columns([3, 1, 1, 1])
            
            with cols[0]:
                st.markdown(f"### {row['nome']}")
                st.caption(f"📞 {row.get('telefone', 'N/A')} | 📅 {row.get('ultima_cobranca', 'Nunca cobrado')}")
                st.write(f"**Valor devido:** R$ {row['valortotal']:,.2f} | **Atraso:** {row['atraso']} dias")
                
                if pd.notna(row['data_cobranca']):
                    data_cob = row['data_cobranca'].strftime('%d/%m/%Y') if isinstance(row['data_cobranca'], pd.Timestamp) else row['data_cobranca']
                    st.write(f"⏳ **Próxima cobrança:** {data_cob}")
                
                st.write(f"**Status:** {'✅ Pago' if row['status'] == 'Pago' else '⚠️ Pendente'}")
            
            with cols[1]:
                if st.button("📞 Cobrado", key=f"cobrar_{index}", use_container_width=True):
                    atualizar_cobranca(index)
            
            with cols[2]:
                if st.button("💳 Pago", key=f"pago_{index}", disabled=(row['status'] == 'Pago'), 
                           use_container_width=True):
                    marcar_como_pago(index)
            
            with cols[3]:
                if st.button("❌ Remover", key=f"remover_{index}", use_container_width=True):
                    remover_devedor(index)

def main():
    st.set_page_config(
        page_title="Sistema de Cobranças",
        page_icon="💰",
        layout="wide"
    )
    
    sidebar()
    exibir_devedores()

if __name__ == "__main__":
    main()