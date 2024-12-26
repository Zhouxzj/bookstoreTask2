import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from be.model import error
from be.model import db_conn

import json
import logging
import traceback
import psycopg2
from psycopg2 import sql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

class Seller(db_conn.dbConn):
    def __init__(self):
        super().__init__()

    def add_book(
        self,
        user_id: str,
        store_id: str,
        book_id: str,
        book_json_str: str,
        stock_level: int,
    ):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)
            if self.book_id_exist(store_id, book_id):
                return error.error_exist_book_id(book_id)

            # # Start a transaction to ensure atomicity
            # self.conn.begin()

            sql = """
            select owner_id from shopdb where shop_id = :store_id;
            """
            result = self.conn.execute(text(sql), {'store_id': store_id})
            row = result.fetchone()

            if row is None or row[0] != user_id:
                return error.error_authorization_fail()

            book_dict = json.loads(book_json_str)
            book_data = {
                'id': None,
                'title': None,
                'author': None,
                'publisher': None,
                'original_title': None,
                'translator': None,
                'pub_year': None,
                'pages': None,
                'price': None,
                'currency_unit': None,
                'binding': None,
                'isbn': None,
                'author_intro': None,
                'book_intro': None,
                'content': None,
                'tags': None,
            }

            price = None
            book_info = None

            for key in book_data.keys():
                if key in book_dict:
                    book_data[key] = book_dict[key]
                    if key == "price":
                        price = book_data[key]
                    if key == "book_intro":
                        book_info = book_data[key]

            sql = text("""
                INSERT INTO bookdb (id, title, author, publisher, original_title, translator, pub_year, pages, price, 
                                    currency_unit, binding, isbn, author_intro, book_intro, content, tags)
                VALUES (:id, :title, :author, :publisher, :original_title, :translator, :pub_year, :pages, :price, 
                        :currency_unit, :binding, :isbn, :author_intro, :book_intro, :content, :tags)
                ON CONFLICT(id) DO NOTHING;
            """)
            self.conn.execute(sql, book_data)

            new_book = {
                "book_id": book_id,
                "num" : stock_level,
                "price" : price,
                "book_info" : book_info
            }

            new_book_json = json.dumps(new_book)

            self.conn.execute(text(
                """
                UPDATE shopdb
                SET books = COALESCE(books, '[]'::jsonb) || :new_book ::jsonb
                WHERE shop_id = :store_id;
                """),
                {'new_book': new_book_json, 'store_id': store_id}
            )

            self.conn.commit()
        except SQLAlchemyError as e:
            self.conn.rollback()
            print("PostgreSQL Error: " + str(e))
            return 528, "{}".format(str(e)), ""
        except Exception as e:
            self.conn.rollback()
            print("Error: " + str(e))
            logging.info("530, {}".format(str(e)))
            return 530, "{}".format(str(e)), ""
        return 200, "ok"

    def add_stock_level(
        self, user_id: str, store_id: str, book_id: str, add_stock_level: int
    ):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)
            if not self.book_id_exist(store_id, book_id):
                return error.error_non_exist_book_id(book_id)

            # # Start a transaction to ensure atomicity
            # self.conn.begin()

            sql = text("""
            select owner_id from shopdb where shop_id = :store_id;
            """)
            result = self.conn.execute(sql, {'store_id': store_id})
            row = result.fetchone()
            owner_id = row[0]
            if owner_id != user_id:
                return error.error_authorization_fail()

            sql = text("""
            UPDATE shopdb
            SET books = (
                SELECT jsonb_agg(
                    CASE
                        WHEN book->>'book_id' = :book_id THEN
                            jsonb_set(book, '{num}', ( (book->>'num')::int + :add_stock )::text::jsonb)
                        ELSE
                            book
                    END
                )
                FROM jsonb_array_elements(books) AS book
            )
            WHERE shop_id = :store_id;
            """)
            self.conn.execute(sql,
                    {'book_id': book_id, 'add_stock': add_stock_level, 'store_id': store_id})

            self.conn.commit()
        except SQLAlchemyError as e:
            self.conn.rollback()
            print("PostgreSQL Error: " + str(e))
            return 528, "{}".format(str(e)), ""
        except Exception as e:
            self.conn.rollback()
            print("Error: " + str(e))
            logging.info("530, {}".format(str(e)))
            return 530, "{}".format(str(e)), ""

        return 200, "ok"

    def create_store(self, user_id: str, store_id: str) -> (int, str):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if self.store_id_exist(store_id):
                return error.error_exist_store_id(store_id)

            # # Start a transaction to ensure atomicity
            # self.conn.begin()

            result = self.conn.execute(text("""
            select password from userdb where user_id = :user_id;
            """),{'user_id': user_id})
            row = result.fetchone()
            if row is None:
                return error.error_non_exist_user_id(user_id)

            password = row[0]
            books = None
            orders =  None

            sql = """
                INSERT INTO shopdb (shop_id, owner_id, password, books, orders)
                VALUES (:store_id, :user_id, :password, :books, :orders);
            """

            self.conn.execute(
                text(sql),
                {'store_id': store_id, 'user_id': user_id, 'password': password, 'books': books, 'orders': orders}
            )

            self.conn.commit()
        except SQLAlchemyError as e:
            self.conn.rollback()
            print("PostgreSQL Error: " + str(e))
            return 528, "{}".format(str(e)), ""
        except Exception as e:
            self.conn.rollback()
            print("Error: " + str(e))
            logging.info("530, {}".format(str(e)))
            return 530, "{}".format(str(e)), ""

        return 200, "ok"

    # 40%
    def deliver(self, store_id: str, order_id: str) -> (int, str):
        try:
            # # Start a transaction to ensure atomicity
            # self.conn.begin()

            # whether this store exists
            result = self.conn.execute(text("""
            select * from shopdb where shop_id = :store_id;
            """), {'store_id': store_id})
            store = result.fetchone()
            if store is None:
                return error.error_non_exist_store_id(store_id)

            # whether the order is paid in shopdb
            sql = text("""
                SELECT order_item
                FROM shopdb,
                jsonb_array_elements(orders) AS order_item
                WHERE order_item->>'order_id' = :order_id AND shop_id = :store_id;
                """)
            result = self.conn.execute(sql, {'order_id': order_id, 'store_id': store_id})
            row = result.fetchone()
            if row is None:
                return error.error_invalid_order_id(order_id)
            buyer_id = row[0]["buyer_id"]
            state_s = row[0]["state"]
            if state_s != "paid":
                return error.error_invalid_order_id(order_id)

            #whether the order is paid in userdb
            sql = """
            select order_item from userdb,
            jsonb_array_elements(orders) as order_item
            where order_item->>'order_id' = :order_id and user_id = :user_id;
            """
            result = self.conn.execute(text(sql), {'order_id': order_id, 'user_id': buyer_id})
            row = result.fetchone()
            if row is None or row[0]["state"] != "paid":
                return error.error_invalid_order_id(order_id)

            # update the shopdb order state
            sql = """
                UPDATE shopdb
                SET orders = (
                    SELECT jsonb_agg(
                        CASE
                            WHEN "order"->>'order_id' = :order_id THEN
                                jsonb_set("order", '{state}', '"delivered"')
                            ELSE
                                "order"
                        END
                    )
                    FROM jsonb_array_elements(orders) AS "order"
                )
                WHERE shop_id = :store_id;
                """
            result = self.conn.execute(text(sql), {'order_id': order_id, 'store_id': store_id})
            if result.rowcount == 0:
                return error.error_invalid_order_id(order_id)

            # update the userdb order stat
            sql = """
                UPDATE userdb
                SET orders = (
                    SELECT jsonb_agg(
                        CASE
                            WHEN "order"->>'order_id' = :order_id THEN
                                jsonb_set("order", '{state}', '"delivered"')
                            ELSE
                                "order"
                        END
                    )
                    FROM jsonb_array_elements(orders) AS "order"
                )
                WHERE user_id = :user_id;
                """
            result = self.conn.execute(text(sql),
                            {'order_id': order_id, 'user_id': buyer_id})
            if result.rowcount == 0:
                return error.error_invalid_order_id(order_id)

            self.conn.commit()
        except SQLAlchemyError as e:
            self.conn.rollback()
            print("PostgreSQL Error: "+ str(e))
            return 528, "{}".format(str(e)), ""
        except Exception as e:
            self.conn.rollback()
            print("Error: " + str(e))
            logging.info("530, {}".format(str(e)))
            return 530, "{}".format(str(e)), ""

        return 200, "ok"
