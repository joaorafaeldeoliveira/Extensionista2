import pandas as pd
import io
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from datetime import datetime, date, timedelta
from functools import wraps
from typing import Tuple, Any, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import date, datetime
import math

from database import get_session, Devedor, StatusDevedor

def session_handler(func):
    
    @wraps(func)
    def wrapper(db_engine, *args, **kwargs):
        session = get_session(db_engine)
        try:
           
            result = func(session, *args, **kwargs)
            session.commit()
            return result
        except IntegrityError as e:
            session.rollback()
           
            return False, f"Erro de Integridade: Um registro com dados únicos já existe. Detalhe: {e.orig}"
        except Exception as e:
            session.rollback()
            
            return False, f"Ocorreu um erro inesperado na operação: {e}"
        finally:
            session.close()
    return wrapper

def load_devedores_from_db(db_engine) -> pd.DataFrame:
   
    try:
        with db_engine.connect() as connection:
           
            query = select(Devedor)
            df = pd.read_sql(query, connection)
        

        for col in ['data_cobranca', 'ultima_cobranca', 'data_pagamento']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        

        if 'status' in df.columns:
             df['status'] = df['status'].apply(lambda s: s.value if isinstance(s, StatusDevedor) else s)
                
        return df
    except Exception as e:
        print(f"Erro ao carregar devedores do banco de dados: {e}")
        return pd.DataFrame(columns=[
            'id', 'pessoa', 'nome', 'valortotal', 'atraso', 'telefone',
            'data_cobranca', 'ultima_cobranca', 'status', 'data_pagamento'
        ])

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
        status=StatusDevedor.PENDENTE 
    )
    session.add(novo_devedor)
    
    return True, f"Devedor '{nome}' adicionado com sucesso!"

@session_handler
def update_devedor_in_db(session, devedor_id: int, updates: Dict[str, Any]) -> Tuple[bool, str]:
    
    devedor = session.query(Devedor).filter_by(id=devedor_id).first()
    if not devedor:
        return False, "Devedor não encontrado para atualização."

    for key, value in updates.items():
       
        if key == 'status' and isinstance(value, str):
            try:
                
                enum_value = StatusDevedor(value)
                setattr(devedor, key, enum_value)
            except ValueError:
                return False, f"Status '{value}' inválido."
        else:
            setattr(devedor, key, value)
            
    return True, f"Devedor ID {devedor_id} atualizado com sucesso."

@session_handler
def remover_devedor_from_db(session, devedor_id: int) -> Tuple[bool, str]:
    
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
    df_excel.dropna(subset=['pessoa'], inplace=True) 
    df_excel = df_excel[df_excel['pessoa'] != '']
    if df_excel.empty:
        return False, "Nenhum devedor com ID Pessoa válido encontrado no arquivo."

    session = get_session(db_engine)
    try:

        existing_pessoas_query = session.query(Devedor.nome).all()
        existing_pessoas = {p[0] for p in existing_pessoas_query}

        
        df_excel['is_duplicate'] = df_excel['pessoa'].isin(existing_pessoas)
        df_to_add = df_excel[~df_excel['is_duplicate']].copy()
        df_excel['pessoa'] = df_excel['pessoa'].astype(str).str.strip().str.upper()
        existing_pessoas = {str(p[0]).strip().upper() for p in existing_pessoas_query}
        count_skipped = len(df_excel) - len(df_to_add)

        if df_to_add.empty:
            return True, f"Importação concluída. Nenhum devedor novo para adicionar. {count_skipped} devedores já existentes foram pulados."

        
        df_to_add['status'] = StatusDevedor.EM_ABERTO
        df_to_add['telefone'] = df_to_add.apply(
            lambda row: str(row['celular1']) if 'celular1' in row and pd.notna(row['celular1']) else str(row.get('telefone')),
            axis=1
        )
        
        model_cols = [c.key for c in Devedor.__table__.columns if c.key not in ['id']]
        records_to_insert = df_to_add[model_cols].to_dict('records')
        
        session.bulk_insert_mappings(Devedor, records_to_insert)
        session.commit()
        
        return True, f"Importação concluída com sucesso! Adicionados: {len(records_to_insert)}. Pulados (já existentes): {count_skipped}."
    
    except Exception as e:
        session.rollback()
        return False, f"Erro durante a importação para o banco de dados: {e}"
    finally:
        session.close()

def export_devedores_to_excel(df_to_export: pd.DataFrame) -> Tuple[io.BytesIO | None, str]:
    if df_to_export.empty:
        return None, "Nenhum dado para exportar."

    output = io.BytesIO()
    df_copy = df_to_export.copy()

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

@session_handler
def marcar_como_pago_in_db(session, devedor_id: int) -> Tuple[bool, str]:
    
    return update_devedor_in_db(
        session, 
        devedor_id, 
        {'status': StatusDevedor.PAGO, 'data_pagamento': date.today()}
    )

@session_handler
def marcar_cobranca_feita_e_reagendar_in_db(session, devedor_id: int, data_programada: date = None) -> Tuple[bool, str]:
    
    devedor = session.query(Devedor).filter_by(id=devedor_id).first()
    if not devedor:
        return False, "Devedor não encontrado"
    
    devedor.ultima_cobranca = date.today()
    devedor.data_cobranca = data_programada if data_programada else date.today() + timedelta(days=10)
    devedor.status = StatusDevedor.AGENDADO

    
    if hasattr(devedor, 'fase_cobranca') and devedor.fase_cobranca < 3:
        devedor.fase_cobranca += 1
    
    return True, "Cobrança registrada e próxima agendada com sucesso."

def get_devedores_para_acoes_count(db_engine, filtro_nome: str = None) -> int:
    """Conta quantos devedores precisam de ação, aplicando filtros."""
    with Session(db_engine) as session:
        hoje = date.today()
        query = session.query(func.count(Devedor.id))
        
        # Lógica de filtro replicada do seu app Streamlit
        nao_pago = Devedor.status != StatusDevedor.PAGO.value
        agendado_para_hoje = (Devedor.status == StatusDevedor.AGENDADO.value) & (func.date(Devedor.data_cobranca) == hoje)
        requer_acao = Devedor.status != StatusDevedor.AGENDADO.value
        
        query = query.filter(nao_pago & or_(agendado_para_hoje, requer_acao))

        if filtro_nome:
            query = query.filter(Devedor.nome.ilike(f"%{filtro_nome}%"))
            
        return query.scalar()

def get_devedores_para_acoes_paginated(db_engine, page: int, page_size: int, sort_column: str, sort_ascending: bool, filtro_nome: str = None) -> pd.DataFrame:
    """Busca uma página de devedores que precisam de ação."""
    with Session(db_engine) as session:
        offset = page * page_size
        hoje = date.today()
        
        query = session.query(Devedor)

        # Mesma lógica de filtro
        nao_pago = Devedor.status != StatusDevedor.PAGO.value
        agendado_para_hoje = (Devedor.status == StatusDevedor.AGENDADO.value) & (func.date(Devedor.data_cobranca) == hoje)
        requer_acao = Devedor.status != StatusDevedor.AGENDADO.value
        
        query = query.filter(nao_pago & or_(agendado_para_hoje, requer_acao))

        if filtro_nome:
            query = query.filter(Devedor.nome.ilike(f"%{filtro_nome}%"))

        # Ordenação
        coluna_ordenacao = getattr(Devedor, sort_column, Devedor.nome)
        if not sort_ascending:
            coluna_ordenacao = coluna_ordenacao.desc()
        query = query.order_by(coluna_ordenacao)

        # Paginação
        query = query.limit(page_size).offset(offset)
        
        # Ler para o pandas
        df = pd.read_sql(query.statement, session.bind)
        return df

def get_devedores_para_dia_count(db_engine, selected_date: date) -> int:
    """
    Conta o número total de cobranças agendadas para uma data específica.
    """
    with Session(db_engine) as session:
        # Usamos func.date() para comparar apenas a parte da data, ignorando a hora.
        query = session.query(func.count(Devedor.id)).filter(
            func.date(Devedor.data_cobranca) == selected_date
        )
        total = query.scalar()
        return total if total is not None else 0

def get_devedores_para_dia_paginated(db_engine, selected_date: date, page: int, page_size: int) -> pd.DataFrame:
    """
    Busca uma página de devedores com cobrança agendada para uma data específica.
    """
    with Session(db_engine) as session:
        offset = page * page_size
        
        query = session.query(Devedor).filter(
            func.date(Devedor.data_cobranca) == selected_date
        ).order_by(
            Devedor.nome  # Ordenar por nome para consistência entre as páginas
        ).limit(
            page_size
        ).offset(
            offset
        )
        
        df = pd.read_sql(query.statement, session.bind)
        return df