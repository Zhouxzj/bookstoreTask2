import jwt
import time
import logging
import sqlite3 as sqlite
from be.model import error
from be.model import db_conn

import uuid
import json
import traceback
import psycopg2
from psycopg2 import sql, errors
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

# encode a json string like:
#   {
#       "user_id": [user name],
#       "terminal": [terminal code],
#       "timestamp": [ts]} to a JWT
#   }


def jwt_encode(user_id: str, terminal: str) -> str:
    encoded = jwt.encode(
        {"user_id": user_id, "terminal": terminal, "timestamp": time.time()},
        key=user_id,
        algorithm="HS256",
    )
    return encoded


# decode a JWT to a json string like:
#   {
#       "user_id": [user name],
#       "terminal": [terminal code],
#       "timestamp": [ts]} to a JWT
#   }
def jwt_decode(encoded_token, user_id: str) -> str:
    decoded = jwt.decode(encoded_token, key=user_id, algorithms="HS256")
    return decoded


class User(db_conn.dbConn):
    token_lifetime: int = 3600  # 3600 second

    def __init__(self):
        super().__init__()

    def __check_token(self, user_id, db_token, token) -> bool:
        try:
            if db_token != token:
                return False
            jwt_text = jwt_decode(encoded_token=token, user_id=user_id)
            ts = jwt_text["timestamp"]
            if ts is not None:
                now = time.time()
                if self.token_lifetime > now - ts >= 0:
                    return True
        except jwt.exceptions.InvalidSignatureError as e:
            logging.error(str(e))
            return False

    def register(self, user_id: str, password: str):
        try:
            terminal = "terminal_{}".format(str(time.time()))
            token = jwt_encode(user_id, terminal)

            account = 0
            address = None
            shops = None
            orders = None
            sql = """
            select * from userdb where user_id = :user_id;
            """
            result = self.conn.execute(text(sql), {'user_id': user_id})
            row = result.fetchone()

            if row is not None:
                return error.error_exist_user_id(user_id)

            self.conn.execute(text("""
                INSERT into userdb (user_id, password, token, terminal, account, address, shops, orders) 
                VALUES (:user_id, :password, :token, :terminal, :account, :address, :shops, :orders)
                """) , {
            'user_id': user_id,
            'password': password,
            'token': token,
            'terminal': terminal,
            'account': account,
            'address': address,
            'shops': shops,
            'orders': orders
        })

            self.conn.commit()
        except SQLAlchemyError as e:
            self.conn.rollback()
            print("PostgreSQL Error: " + str(e))
            return 528, "{}".format(str(e)), ""
        return 200, "ok"

    def check_token(self, user_id: str, token: str) -> (int, str):
        result = self.conn.execute(text("""SELECT token from userdb where user_id = :user_id;"""),
                          {'user_id': user_id})
        row = result.fetchone()
        if row is None:
            return error.error_authorization_fail()
        db_token = row[0]
        if not self.__check_token(user_id, db_token, token):
            return error.error_authorization_fail()
        return 200, "ok"

    def check_password(self, user_id: str, password: str) -> (int, str):
        result = self.conn.execute(text("""SELECT password from userdb where user_id = :user_id;"""),
                          {'user_id': user_id})
        row = result.fetchone()
        if row is None:
            return error.error_authorization_fail()

        if password != row[0]:
            return error.error_authorization_fail()

        return 200, "ok"

    def login(self, user_id: str, password: str, terminal: str) -> (int, str, str):
        token = ""
        try:
            code, message = self.check_password(user_id, password)
            if code != 200:
                return code, message, ""

            # # Start a transaction to ensure atomicity
            # self.conn.begin()
            token = jwt_encode(user_id, terminal)
            sql = """
            UPDATE userdb 
            SET token = :token, terminal = :terminal 
            WHERE user_id = :user_id;
            """
            result = self.conn.execute(text(sql),{'token': token, 'terminal': terminal, 'user_id': user_id})

            if result.rowcount == 0:
                return error.error_authorization_fail() + ("",)
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

        return 200, "ok", token

    def logout(self, user_id: str, token: str) -> bool:
        try:
            code, message = self.check_token(user_id, token)
            if code != 200:
                return code, message

            # # Start a transaction to ensure atomicity
            # self.conn.begin()
            terminal = "terminal_{}".format(str(time.time()))
            dummy_token = jwt_encode(user_id, terminal)

            sql = """
            UPDATE userdb 
            SET token = :token, terminal = :terminal 
            WHERE user_id = :user_id;
            """
            result = self.conn.execute(text(sql),{'token': dummy_token, 'terminal': terminal, 'user_id': user_id})

            if result.rowcount == 0:
                return error.error_authorization_fail()

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

    def unregister(self, user_id: str, password: str) -> (int, str):
        try:
            code, message = self.check_password(user_id, password)
            if code != 200:
                return code, message

            # # Start a transaction to ensure atomicity
            # self.conn.begin()
            result = self.conn.execute(text("""DELETE from userdb where user_id = :user_id;"""),
                                {'user_id': user_id})
            if result.rowcount == 1:
                self.conn.commit()
            else:
                return error.error_authorization_fail()


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

    def change_password(
        self, user_id: str, old_password: str, new_password: str
    ) -> bool:
        try:
            code, message = self.check_password(user_id, old_password)
            if code != 200:
                return code, message

            # # Start a transaction to ensure atomicity
            # self.conn.begin()

            terminal = "terminal_{}".format(str(time.time()))
            token = jwt_encode(user_id, terminal)
            sql = """
            UPDATE userdb 
            SET password = :password, token = :token, terminal = :terminal 
            WHERE user_id = :user_id;
            """
            result = self.conn.execute(text(sql),
                    {'password': new_password, 'token':token, 'terminal': terminal, 'user_id': user_id})
            if result.rowcount == 0:
                return error.error_authorization_fail()

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
