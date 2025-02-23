from sqlalchemy import create_engine, Column, Integer, String, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    weight = Column(Integer)
    height = Column(Integer)
    goal = Column(String)
    training_days = Column(String)
    start_time = Column(String)

class Program(Base):
    __tablename__ = 'programs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)  # Разрешаем NULL для общей программы
    day = Column(Integer)
    intensity = Column(String)
    program_data = Column(JSON)

class Progress(Base):
    __tablename__ = 'progress'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)  # ID пользователя
    date = Column(String)  # Дата тренировки
    exercise = Column(String)  # Название упражнения
    reps = Column(Integer)  # Количество повторений
    weight = Column(Integer)  # Используемый вес

# Создание базы данных
engine = create_engine('sqlite:///client_bot.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()