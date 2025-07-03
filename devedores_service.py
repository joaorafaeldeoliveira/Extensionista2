# devedores_service.py
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func, and_, or_
from datetime import datetime, date, timedelta
import calendar
import pandas as pd

# Presume-se que Devedor e StatusDevedor são importados de database.py
try:
    from database import Devedor, StatusDevedor
except ImportError:
    # Fallback para execução independente ou testes, se necessário
    print("Aviso: Não foi possível importar Devedor e StatusDevedor de database.py. Certifique-se de que database.py está acessível.")
    # Definições mock para permitir que o arquivo seja lido sem erro imediato
    class StatusDevedor:
        AGENDADO = "Agendado"
        PENDENTE = "Pendente"
        PAGO = "Pago"
    class Devedor:
        pass # Apenas para evitar NameError, a funcionalidade real requer a classe completa

# --- Funções Auxiliares ---
def calculate_next_business_day(start_date: date, num_days: int) -> date:
    """
    Calcula uma data futura pulando fins de semana.
    Args:
        start_date (date): A data inicial para o cálculo.
        num_days (int): O número de dias úteis a adicionar.
    Returns:
        date: A data resultante após adicionar os dias úteis.
    """
    current_date = start_date
    business_days_added = 0
    while business_days_added < num_days:
        current_date += timedelta(days=1)
        # weekday() retorna 0 para segunda-feira e 6 para domingo
        if current_date.weekday() < 5:  # Verifica se é um dia de semana (segunda a sexta)
            business_days_added += 1
    return current_date

# --- Funções de Serviço de Banco de Dados ---

def marcar_cobranca_feita_e_reagendar_in_db(engine, devedor_id: int, nova_data: date = None):
    """
    Marca uma cobrança como feita e reagenda a próxima cobrança.
    Se 'nova_data' não for fornecida, reagenda automaticamente para 10 dias úteis.
    Args:
        engine: O objeto engine do SQLAlchemy.
        devedor_id (int): O ID do devedor.
        nova_data (date, optional): A data para reagendar a cobrança.
                                     Se None, calcula 10 dias úteis.
    Returns:
        tuple: (bool, str) - Sucesso da operação e mensagem.
    """
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        devedor = session.query(Devedor).filter_by(id=devedor_id).first()
        if not devedor:
            return False, "Devedor não encontrado."

        devedor.ultima_cobranca = datetime.now()
        # Garante que a fase da cobrança cicla entre 1, 2 e 3
        devedor.fase_cobranca = (devedor.fase_cobranca % 3) + 1

        if nova_data:
            # Se uma nova data foi fornecida (agendamento manual)
            devedor.data_cobranca = nova_data
            msg = f"Cobrança para {devedor.nome} marcada manualmente para {nova_data.strftime('%d/%m/%Y')}."
        else:
            # Se não foi fornecida (botão 'Cobrança Feita'), calcula 10 dias úteis
            proxima_data_cobranca = calculate_next_business_day(date.today(), 10)
            devedor.data_cobranca = proxima_data_cobranca
            msg = f"Cobrança para {devedor.nome} marcada como feita e reagendada para {proxima_data_cobranca.strftime('%d/%m/%Y')} (10 dias úteis)."

        devedor.status = StatusDevedor.AGENDADO.value # O status sempre será "Agendado" após uma cobrança feita/reagendada
        session.commit()
        return True, msg
    except Exception as e:
        session.rollback()
        return False, f"Erro ao marcar cobrança e reagendar: {e}"
    finally:
        session.close()

def marcar_como_pago_in_db(engine, devedor_id: int):
    """
    Marca um devedor como pago.
    Args:
        engine: O objeto engine do SQLAlchemy.
        devedor_id (int): O ID do devedor.
    Returns:
        tuple: (bool, str) - Sucesso da operação e mensagem.
    """
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        devedor = session.query(Devedor).filter_by(id=devedor_id).first()
        if not devedor:
            return False, "Devedor não encontrado."
        
        devedor.status = StatusDevedor.PAGO.value
        devedor.data_pagamento = date.today()
        devedor.data_cobranca = None # Remove a próxima data de cobrança
        session.commit()
        return True, f"Devedor {devedor.nome} marcado como PAGO."
    except Exception as e:
        session.rollback()
        return False, f"Erro ao marcar como pago: {e}"
    finally:
        session.close()

def remover_devedor_from_db(engine, devedor_id: int):
    """
    Remove um devedor do banco de dados.
    Args:
        engine: O objeto engine do SQLAlchemy.
        devedor_id (int): O ID do devedor.
    Returns:
        tuple: (bool, str) - Sucesso da operação e mensagem.
    """
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        devedor = session.query(Devedor).filter_by(id=devedor_id).first()
        if not devedor:
            return False, "Devedor não encontrado."
        
        session.delete(devedor)
        session.commit()
        return True, f"Devedor {devedor.nome} removido com sucesso."
    except Exception as e:
        session.rollback()
        return False, f"Erro ao remover devedor: {e}"
    finally:
        session.close()

def get_devedores_para_acoes_count(engine, filtro_nome: str = None):
    """
    Retorna a contagem de devedores que requerem ação imediata.
    Args:
        engine: O objeto engine do SQLAlchemy.
        filtro_nome (str, optional): Filtra por nome do devedor.
    Returns:
        int: Número total de devedores que requerem ação.
    """
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        # Devedores que requerem ação:
        # - Status PENDENTE
        # - Status AGENDADO e data_cobranca é hoje ou no passado
        query = session.query(Devedor).filter(
            or_(
                Devedor.status == StatusDevedor.PENDENTE.value,
                and_(
                    Devedor.status == StatusDevedor.AGENDADO.value,
                    Devedor.data_cobranca <= date.today()
                )
            )
        )
        if filtro_nome:
            query = query.filter(Devedor.nome.ilike(f"%{filtro_nome}%"))
        return query.count()
    finally:
        session.close()

def get_devedores_para_acoes_paginated(engine, page: int, page_size: int, sort_column: str, sort_ascending: bool, filtro_nome: str = None):
    """
    Retorna devedores que requerem ação imediata, com paginação e ordenação.
    Args:
        engine: O objeto engine do SQLAlchemy.
        page (int): O número da página (base 0).
        page_size (int): O número de itens por página.
        sort_column (str): A coluna para ordenar.
        sort_ascending (bool): True para ascendente, False para descendente.
        filtro_nome (str, optional): Filtra por nome do devedor.
    Returns:
        pd.DataFrame: DataFrame dos devedores.
    """
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        query = session.query(Devedor).filter(
            or_(
                Devedor.status == StatusDevedor.PENDENTE.value,
                and_(
                    Devedor.status == StatusDevedor.AGENDADO.value,
                    Devedor.data_cobranca <= date.today()
                )
            )
        )
        if filtro_nome:
            query = query.filter(Devedor.nome.ilike(f"%{filtro_nome}%"))

        # Aplica ordenação
        if sort_ascending:
            query = query.order_by(getattr(Devedor, sort_column))
        else:
            query = query.order_by(getattr(Devedor, sort_column).desc())

        # Aplica paginação
        query = query.offset(page * page_size).limit(page_size)
        
        devedores = query.all()
        df = pd.DataFrame([d.__dict__ for d in devedores])
        if '_sa_instance_state' in df.columns:
            df = df.drop(columns=['_sa_instance_state'])
        return df
    finally:
        session.close()

def load_devedores_from_db(engine):
    """
    Carrega todos os devedores do banco de dados.
    Args:
        engine: O objeto engine do SQLAlchemy.
    Returns:
        pd.DataFrame: DataFrame de todos os devedores.
    """
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        devedores = session.query(Devedor).all()
        df = pd.DataFrame([d.__dict__ for d in devedores])
        if '_sa_instance_state' in df.columns:
            df = df.drop(columns=['_sa_instance_state'])
        return df
    finally:
        session.close()

def get_devedores_para_dia_count(engine, selected_date: date):
    """
    Retorna a contagem de devedores agendados para uma data específica.
    Args:
        engine: O objeto engine do SQLAlchemy.
        selected_date (date): A data para verificar os agendamentos.
    Returns:
        int: Número total de devedores agendados para a data.
    """
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        return session.query(Devedor).filter(
            and_(
                Devedor.status == StatusDevedor.AGENDADO.value,
                func.date(Devedor.data_cobranca) == selected_date
            )
        ).count()
    finally:
        session.close()

def get_devedores_para_dia_paginated(engine, selected_date: date, page: int, page_size: int):
    """
    Retorna devedores agendados para uma data específica, com paginação.
    Args:
        engine: O objeto engine do SQLAlchemy.
        selected_date (date): A data para verificar os agendamentos.
        page (int): O número da página (base 0).
        page_size (int): O número de itens por página.
    Returns:
        pd.DataFrame: DataFrame dos devedores agendados para a data.
    """
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        query = session.query(Devedor).filter(
            and_(
                Devedor.status == StatusDevedor.AGENDADO.value,
                func.date(Devedor.data_cobranca) == selected_date
            )
        )
        # Ordena para garantir consistência na paginação
        query = query.order_by(Devedor.data_cobranca, Devedor.nome)
        
        # Aplica paginação
        query = query.offset(page * page_size).limit(page_size)
        
        devedores = query.all()
        df = pd.DataFrame([d.__dict__ for d in devedores])
        if '_sa_instance_state' in df.columns:
            df = df.drop(columns=['_sa_instance_state'])
        return df
    finally:
        session.close()