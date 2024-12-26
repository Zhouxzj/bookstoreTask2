import uuid
import json
import logging
from be.model import db_conn
from be.model import error

import time
import sys
import os
from datetime import datetime, timedelta
import schedule
import traceback
import psycopg2
from psycopg2 import sql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class Buyer(db_conn.dbConn):
    def __init__(self):
        super().__init__()

    def new_order(
        self, user_id: str, store_id: str, id_and_count: [(str, int)]
    ) -> (int, str, str):
        order_id = ""
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id) + (order_id,)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id) + (order_id,)

            uid = "{}_{}_{}".format(user_id, store_id, str(uuid.uuid1()))

            # # Start a transaction to ensure atomicity
            # self.conn.begin()

            for book_id, count in id_and_count:
                sql = """
                SELECT book->>'num' AS num, 
                       book->>'price' AS price
                FROM shopdb,
                     jsonb_array_elements(books) AS book
                WHERE shop_id = :store_id
                AND book->>'book_id' = :book_id;"""
                result = self.conn.execute(text(sql), {'store_id':store_id, 'book_id':book_id})

                row = result.fetchone()
                if row is None:
                    return error.error_non_exist_book_id(book_id) + (order_id,)

                stock_level = row[0]
                price = row[1]

                if int(stock_level) < count:
                    return error.error_stock_level_low(book_id) + (order_id,)

                sql = """
                UPDATE shopdb
                SET books = (
                    SELECT jsonb_agg(
                        CASE
                            WHEN book->>'book_id' = :book_id THEN
                                jsonb_set(book, '{num}', ( (book->>'num')::int - :num )::text::jsonb)
                            ELSE
                                book
                        END
                    )
                    FROM jsonb_array_elements(books) AS book
                )
                WHERE shop_id = :store_id;
                """
                result = self.conn.execute(text(sql),{'book_id': book_id, 'num': count, 'store_id': store_id})

                if result.rowcount == 0:
                    return error.error_stock_level_low(book_id) + (order_id,)

                # get owner info
                sql = """
                    select owner_id from shopdb where shop_id = :store_id;
                """
                result = self.conn.execute(text(sql), {'store_id': store_id})
                row = result.fetchone()
                owner_id = row[0]
                sql = """
                    select address from userdb where user_id = :user_id;
                """
                result = self.conn.execute(text(sql), {'user_id': owner_id})
                row = result.fetchone()
                owner_address = row[0]
                # get buyer info
                result = self.conn.execute(text(sql), {'user_id': user_id})
                row = result.fetchone()
                buyer_address = row[0]
                order_time = datetime.now().isoformat()

                new_order_u = {
                    "order_id": uid,
                    "store_id": store_id,
                    "book_id": book_id,
                    "num": count,
                    "state": "ordered",
                    "address": owner_address,
                    "order_time": order_time
                }

                sql = """
                    select address from userdb where user_id = :user_id;
                """
                result = self.conn.execute(text(sql), {'user_id': user_id})
                row = result.fetchone()
                address = row[0]
                new_order_s = {
                    "order_id": uid,
                    "buyer_id": user_id,
                    "book_id": book_id,
                    "count": count,
                    "address": address,
                    "state": "ordered",
                    "order_time": order_time
                }
                self.conn.execute(text(
                    """
                    UPDATE shopdb
                    SET orders = COALESCE(orders, '[]'::jsonb) || :new_order ::jsonb
                    WHERE shop_id = :store_id ;
                    """),
                    {'new_order': json.dumps(new_order_s), 'store_id': store_id}
                )

                self.conn.execute(text(
                    """
                    update userdb 
                    set orders = COALESCE(orders, '[]'::jsonb) || :new_order ::jsonb
                    where user_id = :user_id ;
                    """),
                    {'new_order':json.dumps(new_order_u), 'user_id': user_id}
                )

            self.conn.commit()
            order_id = uid
        except SQLAlchemyError as e:
            self.conn.rollback()
            print("PostgreSQL Error: " + str(e))
            return 528, "{}".format(str(e)), ""
        except Exception as e:
            self.conn.rollback()
            print("Error: " + str(e))
            logging.info("530, {}".format(str(e)))
            return 530, "{}".format(str(e)), ""
        return 200, "ok", order_id

    def payment(self, user_id: str, password: str, order_id: str) -> (int, str):
        conn = self.conn
        try:
            # # Start a transaction to ensure atomicity
            # self.conn.begin()

            # get user order info
            sql = """
            SELECT order_item, password, account
            FROM userdb,
            jsonb_array_elements(orders) AS order_item
            WHERE order_item->>'order_id' = :order_id AND user_id = :user_id;
            """
            result = self.conn.execute(text(sql), {'order_id': order_id, 'user_id':user_id})
            row = result.fetchone()
            if row is None:
                return error.error_invalid_order_id(order_id)
            if password != row[1]:
                return error.error_authorization_fail()

            shop_id = row[0]["store_id"]
            state_u = row[0]["state"]
            account = row[2]

            if not self.store_id_exist(shop_id):
                return error.error_non_exist_store_id(shop_id)
            if state_u != "ordered":
                return error.error_invalid_order_id(order_id)

            #get shop order info
            sql = """
            SELECT order_item
            FROM shopdb,
            jsonb_array_elements(orders) AS order_item
            WHERE order_item->>'order_id' = :order_id AND shop_id = :shop_id;
            """
            result = self.conn.execute(text(sql), {'order_id': order_id, 'shop_id': shop_id})
            row = result.fetchall()
            if row is None:
                return error.error_invalid_order_id(order_id)

            total_price = 0
            for r in row:
                buyer_id = r[0]["buyer_id"]
                if user_id != buyer_id:
                    return error.error_authorization_fail()
                count = r[0]["count"]
                book_id = r[0]["book_id"]
                state_s = r[0]["state"]
                if state_s != "ordered":
                    return error.error_invalid_order_id(order_id)

                sql = """
                SELECT book_item
                FROM shopdb,
                jsonb_array_elements(books) AS book_item
                WHERE book_item->>'book_id' = :book_id AND shop_id = :shop_id;
                """
                result = self.conn.execute(text(sql), {'book_id': book_id, 'shop_id': shop_id})
                row = result.fetchone()
                price = row[0]["price"]

                total_price += int(price) * int(count)

            if int(account) < total_price:
                return error.error_not_sufficient_funds(order_id)

            # update shop order
            sql = """
            UPDATE shopdb
            SET orders = (
                SELECT jsonb_agg(
                    CASE
                        WHEN "order"->>'order_id' = :order_id THEN
                            jsonb_set("order", '{state}', '"paid"')
                        ELSE
                            "order"
                    END
                )
                FROM jsonb_array_elements(orders) AS "order"
            )
            WHERE shop_id = :shop_id;
            """
            self.conn.execute(text(sql), {'order_id': order_id, 'shop_id': shop_id})

            # update user order
            sql = """
                UPDATE userdb
                SET orders = (
                    SELECT jsonb_agg(
                        CASE
                            WHEN "order"->>'order_id' = :order_id THEN
                                jsonb_set("order", '{state}', '"paid"')
                            ELSE
                                "order"
                        END
                    )
                    FROM jsonb_array_elements(orders) AS "order"
                )
                WHERE user_id = :user_id;
                """
            self.conn.execute(text(sql), {'order_id': order_id, 'user_id': user_id})

            # update user account
            sql = """
            UPDATE userdb
            SET account = account - :total
            WHERE user_id = :user_id;
            """
            self.conn.execute(text(sql), {'total': total_price, 'user_id': user_id})

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

    def add_funds(self, user_id, password, add_value) -> (int, str):
        try:
            # # Start a transaction to ensure atomicity
            # self.conn.begin()
            sql = """
            select password
            from userdb where user_id = :user_id;
            """
            result = self.conn.execute(text(sql), {'user_id': user_id})
            row = result.fetchone()
            if row is None:
                return error.error_authorization_fail()

            if row[0] != password:
                return error.error_authorization_fail()


            # update user account
            sql = """
                UPDATE userdb
                SET account = account + :add_value
                WHERE user_id = :user_id;
                """
            result = self.conn.execute(text(sql), {'add_value': add_value, 'user_id': user_id})
            if result.rowcount == 0:
                return error.error_non_exist_user_id(user_id)

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
    def search_books(self, user_id: str, password: str, keyword: str, store_id: str):
        try:
            # # Start a transaction to ensure atomicity
            # self.conn.begin()

            result = self.conn.execute(text("""
            select password from userdb where user_id = :user_id;
            """), {'user_id': user_id})
            row = result.fetchone()
            if row is None or row[0] != password:
                return error.error_authorization_fail()

            """
            搜索书籍，支持分页查询
            :param keyword: 搜索关键字
            :param store_id: 可选的商店ID，如果提供则限制在该商店内搜索
            :param page: 当前页码
            :param per_page: 每页显示的书籍数量
            :return: 包含结果列表和分页信息的字典
            """
            page = 1
            per_page = 10
            # 创建全文搜索查询，匹配 title, book_intro, author, content, author_intro 字段
            search_query = sql.SQL(
                "to_tsvector('english', title) || ' ' || "
                "to_tsvector('english', book_intro) || ' ' || "
                "to_tsvector('english', author) || ' ' || "
                "to_tsvector('english', content) || ' ' || "
                "to_tsvector('english', author_intro)"
            )

            # 使用 sql.Literal 来处理 keyword 参数
            ts_query = sql.SQL("to_tsquery('english', {})").format(sql.Literal(keyword))

            # 查询的基础部分
            query = sql.SQL("""
                        SELECT id, title, book_intro, author, content, author_intro
                        FROM bookdb
                        WHERE {} @@ {}
                    """).format(search_query, ts_query)

            # 分页
            offset = (page - 1) * per_page
            # 如果提供了 store_id，增加对商店中书籍ID的过滤
            if store_id:
                query += sql.SQL("""
                            AND book_id IN (
                                SELECT unnest(books)
                                FROM shopdb
                                WHERE shop_id = :store_id
                                LIMIT :per_page OFFSET :offset
                            )
                        """)

                ret = self.conn.execute(text(query), {'store_id': store_id, 'per_page': per_page, 'offset': offset})
            else:
                query += sql.SQL("""
                        LIMIT :per_page OFFSET :offset
                    """)

                ret = self.conn.execute(text(query), {'per_page': per_page, 'offset': offset})

            results = ret.fetchall()
            print("Books:", results)

            # 获取总数查询
            total_query = sql.SQL("""
                            SELECT COUNT(*)
                            FROM bookdb
                            WHERE {} @@ {}
                        """).format(search_query, ts_query)

            # 如果 store_id 存在，添加商店过滤
            if store_id:
                total_query += sql.SQL("""
                                AND book_id IN (
                                    SELECT unnest(books)
                                    FROM shopdb
                                    WHERE shop_id = :store_id
                                )
                            """)

                ret = self.conn.execute(text(total_query), {'store_id': store_id})
            else:
                ret = self.conn.execute(text(total_query))

            total_count = ret.fetchone()[0]  # 获取总数

            # 这一段可以返回搜索结果和分页信息
            # 返回结果
            # return {
            #     'books': results,
            #     'total_count': total_count,
            #     'page': page,
            #     'per_page': per_page
            # }
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

    def receive(self, user_id: str, order_id: str):
        try:
            # # Start a transaction to ensure atomicity
            # self.conn.begin()

            # check userdb info is right or not
            result = self.conn.execute(text("""
            SELECT order_item
            FROM userdb, jsonb_array_elements(orders) AS order_item
            WHERE order_item->>'order_id' = :order_id AND user_id = :user_id;
            """), {'order_id': order_id, 'user_id': user_id})
            row = result.fetchone()
            if row is None:
                return error.error_non_exist_user_id(user_id)

            if row[0]["state"] != "delivered":
                return error.error_invalid_order_id(order_id)

            # check shopdb info is right or not
            shop_id = row[0]["store_id"]
            result = self.conn.execute(text("""
            select order_item
            from shopdb, jsonb_array_elements(orders) as order_item
            where order_item->>'order_id' = :order_id and shop_id = :shop_id;
            """), {'order_id': order_id, 'shop_id': shop_id})
            row = result.fetchone()
            if row is None or row[0]["state"] != "delivered":
                return error.error_invalid_order_id(order_id)

            # update the userdb info
            sql = """
            UPDATE userdb
            SET orders = (
                SELECT jsonb_agg(
                    CASE
                        WHEN "order"->>'order_id' = :order_id THEN
                            jsonb_set("order", '{state}', '"received"')
                        ELSE
                            "order"
                    END
                )
                FROM jsonb_array_elements(orders) AS "order"
            )
            WHERE user_id = :user_id;
            """
            result = self.conn.execute(text(sql), {'order_id': order_id, 'user_id': user_id})
            if result.rowcount == 0:
                return error.error_update_order_failure(order_id)

            # update the shopdb info
            sql = """
            UPDATE shopdb
            SET orders = (
                SELECT jsonb_agg(
                    CASE
                        WHEN "order"->>'order_id' = :order_id THEN
                            jsonb_set("order", '{state}', '"received"')
                        ELSE
                            "order"
                    END
                )
                FROM jsonb_array_elements(orders) AS "order"
            )
            WHERE shop_id = :shop_id;
            """
            result = self.conn.execute(text(sql), {'order_id': order_id, 'shop_id': shop_id})
            if result.rowcount == 0:
                return error.error_update_order_failure(order_id)
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

    def search_history_order(self, user_id: str, password: str):
        try:
            # # Start a transaction to ensure atomicity
            # self.conn.begin()

            # check authorization
            result = self.conn.execute(text("""
            select password from userdb where user_id = :user_id;
            """), {'user_id':user_id})
            row = result.fetchone()
            if row is None:
                return error.error_non_exist_user_id(user_id)

            if password != row[0]:
                return error.error_authorization_fail()

            # get history order
            sql = """
            SELECT order_item
            FROM userdb, jsonb_array_elements(orders) AS order_item
            WHERE user_id = :user_id AND order_item->>'state' = 'received';
            """
            result = self.conn.execute(text(sql), {'user_id': user_id})
            history_order = result.fetchall()
            if history_order is None:
                return error.error_not_find_history_order(user_id)
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

    def buyer_cancel_order(self, user_id: str, order_id: str):
        try:
            # # Start a transaction to ensure atomicity
            # self.conn.begin()

            # check userdb info
            result = self.conn.execute(text("""
            select order_item from userdb, 
            jsonb_array_elements(orders) as order_item
            where order_item->>'order_id' = :order_id and user_id = :user_id;
            """), {'order_id': order_id, 'user_id': user_id})
            row = result.fetchone()
            if row is None:
                return error.error_non_exist_user_id(user_id)
            if row[0]["state"] != "ordered":
                return error.error_invalid_order_id(order_id)
            shop_id = row[0]["store_id"]

            # check shopdb info
            result = self.conn.execute(text("""
            select order_item from shopdb,
            jsonb_array_elements(orders) as order_item
            where order_item->>'order_id' = :order_id and shop_id = :shop_id;
            """), {'order_id': order_id, 'shop_id': shop_id})
            row = result.fetchone()
            if row is None or row[0]["state"] != "ordered":
                return error.error_invalid_order_id(order_id)

            # delete order in shopdb
            sql = """
            UPDATE shopdb
            SET orders = (
            SELECT jsonb_agg("order")
            FROM jsonb_array_elements(orders) AS "order"
            WHERE "order"->>'order_id' != :order_id  
            )
            WHERE shop_id = :shop_id; 
            """
            result = self.conn.execute(text(sql), {'order_id': order_id, 'shop_id': shop_id})
            if result.rowcount == 0:
                return error.error_update_order_failure(order_id)

            # delete order in userdb
            sql = """
            UPDATE userdb
            SET orders = (
            SELECT jsonb_agg("order")
            FROM jsonb_array_elements(orders) AS "order"
            WHERE "order"->>'order_id' != :order_id  
            )
            WHERE user_id = :user_id; 
            """
            result = self.conn.execute(text(sql), {'order_id': order_id, 'user_id': user_id})
            if result.rowcount == 0:
                return error.error_update_order_failure(order_id)

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

    def filter_orders_by_time(self, store):
        for item in store:
            if item is None:
                return False

        time = store[2]
        current_time = datetime.now()
        order_time = datetime.fromisoformat(time)
        if (current_time - order_time) > timedelta(seconds=10):
            return True

    def auto_cancel_order(self):
        try:
            # # Start a transaction to ensure atomicity
            # self.conn.begin()

            # get all order whose state is "ordered"
            sql = """
            SELECT 
                shop_id,
                "order"->>'order_id' AS order_id,
                "order"->>'order_time' AS order_time,
                "order"->>'buyer_id' AS buyer_id
            FROM 
                shopdb,
                jsonb_array_elements(orders) AS "order"
            WHERE 
                "order"->>'state' != 'ordered';
            """
            result = self.conn.execute(text(sql))
            shop_data = result.fetchall()
            for shop_item in shop_data:
                result = self.filter_orders_by_time(shop_item)

                if result is False:
                    continue
                else:
                    # auto delete order in shopdb
                    sql = """
                        UPDATE shopdb
                        SET orders = (
                        SELECT jsonb_agg("order")
                        FROM jsonb_array_elements(orders) AS "order"
                        WHERE "order"->>'order_id' != :order_id  
                        )
                        WHERE shop_id = :shop_id; 
                        """
                    result = self.conn.execute(text(sql), {'order_id': shop_item[1], 'shop_id': shop_item[0]})
                    if result.rowcount == 0:
                        return error.error_cancel_order_fail()

                    # auto delete order in userdb
                    sql = """
                        UPDATE userdb
                        SET orders = (
                        SELECT jsonb_agg("order")
                        FROM jsonb_array_elements(orders) AS "order"
                        WHERE "order"->>'order_id' != :order_id  
                        )
                        WHERE user_id = :user_id; 
                        """
                    result = self.conn.execute(text(sql), {'order_id': shop_item[1], 'user_id': shop_item[3]})

                    # if result.rowcount == 0:
                    #     return error.error_cancel_order_fail()
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

    def auto_exe_cancel(self):
        while True:
            self.auto_cancel_order()
            time.sleep(10)

