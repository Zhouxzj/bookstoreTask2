import pytest
import uuid
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer
from fe.access import book
from fe import conf
from fe.access import seller
from fe.access import buyer
import random

class TestSearchBook:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        # do before test
        self.seller_id = "test_search_books_{}".format(str(uuid.uuid1()))
        self.store_id = "test_search_books_{}".format(str(uuid.uuid1()))
        self.password = self.seller_id
        self.seller = register_new_seller(self.seller_id, self.password)
        code = self.seller.create_store(self.store_id)
        assert code == 200

        self.user_id = "test_search_book_{}".format(str(uuid.uuid1()))
        self.passwd = self.user_id
        self.buyer = register_new_buyer(self.user_id, self.passwd)
        yield

    def gen_keyword(self):
        book_db = book.BookDB(conf.Use_Large_DB)
        rows = book_db.get_book_count()
        start = 0
        size = random.randint(1, rows)
        books = book_db.get_book_info(rows, rows+1)
        book_id_exist = []
        stock_level = 0
        for bk in books:
            code = self.seller.add_book(self.store_id, stock_level, bk)
            assert code == 200
            book_id_exist.append(bk)

        self.keyword_list = []
        for bk in book_id_exist:
            book_info = bk.__dict__
            r = random.randint(1, 4)
            if r == 1:
                self.keyword_list.append(book_info['title'])
            elif r == 2:
                self.keyword_list.append(book_info['tags'])
            elif r == 3:
                self.keyword_list.append(book_info['author'])
            else:
                content = book_info['content']
                content_slice = content[:10]
                self.keyword_list.append(content_slice)

        return "ok", self.keyword_list


    def test_ok(self):
        ok, keyword_list = self.gen_keyword()
        assert ok
        tag = 0
        for keyword in keyword_list:
            if tag :
                code = self.buyer.search_books(keyword, store_id=None)
            else:
                code = self.buyer.search_books(keyword, store_id=self.store_id)
            assert code == 200

    def test_error_store_id(self):
        ok, keyword_list = self.gen_keyword()
        assert ok
        tag = 0
        for keyword in keyword_list:
            code = self.buyer.search_books(keyword, self.store_id + "x")
            assert code != 200

