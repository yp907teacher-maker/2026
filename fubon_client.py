"""
富邦新一代 API (fubon_neo) 連線與下單框架。

登入所需帳密與憑證資訊一律從環境變數讀取，不寫死於程式碼中：
    FUBON_ID          身分證字號 / 統一編號
    FUBON_PASSWORD    登入密碼
    FUBON_CERT_PATH   憑證檔案路徑 (.pfx)
    FUBON_CERT_PASS   憑證密碼

下單功能 (place_order) 目前僅組裝 Order 物件供檢視，尚未呼叫
sdk.stock.place_order() 送出真實委託。待確認無誤後再開通。
"""

import os

from fubon_neo.sdk import FubonSDK, Order
from fubon_neo.constant import BSAction, MarketType, OrderType, PriceType, TimeInForce


class FubonClient:
    def __init__(self):
        self.sdk = FubonSDK()
        self.accounts = None

    def connect(self):
        """使用環境變數中的帳密與憑證登入富邦新一代 API，回傳帳戶清單。"""
        fubon_id = os.environ["FUBON_ID"]
        password = os.environ["FUBON_PASSWORD"]
        cert_path = os.environ["FUBON_CERT_PATH"]
        cert_pass = os.environ["FUBON_CERT_PASS"]

        result = self.sdk.login(fubon_id, password, cert_path, cert_pass)
        if not result.is_success:
            raise RuntimeError(f"登入失敗: {result.message}")

        self.accounts = result.data
        return self.accounts

    def disconnect(self):
        """登出並釋放連線。"""
        self.sdk.logout()
        self.accounts = None

    def get_default_account(self):
        if not self.accounts:
            raise RuntimeError("尚未登入，請先呼叫 connect()")
        return self.accounts[0]

    def build_order(self, symbol, quantity, price, buy_sell=BSAction.Buy):
        """組裝一筆委託單物件，僅供檢視/驗證用途，不會送出委託。"""
        return Order(
            buy_sell=buy_sell,
            symbol=symbol,
            price=str(price),
            quantity=quantity,
            market_type=MarketType.Common,
            price_type=PriceType.Limit,
            time_in_force=TimeInForce.ROD,
            order_type=OrderType.Stock,
        )

    def get_holdings(self, account=None):
        """查詢目前持股庫存（查詢動作，不涉及下單）。"""
        account = account or self.get_default_account()
        result = self.sdk.accounting.inventories(account)
        if not result.is_success:
            raise RuntimeError(f"查詢持股失敗: {result.message}")
        return result.data

    def place_order(self, order):
        """
        下單動作目前停用。
        需求方已明確表示「先不要做任何下單動作」，
        因此本函式先不呼叫 self.sdk.stock.place_order()，
        待確認需求後再啟用。
        """
        raise NotImplementedError("下單功能尚未啟用，待確認需求後再開通")


if __name__ == "__main__":
    client = FubonClient()
    accounts = client.connect()
    print("登入成功，帳戶清單:", accounts)

    holdings = client.get_holdings()
    print("目前持股:", holdings)

    client.disconnect()
