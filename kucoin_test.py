import os, ccxt
exchange = ccxt.kucoin({'sandbox': False, 'apiKey': os.getenv('KUCOIN_APIKEY'), 'secret': os.getenv('KUCOIN_SECRET')})
balance = exchange.fetch_balance()
print(balance['total'])
