# database.py
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Enum
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import enum

# Definição do Enum para StatusDevedor
class StatusDevedor(enum.Enum):
    PENDENTE = "Pendente"
    AGENDADO = "Agendado"
    PAGO = "Pago"

Base = declarative_base()

class Devedor(Base):
    __tablename__ = 'devedores'

    id = Column(Integer, primary_key=True, autoincrement=True)
    pessoa = Column(String, unique=True, nullable=True) 
    nome = Column(String, nullable=False)
    valortotal = Column(Float, nullable=False)
    atraso = Column(Integer, nullable=False)
    telefone = Column(String, nullable=True)
    data_cobranca = Column(DateTime, nullable=True)
    ultima_cobranca = Column(DateTime, nullable=True)
    status = Column(Enum(StatusDevedor), default=StatusDevedor.PENDENTE, nullable=False)
    data_pagamento = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Devedor(id={self.id}, pessoa='{self.pessoa}', nome='{self.nome}', valortotal={self.valortotal})>"

def init_db():
    engine = create_engine('sqlite:///cobrancas.db')
    Base.metadata.create_all(engine)
    return engine

def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()