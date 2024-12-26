import pytest
import uuid
from fe.access import buyer
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer
from fe.access import book
from fe.access import seller
from fe import conf


class TestDeliver:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.user_id = "test_deliver_user_{}".format(str(uuid.uuid1()))
        self.store_id = "test_deliver_store_{}".format(str(uuid.uuid1()))
        self.password = self.user_id
        self.seller = register_new_seller(self.user_id, self.password)

        self.buyer_id = "test_deliver_buyer_{}".format(str(uuid.uuid1()))
        self.password = self.buyer_id
        self.buyer = register_new_buyer(self.buyer_id, self.password)

        self.order_ids = []
        code = self.seller.create_store(self.store_id)
        assert code == 200
        book_db = book.BookDB(conf.Use_Large_DB)
        self.books = book_db.get_book_info(0, 5)
        for bk in self.books:
            code = self.seller.add_book(self.store_id, 10, bk)
            assert code == 200
            book_id_and_count = [(bk.id, 5)]
            code, self.order_id = self.buyer.new_order(self.store_id, book_id_and_count)
            assert code == 200
            self.order_ids.append(self.order_id)
            code = self.buyer.add_funds(999999)
            assert code == 200
            code = self.buyer.payment(self.order_id)
            assert code == 200
        yield

    def test_error_store_id(self):
        for order in self.order_ids:
            code = self.seller.deliver(
                self.store_id + "_x", order
            )
            assert code != 200

    def test_error_order_id(self):
        for order in self.order_ids:
            code = self.seller.deliver(
                self.store_id, order + "_x"
            )
            assert code != 200

    def test_ok(self):
        for order in self.order_ids:
            code = self.seller.deliver(
                self.store_id, order
            )
        assert code == 200

