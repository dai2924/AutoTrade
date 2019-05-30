"""
概要：
bitbankのAPIを使って自動で注文を行うプログラム．
実行時間，使用金額，値幅，通貨ペア，インターバルを指定して実行する．

動作：
指定通貨ペアで，使用金額分の買い注文を(現在の買いの価格) * (1-RANGE)の値段で発注する．
買い注文が約定したかどうかをインターバルの間隔で確認し，約定したなら，
同量の売り注文を(現在の売りの価格) * (1+RANGE)の値段で発注する．
売り注文が約定したかどうかをインターバルの間隔で確認し，約定したなら，
次の買い注文を行う．これを実行時間の間だけ繰り返す．

注意：
約定の確認をアクティブな注文があるかどうかで確認するため，プログラム以外に指定通貨の注文は無いことが前提
"""

import sys
import time
import python_bitbankcc as pbcc


# Trade key
API_KEY = 'public key'
API_SECRET = 'your private key'

TIME = 100  # run-time (min)
BUDGET = 10000  # Initial available budget
RANGE = 0.0001  # Price range
PAIR = 'xrp_jpy'  # Currency pair to order
CHECK_INTERVAL = 3  # Interval time of order check (sec)
MAKER_FEE_RATE = -0.0005
TAKER_FEE_RATE = 0.0015

# Get instance
prv = pbcc.private(API_KEY, API_SECRET)
pub = pbcc.public()



def make_order_info(pair, amount, price, orderside, ordertype='limit'):
    order_info = {"pair": pair,  # ペア
                    "amount": amount,  # 注文枚数
                    "price": price,  # 注文価格
                    "orderside": orderside,  # buy or sell
                    "ordertype": ordertype  # 指値注文の場合はlimit
                    }

    return order_info

#order process
def order(order_info):
    #Order
    value = prv.order(
        order_info["pair"], # ペア
        order_info["price"], # 価格
        order_info["amount"], # 注文枚数
        order_info["orderside"], # 注文サイド 売 or 買(buy or sell)
        order_info["ordertype"] # 注文タイプ 指値 or 成行(limit or market))
    )
    return value

def check_active_order():
    while (True):
        active_orders = prv.get_active_orders(PAIR)
        if not active_orders['orders']:  # check list empty
            break  # list is empty
        time.sleep(CHECK_INTERVAL)

def main():
    # Get my balance
    balances = prv.get_asset()
    for data in balances['assets']:
        print('●通貨：' + data['asset'])
        print('保有量：' + data['onhand_amount'])

    # Initial assets of JPY
    initial_jpy = float(balances['assets'][0]['onhand_amount'])

    # Budget error check
    if (initial_jpy < BUDGET):
        print('Error! BUDGET is over your assets!')
        sys.exit()

    # Initialize
    tmp_budget = BUDGET
    total_profit = 0
    total_num_trade = 0

    # Start time
    start_time = time.time()

    while(True):

        # Get ticker infomation
        ticker_value_1 = pub.get_ticker(PAIR)

        # Buy order
        buy_order_price = float(ticker_value_1['buy']) * (1.0 - RANGE)
        buy_order_amount = tmp_budget/buy_order_price
        print('board_buy_price: ', ticker_value_1['buy'])
        print('order_buy_price: ', buy_order_price)
        print('buy_order_amount: ', buy_order_amount)
        buy_order_info = make_order_info(PAIR, buy_order_amount, buy_order_price, orderside='buy', ordertype='limit')
        buy_info = order(buy_order_info)
        print('buy ordered!')
        print(buy_order_info)

        # Check active orders
        check_active_order()

        # Get ticker infomation
        ticker_value_2 = pub.get_ticker(PAIR)

        # Sell order
        tmp_sell_order_price = float(ticker_value_1['buy']) * (1.0 + RANGE)  # Calculate sell price using buy price
        if tmp_sell_order_price < float(ticker_value_2['sell']):  # 現在の板の売値より安いかを判定
            sell_order_price = float(ticker_value_2['sell']) * (1.0 + RANGE)  # 安い場合は現在の売値から再計算
            print('Sell price recalclated!')
        else:
            sell_order_price = tmp_sell_order_price
        sell_order_amount = buy_order_amount
        print('board_sell_price: ', ticker_value_2['sell'])
        print('order_sell_price: ', sell_order_price)
        print('sell_order_amount: ', sell_order_amount)
        sell_order_info = make_order_info(PAIR, sell_order_amount, sell_order_price, orderside='sell', ordertype='limit')
        sell_info = order(sell_order_info)
        print('sell ordered!')
        print(sell_order_info)

        # Check active orders
        check_active_order()

        # Get trade history
        trade_history = prv.get_trade_history(PAIR, '2')

        # Check order histoty about maker/taker
        sell_history = trade_history['trades'][0]
        buy_history = trade_history['trades'][1]
        if buy_history['maker_taker'] == 'taker':
            print('buy order was taker!')
            buy_fee_rate = TAKER_FEE_RATE
        else:
            buy_fee_rate = MAKER_FEE_RATE
        if sell_history['maker_taker'] == 'taker':
            print('sell order was taker!')
            sell_fee_rate = TAKER_FEE_RATE
        else:
            sell_fee_rate = MAKER_FEE_RATE

        # Calculate order cost and profit
        print(buy_history)
        print(sell_history)
        buy_cost = (buy_order_price * buy_order_amount) * (1+buy_fee_rate)
        sell_cost = (sell_order_price * sell_order_amount) * (1-sell_fee_rate)
        profit = sell_cost - buy_cost
        total_profit += profit
        total_num_trade += 1
        print('buy_cost: ', buy_cost)
        print('sell_cost: ', sell_cost)
        print('profit: ', profit)
        print('total_profit: ', total_profit)
        print('total_num_trade: ', total_num_trade)

        # Time check
        if (time.time() - start_time) > TIME*60:
            print('Run END!')
            break


if __name__ == '__main__':
    main()
    sys.exit()
