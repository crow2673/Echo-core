import ccxt
kucoin = ccxt.kucoin({
    'apiKey': 'YOUR_API_KEY',
    'secret': 'YOUR_API_SECRET',
    'password': 'YOUR_API_PASSPHRASE',
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'mode': 'live'
    }
})
# Test with a small trade (example: buy 0 worth of BTC)
order = kucoin.create_market_buy_order('BTC/USDT', 10)
print(order)
