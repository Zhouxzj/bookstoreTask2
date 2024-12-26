import pytest
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer
from fe.access import book
from fe import conf
from fe.access import seller
from fe.access import buyer
import uuid

class TestCancelOrder:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.user_id = "test_cancel_order_{}".format(str(uuid.uuid1()))
        self.store_id = "test_cancel_order_{}".format(str(uuid.uuid1()))
        self.password = self.user_id
        self.seller = register_new_seller(self.user_id, self.password)

        self.buyer_id = "test_cancel_order1_{}".format(str(uuid.uuid1()))
        self.password = self.buyer_id
        self.buyer = register_new_buyer(self.buyer_id, self.password)

        code = self.seller.create_store(self.store_id)
        assert code == 200
        book_db = book.BookDB(conf.Use_Large_DB)
        self.books = book_db.get_book_info(0, 5)
        self.order_ids = []
        for bk in self.books:
            code = self.seller.add_book(self.store_id, 10, bk)
            assert code == 200
            book_id_and_count = [(bk.id, 5)]
            code, self.order_id = self.buyer.new_order(self.store_id, book_id_and_count)
            assert code == 200
            self.order_ids.append(self.order_id)

        yield

    def test_ok(self):
        for order in self.order_ids:
            code = self.buyer.buyer_cancel_order(order)
            assert code == 200

    def test_invalid_order_id_error(self):
        for order in self.order_ids:
            code = self.buyer.buyer_cancel_order(order + "x")
            assert code != 200
