import os
from okx import OkxRestClient

# 配置（用环境变量更好）
OKX_API_KEY = os.getenv('OKX_API_KEY')
OKX_SECRET_KEY = os.getenv('OKX_SECRET_KEY')
OKX_PASSPHRASE = os.getenv('OKX_PASSPHRASE')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = int(os.getenv('TELEGRAM_CHAT_ID', '0'))



# 支持的币种 → OKX 交易对
PRICE_SYMBOLS = {
    'btc': 'BTC-USDT',
    'eth': 'ETH-USDT',
    'sol': 'SOL-USDT',
    'okb': 'OKB-USDT',
    'ton': 'TON-USDT',
    # 可以继续添加
    'BTC': 'BTC-USDT',
    'ETH': 'ETH-USDT',
    'SOL': 'SOL-USDT',
}

# 关闭全局代理，确保 OKX 直连
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

# 价格提醒全局变量
PRICE_ALERTS = {}
ALERT_COUNTER = 0

# 初始化 OKX 客户端
api = OkxRestClient(OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE)