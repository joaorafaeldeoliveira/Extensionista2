# devedores_service.py
import pandas as pd
import io
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from datetime import datetime, date, timedelta
from functools import wraps
from typing import Tuple, Any, Dict, List

# Importações do seu projeto
from database import get_session, Devedor, StatusDevedor

# ### NOVO: Decorador para Gerenciamento de Sessão ###
# Este decorador simplifica todas as funções que acessam o banco de dados.
# Ele cuida de:
# 1. Abrir a sessão.
# 2. Passar a sessão para a função.
# 3. Fazer o commit em caso de sucesso.
# 4. Fazer o rollback em caso de erro.
# 5. Fechar a sessão, não importa o que aconteça.
def session_handler(func):
    """Um decorador que gerencia o ciclo de vida da sessão do SQLAlchemy."""
    @wraps(func)
    def wrapper(db_engine, *args, **kwargs):
        session = get_session(db_engine)
        try:
            # Passa a sessão como o primeiro argumento para a função original
            result = func(session, *args, **kwargs)
            session.commit()
            return result
        except IntegrityError as e:
            session.rollback()
            # Retorna um erro específico para violações de chave única (ID duplicado)
            return False, f"Erro de Integridade: Um registro com dados únicos já existe. Detalhe: {e.orig}"
        except Exception as e:
            session.rollback()
            # Retorna um erro genérico para outras exceções
            return False, f"Ocorreu um erro inesperado na operação: {e}"
        finally:
            session.close()
    return wrapper

# ### ALTERADO: Função de carregamento otimizada ###
# Usa pd.read_sql para carregar os dados diretamente em um DataFrame,
# o que é significativamente mais rápido do que iterar sobre os resultados.
def load_devedores_from_db(db_engine) -> pd.DataFrame:
    """Carrega todos os devedores do banco de dados de forma eficiente."""
    try:
        with db_engine.connect() as connection:
            # A query busca todas as colunas da tabela Devedor
            query = select(Devedor)
            df = pd.read_sql(query, connection)
        
        # Converte as colunas de data/hora para o tipo correto, tratando erros
        for col in ['data_cobranca', 'ultima_cobranca', 'data_pagamento']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Converte o valor do enum para string, se necessário
        if 'status' in df.columns:
             df['status'] = df['status'].apply(lambda s: s.value if isinstance(s, StatusDevedor) else s)
                
        return df
    except Exception as e:
        print(f"Erro ao carregar devedores do banco de dados: {e}")
        # Retorna um DataFrame vazio com as colunas esperadas em caso de falha
        return pd.DataFrame(columns=[
            'id', 'pessoa', 'nome', 'valortotal', 'atraso', 'telefone',
            'data_cobranca', 'ultima_cobranca', 'status', 'data_pagamento'
        ])

# ### ALTERADO: Funções simplificadas com o decorador ###
@session_handler
def add_devedor_to_db(session, nome: str, valortotal: float, atraso: int, telefone: str = None, pessoa_id: str = None) -> Tuple[bool, str]:

    if not nome:
        return False, "Erro: O campo 'Nome' é obrigatório e não pode ser vazio."
    
    novo_devedor = Devedor(
        pessoa=pessoa_id,
        nome=nome,
        valortotal=valortotal,
        atraso=atraso,
        telefone=telefone,
        status=StatusDevedor.PENDENTE # Usando um status mais genérico como padrão
    )
    session.add(novo_devedor)
    # o commit é feito pelo decorador
    return True, f"Devedor '{nome}' adicionado com sucesso!"

# ### NOVO: Função para atualizar devedor (para a edição na tabela) ###
@session_handler
def update_devedor_in_db(session, devedor_id: int, updates: Dict[str, Any]) -> Tuple[bool, str]:
    """Atualiza um devedor existente com base em um dicionário de mudanças."""
    devedor = session.query(Devedor).filter_by(id=devedor_id).first()
    if not devedor:
        return False, "Devedor não encontrado para atualização."

    for key, value in updates.items():
        # Converte o valor do enum de volta para o objeto Enum antes de salvar
        if key == 'status' and isinstance(value, str):
            try:
                # Transforma a string 'Em aberto' no objeto StatusDevedor.EM_ABERTO
                enum_value = StatusDevedor(value)
                setattr(devedor, key, enum_value)
            except ValueError:
                return False, f"Status '{value}' inválido."
        else:
            setattr(devedor, key, value)
            
    return True, f"Devedor ID {devedor_id} atualizado com sucesso."

@session_handler
def remover_devedor_from_db(session, devedor_id: int) -> Tuple[bool, str]:
    """Remove um devedor do banco de dados."""
    devedor = session.query(Devedor).filter_by(id=devedor_id).first()
    if devedor:
        session.delete(devedor)
        return True, "Devedor removido com sucesso!"
    else:
        return False, "Devedor não encontrado para remoção."

def import_excel_to_db(db_engine, file: io.BytesIO) -> Tuple[bool, str]:

    try:
        df_excel = pd.read_excel(file, engine='openpyxl')
    except Exception as e:
        return False, f"Erro ao ler o arquivo Excel: {e}"

    required_cols = ['pessoa', 'nome', 'valortotal', 'atraso']
    if not all(col in df_excel.columns for col in required_cols):
        return False, f"O arquivo Excel deve conter as colunas: {', '.join(required_cols)}."

    # Limpeza dos dados
    df_excel['pessoa'] = df_excel['pessoa'].astype(str).str.strip()
    df_excel.dropna(subset=['pessoa'], inplace=True) # Remove linhas sem 'pessoa'
    df_excel = df_excel[df_excel['pessoa'] != '']
    if df_excel.empty:
        return False, "Nenhum devedor com ID Pessoa válido encontrado no arquivo."

    session = get_session(db_engine)
    try:

        existing_pessoas_query = session.query(Devedor.nome).all()
        existing_pessoas = {p[0] for p in existing_pessoas_query}

        # 2. Identifica duplicatas usando Pandas
        df_excel['is_duplicate'] = df_excel['pessoa'].isin(existing_pessoas)
        df_to_add = df_excel[~df_excel['is_duplicate']].copy()
        df_excel['pessoa'] = df_excel['pessoa'].astype(str).str.strip().str.upper()
        existing_pessoas = {str(p[0]).strip().upper() for p in existing_pessoas_query}
        count_skipped = len(df_excel) - len(df_to_add)

        if df_to_add.empty:
            return True, f"Importação concluída. Nenhum devedor novo para adicionar. {count_skipped} devedores já existentes foram pulados."

        # Prepara os dados para inserção em massa
        df_to_add['status'] = StatusDevedor.EM_ABERTO
        df_to_add['telefone'] = df_to_add.apply(
            lambda row: str(row['celular1']) if 'celular1' in row and pd.notna(row['celular1']) else str(row.get('telefone')),
            axis=1
        )
        
        # Seleciona apenas as colunas que correspondem ao modelo Devedor
        model_cols = [c.key for c in Devedor.__table__.columns if c.key not in ['id']]
        records_to_insert = df_to_add[model_cols].to_dict('records')
        
        # 3. Insere todos os registros de uma vez
        session.bulk_insert_mappings(Devedor, records_to_insert)
        session.commit()
        
        return True, f"Importação concluída com sucesso! Adicionados: {len(records_to_insert)}. Pulados (já existentes): {count_skipped}."
    
    except Exception as e:
        session.rollback()
        return False, f"Erro durante a importação para o banco de dados: {e}"
    finally:
        session.close()

def export_devedores_to_excel(df_to_export: pd.DataFrame) -> Tuple[io.BytesIO | None, str]:
    """Exporta um DataFrame de devedores para um arquivo Excel em memória."""
    if df_to_export.empty:
        return None, "Nenhum dado para exportar."

    output = io.BytesIO()
    df_copy = df_to_export.copy()

    # Formata as colunas de data/hora para string antes de exportar
    for col in ['data_cobranca', 'ultima_cobranca', 'data_pagamento']:
        if col in df_copy.columns and pd.api.types.is_datetime64_any_dtype(df_copy[col]):
            df_copy[col] = df_copy[col].dt.strftime('%Y-%m-%d %H:%M:%S').replace('NaT', '')

    try:
        with pd.ExcelWriter(output, engine='xlsxwriter', datetime_format='yyyy-mm-dd') as writer:
            df_copy.to_excel(writer, index=False, sheet_name='Devedores')
        output.seek(0)
        return output.getvalue(), "Dados exportados com sucesso!"
    except Exception as e:
        return None, f"Erro ao gerar o arquivo Excel: {e}"

# As funções abaixo, relacionadas a cobranças, foram mantidas com o novo padrão de decorador
@session_handler
def marcar_como_pago_in_db(session, devedor_id: int) -> Tuple[bool, str]:
    """Marca um devedor como pago."""
    return update_devedor_in_db(
        session, 
        devedor_id, 
        {'status': StatusDevedor.PAGO, 'data_pagamento': date.today()}
    )

@session_handler
def marcar_cobranca_feita_e_reagendar_in_db(session, devedor_id: int, data_programada: date = None) -> Tuple[bool, str]:
    """Registra uma cobrança e agenda a próxima."""
    devedor = session.query(Devedor).filter_by(id=devedor_id).first()
    if not devedor:
        return False, "Devedor não encontrado"
    
    devedor.ultima_cobranca = date.today()
    devedor.data_cobranca = data_programada if data_programada else date.today() + timedelta(days=10)
    devedor.status = StatusDevedor.AGENDADO

    # A lógica de 'fase_cobranca' é mantida se existir no seu modelo
    if hasattr(devedor, 'fase_cobranca') and devedor.fase_cobranca < 3:
        devedor.fase_cobranca += 1
    
    return True, "Cobrança registrada e próxima agendada com sucesso."