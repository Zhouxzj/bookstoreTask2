from be.model import store
import psycopg2
import sys
import os
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class dbConn:
    def __init__(self):
        self.conn = store.get_db_conn()

    def user_id_exist(self, user_id):
        result = self.conn.execute(
            text("SELECT * FROM userdb WHERE user_id = :user_id;"), {'user_id': user_id}
        )

        row = result.fetchone()
        if row is None:
            return False
        else:
            return True

    def book_id_exist(self, store_id, book_id):
        result = self.conn.execute(text(
            """
            SELECT *
            FROM shopdb
            WHERE shop_id = :store_id
            AND EXISTS (
                SELECT *
                FROM jsonb_array_elements(books) AS book
                WHERE book->>'book_id' = :book_id
            );
            """),
            {'store_id': store_id, 'book_id': book_id}
        )
        row = result.fetchone()
        if row is None:
            return False
        else:
            return True

    def store_id_exist(self, store_id):
        result = self.conn.execute(text(
            "SELECT * FROM shopdb WHERE shop_id = :store_id;"), {'store_id': store_id}
        )
        row = result.fetchone()
        if row is None:
            return False
        else:
            return True
