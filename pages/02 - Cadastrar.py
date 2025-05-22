import streamlit as st
import pandas as pd

if 'df' not in st.session_state:
    st.session_state.df = None
if 'filtered_df' not in st.session_state:
    st.session_state.filtered_df = None

def load_excel(file):
    try:
        return pd.read_excel(file, engine='openpyxl')
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
        df = load_excel(uploaded_file)
        if df is not None:
            st.session_state.df = df
            st.session_state.filtered_df = df.copy()
            st.sidebar.success("Arquivo carregado com sucesso!")

def show_cadastro():
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
                if st.session_state.df is None:
                    st.session_state.df = pd.DataFrame([novo_registro])
                else:
                    st.session_state.df = pd.concat(
                        [st.session_state.df, pd.DataFrame([novo_registro])],
                        ignore_index=True
                    )
                
                st.session_state.filtered_df = st.session_state.df.copy()
                st.success("Devedor cadastrado com sucesso!")
                
                st.dataframe(
                    st.session_state.df.tail(1),
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.error("Preencha os campos obrigatórios: ID, Nome e Valor")
def main():
    st.set_page_config(
        page_title="Sistema de Cobranças",
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    sidebar()
    show_cadastro()

if __name__ == "__main__":
    main()