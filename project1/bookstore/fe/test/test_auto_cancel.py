import time
import pytest
from fe.access import buyer
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer
from fe.access import book
from fe.access import seller
from fe import conf
import uuid

class TestAutoCancel:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.user_id = "test_auto_cancel_order_{}".format(str(uuid.uuid1()))
        self.store_id = "test_auto_cancel_order_{}".format(str(uuid.uuid1()))
        self.password = self.user_id
        self.seller = register_new_seller(self.user_id, self.password)

        self.buyer_id = "test_auto_cancel_order1_{}".format(str(uuid.uuid1()))
        self.password = self.buyer_id
        self.buyer = register_new_buyer(self.buyer_id, self.password)

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

        yield

    def test_ok(self):
        time.sleep(12)  # 等待一段时间观察效果，设置的是过十秒即为超时，取消订单，每十秒会检查一次
        code = self.buyer.auto_cancel_order()
        assert code == 200