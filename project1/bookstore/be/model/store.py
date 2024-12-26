import logging
import os
import threading
import psycopg2
from psycopg2 import sql
from sqlalchemy import create_engine,MetaData
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

class Store:
    database: str

    def __init__(self, db_path):
        # 连接 PostgreSQL 数据库
        self.engine = create_engine('postgresql://postgres:123456@127.0.0.1:5432/postgres')  # 本地服务器
        self.init_tables()

    def init_tables(self):
        try:
            conn = self.get_db_conn()
            conn.execute(
                text('''
                    CREATE TABLE IF NOT EXISTS bookdb (
                    id TEXT primary key,
                    title TEXT,
                    author TEXT,
                    publisher TEXT,
                    original_title TEXT,
                    translator TEXT,
                    pub_year TEXT,
                    pages INTEGER,
                    price INTEGER,
                    currency_unit TEXT,
                    binding TEXT,
                    isbn TEXT,
                    author_intro TEXT,
                    book_intro text,
                    content TEXT,
                    tags TEXT
                    );
                ''')
            )

            conn.execute(
                text('''
                CREATE TABLE userdb (
                id SERIAL PRIMARY KEY,          -- 用户 ID，自增主键
                user_id TEXT NOT NULL ,
                password TEXT NOT NULL,         -- 密码
                token TEXT,                     -- Token
                terminal TEXT,                  -- 终端信息
                account INTEGER NOT NULL,          -- 账户余额
                address TEXT,                   -- 地址
                shops JSONB,                     -- 多个 shop.id
                orders JSONB 
                );
            ''')
            )

            conn.execute(
                text('''
                CREATE TABLE shopdb (
                id SERIAL PRIMARY KEY,          -- 用户 ID，自增主键
                shop_id TEXT NOT NULL ,
                owner_id TEXT NOT NULL ,
                password TEXT NOT NULL ,
                books JSONB,
                orders JSONB  
                ); 
                ''')
            )

            conn.commit()
        except SQLAlchemyError as e:
            logging.error(e)
            conn.rollback()



    def get_db_conn(self):
        self.Base = declarative_base()
        self.metadata = MetaData()
        self.dbSession = sessionmaker(bind=self.engine)
        self.conn = self.dbSession()
        return self.conn


# 全局变量，确保只有一个数据库实例
database_instance: Store = None
# 用于通知数据库初始化完成
init_completed_event = threading.Event()


def init_database(db_path):
    global database_instance
    database_instance = Store(db_path)


def get_db_conn():
    global database_instance
    return database_instance.get_db_conn()
