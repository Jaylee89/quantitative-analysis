POLL_MIN_INTERVAL = 2.0
POLL_MAX_INTERVAL = 3.0
API_URL_TEMPLATE = "https://api.jijinhao.com/sQuoteCenter/realTime.htm?code=JO_92233&isCalc=true&_={timestamp}"
DB_PATH = "data/gold.db"
SIGNALS_DB_PATH = "data/signals.db"
REQUEST_TIMEOUT = 10
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Referer": "https://m.cngold.org/",
    "sec-ch-ua": '"Chromium";v="130", "Microsoft Edge";v="130", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "script",
    "sec-fetch-mode": "no-cors",
    "sec-fetch-site": "cross-site",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
