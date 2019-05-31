"""
概要：
bitbankのAPIを使って自動で注文を行うプログラム．同時に複数の注文を行う．
実行時間，使用数量，値幅，通貨ペア，注文監視インターバル，注文インターバル，リトライ回数，同時並列注文数を指定して実行する．

動作：
・取引可能な十分な資産があるかの確認
While
    ・使用可能な空き注文ラインがあるかを確認
    ・Orderクラスのインスタンスを作成
        ・作成時に買い注文と売り注文を同時に行う．
            ・買いの値段：(現在の買いの価格) * (1-RANGE)
            ・売りの値段：(現在の売りの価格) * (1+RANGE)
        ・注文後は，注文を監視し，自分の注文が約定したかを確認する．
        　→両方約定した場合は，ライン数の1増加させる．
        　→注文が残っている場合は，注文監視インターバル後に再度確認を行い，これを繰り返す．
    ・上記の処理を実行時間の間だけ繰り返す

注意：
・同時に並列数分の注文が実行され,time.sleepがそれぞれ実行されるため，並列処理を行なっている．
"""

import sys
import time
import concurrent.futures
import python_bitbankcc as pbcc

# Trade key
API_KEY = 'public key'
API_SECRET = 'your private key'

TIME = 60  # Run-time (min)
TRADE_AMOUNT = 400  # Initial available amount
RANGE = 0.0006  # Price range
PAIR = 'xrp_jpy'  # Currency pair to order
CHECK_INTERVAL = 3  # Interval time of order check (sec)
ORDER_INTERVAL = 30  # Interval time of reorder (sec)
ORDER_RETRY = 5  # Number of retry in sending order
MAX_LINE = 4  # Max parallel order
MAKER_FEE_RATE = -0.0005
TAKER_FEE_RATE = 0.0015

# Get instance
prv = pbcc.private(API_KEY, API_SECRET)
pub = pbcc.public()

# Make executor to parallel process
executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_LINE)

# Global variables
total_profit = 0
active_line_num = MAX_LINE


class Order:

    def __init__(self, idx):
        self.idx = idx
        self.order_amount = TRADE_AMOUNT / MAX_LINE
        self.buy_order_price = None
        self.sell_order_price = None
        self.buy_order_id = None
        self.sell_order_id = None
        self.profit = None
        self.buy_trade_history = None
        self.sell_trade_history = None
        self.buy_fee_rate = MAKER_FEE_RATE
        self.sell_fee_rate = MAKER_FEE_RATE

    def __del__(self):
        # print('delete instance', self.idx)
        pass

    def order_run(self):
        ticker_value = pub.get_ticker(PAIR)
        self.buy(ticker_value)
        self.sell(ticker_value)
        executor.submit(self.order_after)

    def order_after(self):
        self.monitor_active_order()
        self.check_history()
        self.calc_profit()
        self.show_result()
        self.return_line()

    # buy order method
    def buy(self, ticker_value):
        self.buy_order_price = float(ticker_value['buy']) * (1.0 - RANGE)
        buy_info = send_order(PAIR, self.order_amount, self.buy_order_price, orderside='buy', ordertype='limit')
        self.buy_order_id = buy_info['order_id']
        print(f'buy ordered! idx:{self.idx}  price:{self.buy_order_price:.6g}')

    # sell order method
    def sell(self, ticker_value):
        self.sell_order_price = float(ticker_value['sell']) * (1.0 + RANGE)
        sell_info = send_order(PAIR, self.order_amount, self.sell_order_price, orderside='sell', ordertype='limit')
        self.sell_order_id = sell_info['order_id']
        print(f'sell ordered! idx:{self.idx}  price:{self.sell_order_price:.6g}')

    # Monitor my buy/sell orders
    def monitor_active_order(self):
        while True:
            order_active_flag = False
            active_orders = prv.get_active_orders(PAIR)
            for order in active_orders['orders']:
                if (order['order_id'] == self.buy_order_id) or (order['order_id'] == self.sell_order_id):
                    order_active_flag = True
                else:
                    pass
            # if buy and sell orders dealt, break while loop
            if not order_active_flag:
                break
            time.sleep(CHECK_INTERVAL)

    # Check order histoty about maker/taker
    def check_history(self):

        # Flag of if order is found in trade_history (i.e.dealt or canceled)
        buy_history_flag = False
        sell_history_flag = False

        # Get trade history
        trade_history = prv.get_trade_history(PAIR, '20')
        for trade in trade_history['trades']:
            if trade['order_id'] == self.buy_order_id:
                self.buy_trade_history = trade
                buy_history_flag = True
            elif trade['order_id'] == self.sell_order_id:
                self.sell_trade_history = trade
                sell_history_flag = True
            else:
                pass

        if buy_history_flag:
            if self.buy_trade_history['maker_taker'] == 'taker':
                print('buy order was taker!')
                self.buy_fee_rate = TAKER_FEE_RATE
        if sell_history_flag:
            if self.sell_trade_history['maker_taker'] == 'taker':
                print('sell order was taker!')
                self.sell_fee_rate = TAKER_FEE_RATE

    # Calculate profit and add total profit
    def calc_profit(self):
        global total_profit
        deal_profit = (self.sell_order_price - self.buy_order_price) * self.order_amount
        fee_profit = (self.sell_order_price*self.sell_fee_rate + self.buy_order_price*self.buy_fee_rate) * self.order_amount
        self.profit = deal_profit - fee_profit
        total_profit += self.profit

    def show_result(self):
        print('注文がおそらく約定しました')
        print(f'order_idx:{self.idx}  profit:{self.profit:.5g}  total_profit:{total_profit:.5g}')

    def return_line(self):
        global active_line_num
        active_line_num += 1


# Check now assets to order
def check_assets(balances):
    hand_xrp_amount = float(balances['assets'][3]['onhand_amount'])
    hand_jpy_amount = float(balances['assets'][0]['onhand_amount'])

    ticker_value = pub.get_ticker(PAIR)
    now_xrp_price = float(ticker_value['last'])

    if (TRADE_AMOUNT < hand_xrp_amount) and (TRADE_AMOUNT*now_xrp_price < hand_jpy_amount):
        return True
    else:
        return False


# Send order to bitbank
def send_order(pair, amount, price, orderside, ordertype='limit'):
    for i in range(1, ORDER_RETRY + 1):
        try:
            value = prv.order(pair,  # ペア
                              price,  # 価格
                              amount,  # 注文枚数
                              orderside,  # 注文サイド 売 or 買(buy or sell)
                              ordertype  # 注文タイプ 指値 or 成行(limit or market))
                              )
        except Exception as e:
            print('error and retry:',i)
        else:
            return value
    print('critical')
    return False


def main():
    global active_line_num
    global total_profit

    start_time = time.time()
    order_idx = 0

    # Get my balance
    balances = prv.get_asset()
    for data in balances['assets']:
        print('●通貨：' + data['asset'])
        print('保有量：' + data['onhand_amount'])

    # Check if my assets is enough to order
    asset_flag = check_assets(balances)
    if asset_flag:
        print('asset is OK!')
    else:
        print('asset is not enough to order!')
        sys.exit()

    while True:
        # Check available line
        while True:
            if active_line_num > 0:
                break
            else:
                time.sleep(CHECK_INTERVAL)

        # Make order
        active_line_num -= 1
        order_idx += 1
        order_ins = Order(order_idx)
        order_ins.order_run()

        # Time check
        if (time.time() - start_time) > TIME * 60:
            break

        time.sleep(ORDER_INTERVAL)

    print('Run END!')
    print('total_order_num:', order_idx)
    print('total_profit:', total_profit)


if __name__ == '__main__':
    main()
    sys.exit()
