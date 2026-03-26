import ccxt
import time
import csv
from datetime import datetime

exchange = ccxt.binance()
symbol = "BTC/USDT"

prices = []
in_position = False
position_type = None
entry_price = 0
highest_price = 0
lowest_price = 0
wins = 0
losses = 0
trade_count = 0
total_pnl = 0
short_avg_previous = 0
long_avg_previous = 0
cooldown_counter = 0
rsi_period = 14


def get_price():
    ticker = exchange.fetch_ticker(symbol)
    return ticker["last"]


def calculate_rsi(prices_list, period=14):
    if len(prices_list) < period + 1:
        return None

    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = prices_list[-i] - prices_list[-i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


with open("trades_log.csv", "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["time", "entry_price", "exit_price", "pnl", "result"])

while True:
    try:
        if cooldown_counter > 0:
            cooldown_counter -= 1

        price = get_price()
        prices.append(price)

        if len(prices) > 20:
            prices.pop(0)

        short_avg = sum(prices[-5:]) / len(prices[-5:])
        long_avg = sum(prices) / len(prices)
        trend_diff = short_avg - long_avg
        market_regime = "trend" if abs(trend_diff) >= 12 else "sideways"

        rsi = calculate_rsi(prices, rsi_period)
        recent_high = max(prices[-10:]) if len(prices) >= 10 else None
        recent_low = min(prices[-10:]) if len(prices) >= 10 else None
        recent_range = (max(prices[-10:]) - min(prices[-10:])) if len(prices) >= 10 else 0

        # V5 sniper: no entries before minimum data window.
        if len(prices) < 15:
            print("Waiting...")
            avg_pnl = total_pnl / trade_count if trade_count > 0 else 0
            print("\n====== BOT STATUS ======")
            print(f"BTC price: {price}")
            print(f"Short avg: {round(short_avg, 2)}")
            print(f"Long avg: {round(long_avg, 2)}")
            print(f"Market regime: {market_regime}")
            print(f"Trend diff: {round(trend_diff, 2)}")
            print(f"Recent range: {round(recent_range, 2)}")
            print(f"RSI: {round(rsi, 2) if rsi is not None else 'N/A'}")
            print(f"Position: {in_position}")
            print(f"Wins: {wins} | Losses: {losses}")
            print(f"Trades: {trade_count}")
            print(f"Total PnL: {round(total_pnl, 2)}")
            print(f"Avg per trade: {round(avg_pnl, 2)}")
            print("========================\n")
            short_avg_previous = short_avg
            long_avg_previous = long_avg
            time.sleep(0.5)
            continue

        if (
            not in_position
            and cooldown_counter == 0
            and market_regime == "trend"
            and recent_range >= 25
            and rsi is not None
            and short_avg > long_avg
            and trend_diff >= 15
            and long_avg > long_avg_previous
            and short_avg > short_avg_previous
            and price >= short_avg
            and recent_high is not None
            and price >= recent_high + 3
            and rsi > 58
            and rsi < 72
        ):
            print("LONG SIGNAL")
            in_position = True
            position_type = "long"
            entry_price = price
            highest_price = price
            print("=== ENTER LONG ===")
            print(f"Entry price: {round(entry_price, 2)}")
            print(f"DEBUG ENTRY at price: {price}")

        if (
            not in_position
            and cooldown_counter == 0
            and market_regime == "trend"
            and recent_range >= 25
            and rsi is not None
            and short_avg < long_avg
            and trend_diff <= -15
            and long_avg < long_avg_previous
            and short_avg < short_avg_previous
            and price <= short_avg
            and recent_low is not None
            and price <= recent_low - 3
            and rsi < 42
            and rsi > 28
        ):
            print("SHORT SIGNAL")
            in_position = True
            position_type = "short"
            entry_price = price
            lowest_price = price
            print("=== ENTER SHORT ===")
            print(f"Entry price: {round(entry_price, 2)}")
            print(f"DEBUG ENTRY at price: {price}")

        if in_position:
            if position_type == "long":
                pnl = price - entry_price
            else:
                pnl = entry_price - price

            if pnl > 8:
                if position_type == "long":
                    stop_loss_price = entry_price - 2
                else:
                    stop_loss_price = entry_price + 2
            else:
                if position_type == "long":
                    stop_loss_price = entry_price - 25
                else:
                    stop_loss_price = entry_price + 25

            if position_type == "long":
                if price > highest_price:
                    highest_price = price
                trailing_drop = highest_price - price
            else:
                if price < lowest_price:
                    lowest_price = price
                trailing_drop = price - lowest_price

            print(f"Entry price: {round(entry_price, 2)}")
            print(f"current PnL: {round(pnl, 2)}")
            if position_type == "long":
                print(f"highest price: {round(highest_price, 2)}")
            else:
                print(f"lowest price: {round(lowest_price, 2)}")

            if pnl >= max(40, long_avg * 0.0008):
                print(f"=== TAKE PROFIT ({position_type.upper()}) ===")
                print(f"Exit pnl: {round(pnl, 2)}")
                print(f"EXIT TRADE | pnl={pnl}")
                wins += 1
                trade_count += 1
                total_pnl += pnl
                in_position = False
                position_type = None
                cooldown_counter = 3
                with open("trades_log.csv", "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.now(),
                        entry_price,
                        price,
                        round(pnl, 2),
                        "win" if pnl > 0 else "loss"
                    ])

            elif (position_type == "long" and price <= stop_loss_price) or (position_type == "short" and price >= stop_loss_price):
                print(f"=== STOP LOSS ({position_type.upper()}) ===")
                print(f"Exit pnl: {round(pnl, 2)}")
                print(f"EXIT TRADE | pnl={pnl}")
                losses += 1
                trade_count += 1
                total_pnl += pnl
                in_position = False
                position_type = None
                cooldown_counter = 3
                with open("trades_log.csv", "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.now(),
                        entry_price,
                        price,
                        round(pnl, 2),
                        "win" if pnl > 0 else "loss"
                    ])

            dynamic_trailing = max(10, pnl * 0.4)
            if trailing_drop >= dynamic_trailing and pnl > 15:
                print(f"TRAILING STOP HIT ({position_type.upper()})")
                print(f"EXIT TRADE | pnl={pnl}")
                losses += 1
                trade_count += 1
                total_pnl += pnl
                in_position = False
                position_type = None
                cooldown_counter = 3
                with open("trades_log.csv", "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.now(),
                        entry_price,
                        price,
                        round(pnl, 2),
                        "win" if pnl > 0 else "loss"
                    ])

        else:
            print("Waiting...")

        avg_pnl = total_pnl / trade_count if trade_count > 0 else 0
        print("\n====== BOT STATUS ======")
        print(f"BTC price: {price}")
        print(f"Short avg: {round(short_avg, 2)}")
        print(f"Long avg: {round(long_avg, 2)}")
        print(f"Market regime: {market_regime}")
        print(f"Trend diff: {round(trend_diff, 2)}")
        print(f"Recent range: {round(recent_range, 2)}")
        print(f"RSI: {round(rsi, 2) if rsi is not None else 'N/A'}")
        print(f"Position: {in_position}")
        print(f"Wins: {wins} | Losses: {losses}")
        print(f"Trades: {trade_count}")
        print(f"Total PnL: {round(total_pnl, 2)}")
        print(f"Avg per trade: {round(avg_pnl, 2)}")
        print("========================\n")

        short_avg_previous = short_avg
        long_avg_previous = long_avg
        time.sleep(0.5)

    except Exception as e:
        print("Error:", e)
        time.sleep(0.5)


def test_
def get_bitcoin_price():

# create a crypto trading bot using binance and ccxt
