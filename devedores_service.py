# devedores_service.py
import pandas as pd
import io
from sqlalchemy.exc import IntegrityError
from datetime import datetime, date
from database import get_session, Devedor, StatusDevedor

# Função para carregar todos os devedores do banco de dados para um DataFrame
def load_devedores_from_db(db_engine):
    session = get_session(db_engine)
    try:
        devedores = session.query(Devedor).all()
        data = []
        for d in devedores:
            data.append({
                'id': d.id,
                'pessoa': d.pessoa,
                'nome': d.nome,
                'valortotal': d.valortotal,
                'atraso': d.atraso,
                'telefone': d.telefone,
                'data_cobranca': d.data_cobranca, # MANTIDO
                'ultima_cobranca': d.ultima_cobranca, # MANTIDO
                'status': d.status.value if isinstance(d.status, StatusDevedor) else d.status,
                'data_pagamento': d.data_pagamento
            })
        
        df = pd.DataFrame(data)
        
        for col in ['data_cobranca', 'ultima_cobranca', 'data_pagamento']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce') 
        return df
    except Exception as e:
        print(f"Erro ao carregar devedores do banco de dados: {e}")
        return pd.DataFrame(columns=[
            'id', 'pessoa', 'nome', 'valortotal', 'atraso', 'telefone',
            'data_cobranca', 'ultima_cobranca', 'status', 'data_pagamento'
        ])
    finally:
        session.close()

# Função para adicionar um novo devedor ao banco de dados
def add_devedor_to_db(db_engine, nome, valortotal, atraso, telefone=None, pessoa_id=None):
    session = get_session(db_engine)
    try:
        if pessoa_id:
            existing_devedor = session.query(Devedor).filter_by(pessoa=pessoa_id).first()
            if existing_devedor:
                return False, f"Erro: Já existe um devedor com o ID Pessoa '{pessoa_id}'. Por favor, use um ID único."
        
        novo_devedor = Devedor(
            pessoa=pessoa_id if pessoa_id else None,
            nome=nome,
            valortotal=valortotal,
            atraso=atraso,
            telefone=telefone,
            status=StatusDevedor.PENDENTE, # Sempre começa como PENDENTE
            data_cobranca=None, # Inicia nulo, será preenchido na tela de Cobranças
            ultima_cobranca=None, # Inicia nulo, será preenchido na tela de Cobranças
            data_pagamento=None # Inicia nulo, será preenchido na tela de Cobranças
        )
        session.add(novo_devedor)
        session.commit()
        return True, f"Devedor '{nome}' adicionado com sucesso! ID: {novo_devedor.id}"
    except IntegrityError: # Captura erro de unicidade do DB se a validação inicial falhar por concorrência
        session.rollback()
        return False, f"Erro: Um devedor com o ID Pessoa '{pessoa_id}' já existe."
    except Exception as e:
        session.rollback()
        return False, f"Erro ao adicionar devedor: {e}"
    finally:
        session.close()

# Função para marcar como pago no banco de dados (Esta função será usada na página Cobrancas.py, mas manteremos aqui)
def marcar_como_pago_in_db(db_engine, devedor_id):
    session = get_session(db_engine)
    try:
        devedor = session.query(Devedor).filter_by(id=devedor_id).first()
        if devedor:
            devedor.status = StatusDevedor.PAGO
            devedor.data_pagamento = date.today()
            session.commit()
            return True, "Devedor marcado como pago!"
        else:
            return False, "Devedor não encontrado."
    except Exception as e:
        session.rollback()
        return False, f"Erro ao marcar como pago: {e}"
    finally:
        session.close()

# Função para remover devedor do banco de dados
def remover_devedor_from_db(db_engine, devedor_id):
    session = get_session(db_engine)
    try:
        devedor = session.query(Devedor).filter_by(id=devedor_id).first()
        if devedor:
            session.delete(devedor)
            session.commit()
            return True, "Devedor removido com sucesso!"
        else:
            return False, "Devedor não encontrado."
    except Exception as e:
        session.rollback()
        return False, f"Erro ao remover devedor: {e}"
    finally:
        session.close()

# Função para importar dados de um arquivo Excel para o banco de dados
def import_excel_to_db(db_engine, file):
    try:
        df_excel = pd.read_excel(file, engine='openpyxl')
        
        required_cols_excel = ['nome', 'valortotal', 'atraso', 'pessoa'] 
        
        if not all(col in df_excel.columns for col in required_cols_excel):
            return False, f"O arquivo Excel não contém todas as colunas obrigatórias para importação: {', '.join(required_cols_excel)}. Colunas encontradas: {list(df_excel.columns)}"

        session = get_session(db_engine)
        count_added = 0
        count_skipped = 0
        skipped_messages = [] 
        
        try:
            for index, row in df_excel.iterrows():
                pessoa_value = str(row['pessoa']) if 'pessoa' in row and pd.notna(row['pessoa']) else None
                
                if pessoa_value is None:
                    skipped_messages.append(f"Devedor '{row.get('nome', 'N/A')}' pulado: ID Pessoa não fornecido no Excel.")
                    count_skipped += 1
                    continue

                existing_devedor = session.query(Devedor).filter_by(pessoa=pessoa_value).first()
                if existing_devedor:
                    skipped_messages.append(f"Devedor '{row.get('nome', 'N/A')}' (ID Pessoa: {pessoa_value}) já existe. Pulado.")
                    count_skipped += 1
                    continue

                telefone_final = None
                if 'celular1' in row and pd.notna(row['celular1']):
                    telefone_final = str(row['celular1'])
                elif 'telefone' in row and pd.notna(row['telefone']):
                    telefone_final = str(row['telefone'])

                novo_devedor_excel = Devedor(
                    pessoa=pessoa_value,
                    nome=row.get('nome', 'N/A'),
                    valortotal=row.get('valortotal', 0.0),
                    atraso=row.get('atraso', 0),
                    telefone=telefone_final,
                    status=StatusDevedor.PENDENTE, # Novos devedores importados começam como Pendente
                    data_cobranca=None, # Não preenchido na importação, responsabilidade da tela de Cobranças
                    ultima_cobranca=None, # Não preenchido na importação, responsabilidade da tela de Cobranças
                    data_pagamento=None # Não preenchido na importação, responsabilidade da tela de Cobranças
                )
                session.add(novo_devedor_excel)
                count_added += 1
            session.commit()
            
            final_message = f"Importação concluída. Adicionados: {count_added} devedores. Pulados (já existentes ou sem ID Pessoa): {count_skipped}."
            if skipped_messages:
                final_message += "\n\nDetalhes dos devedores pulados (opcional):"
                for i, msg in enumerate(skipped_messages):
                    if i < 5: 
                        final_message += f"\n- {msg}"
                    else:
                        final_message += f"\n- E mais {len(skipped_messages) - 5} devedores..."
                        break

            return True, final_message
        except IntegrityError as e:
            session.rollback()
            return False, f"Erro de unicidade ao importar: Um devedor com o ID Pessoa já existe. Detalhes: {e}"
        except Exception as e:
            session.rollback()
            return False, f"Erro ao importar dados do Excel para o banco de dados: {e}"
        finally:
            session.close()
    except Exception as e:
        return False, f"Erro ao ler o arquivo Excel para importação: {e}"

# Função para exportar dados para um arquivo Excel
def export_devedores_to_excel(df_to_export):
    if df_to_export.empty:
        return None, "Nenhum dado para exportar."

    output = io.BytesIO()
    df_for_excel = df_to_export.copy()

    # Converte colunas de data para string formatada para evitar problemas no Excel
    # Manter todas as colunas de data que podem ser preenchidas por Cobrancas.py
    for col in ['data_cobranca', 'ultima_cobranca', 'data_pagamento']:
        if col in df_for_excel.columns and pd.api.types.is_datetime64_any_dtype(df_for_excel[col]):
            df_for_excel[col] = df_for_excel[col].dt.strftime('%Y-%m-%d')
        else:
            df_for_excel[col] = df_for_excel[col].astype(str) # Converte para string para não dar erro

    try:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_for_excel.to_excel(writer, index=False, sheet_name='Devedores')
        output.seek(0)
        return output.getvalue(), "Dados exportados com sucesso!"
    except Exception as e:
        return None, f"Erro ao exportar dados para Excel: {e}"

# Nova função para agendar cobrança (será usada em Cobrancas.py)
def agendar_cobranca_in_db(db_engine, devedor_id, data_programada):
    session = get_session(db_engine)
    try:
        devedor = session.query(Devedor).filter_by(id=devedor_id).first()
        if devedor:
            devedor.data_cobranca = data_programada
            devedor.ultima_cobranca = date.today()
            if devedor.status != StatusDevedor.PAGO:
                devedor.status = StatusDevedor.AGENDADO
            session.commit()
            return True, "Cobrança agendada com sucesso!"
        else:
            return False, "Devedor não encontrado."
    except Exception as e:
        session.rollback()
        return False, f"Erro ao agendar cobrança: {e}"
    finally:
        session.close()