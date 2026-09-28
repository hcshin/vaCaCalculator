import logging
import requests
import copy
import json
from statistics import median
from datetime import datetime


logger = logging.getLogger('autoinvestment_logger')


class BaseStock:
    def __init__(self, exchange_rate: float, ref_exchange_rate: float, ref_stockgrp_info: dict):
        self.exchange_rate = exchange_rate
        self.ref_exchange_rate = ref_exchange_rate
        self.ref_stockgrp_info = ref_stockgrp_info
        self.stockgrp_info = copy.deepcopy(ref_stockgrp_info)  # where new values will be stored

    def _postWrapper(self, URL, headers=None, data=None, verify=True):
        logger.debug(f'POSTing headers {headers} and data {data} to {URL}.')
        res = requests.post(URL, headers=headers, data=data, verify=verify)
        logger.debug(f'Got POST response: {res.text}')

        return res

    def _getWrapper(self, URL, headers=None, params=None, verify=True, timeout=None):
        logger.debug(f'GETing headers {headers} and params {params} to {URL}.')
        res = requests.get(URL, headers=headers, params=params, verify=verify, timeout=timeout)
        logger.debug(f'Got GET response: {res.text}')

        return res

    def _update_ca_invested(self):
        for stockkey, stock in self.stockgrp_info['stocks'].items():
            # utilize ref_stockgrp_info to derive cumSumCaInvested for this report
            # N.B. need2investCA has nothing to do with actual invested amount of each stock it's just an ideal guideline for deriving VA amount
            #       Even if we didn't followed the guideline its trajectory remains unaltered (so that we can eventually persue the ideal goal)
            ref_stock = self.ref_stockgrp_info['stocks'][stockkey]
            if 'cumSumCaInvested' not in ref_stock.keys():
                # in case of neither cumSumCaInvested, cumSumCaInvestedInKRW, nor cumSumCaInvestedInUSD exists
                # use appraisement as previous cumSumCaInvested
                # N.B. this route is only for the 1st report because reports afterward all have cumSumCaInvested
                if 'cumSumCaInvestedInKRW' not in ref_stock.keys() and 'cumSumCaInvestedInUSD' not in ref_stock.keys():
                    stock['cumSumCaInvested'] = stock['appraisement']
                # in case either cumSumCaInvestedInKRW or cumSumCaInvestedInUSD exists, use them instead
                else:
                    stock['cumSumCaInvested'] = 0.0
                    if 'cumSumCaInvestedInKRW' in ref_stock.keys():
                        stock['cumSumCaInvested'] += ref_stock['cumSumCaInvestedInKRW'] / self.exchange_rate
                        del stock['cumSumCaInvestedInKRW']
                    if 'cumSumCaInvestedInUSD' in ref_stock.keys():
                        stock['cumSumCaInvested'] += ref_stock['cumSumCaInvestedInUSD']
                        del stock['cumSumCaInvestedInUSD']
            else:
                stock['cumSumCaInvested'] = ref_stock['cumSumCaInvested'] + ref_stock['need2investCA']

    def _update_holdings(self):
        for stockkey, stock in self.stockgrp_info['stocks'].items():
            if 'holdings' not in stock.keys():
                logger.error(f'{stockkey} does not have holdings item. this must be given to update holdings')
                raise ValueError

            # take account of actually invested units. add them up into holdings
            if 'actualInvestedInUnits' in stock.keys():
                stock['holdings'] += stock['actualInvestedInUnits']
                del stock['actualInvestedInUnits']  # remove actualInvestedInUnits from this_report

    def _derive_appraisement(self):
        for stockkey, stock in self.stockgrp_info['stocks'].items():
            if 'price' not in stock.keys():
                logger.error(f'{stockkey} does not have price item. this must be given to derive appraisement')
                raise Exception

            if 'holdings' not in stock.keys():
                logger.error(f'{stockkey} does not have holdings item. this must be given to derive appraisement.')
                raise Exception

            # for domestic: prices are in KRW
            if stock['currency'] == 'KRW':
                appraisementKRW = float(stock['holdings']) * float(stock['price'])
                stock['appraisement'] = appraisementKRW / self.exchange_rate

            # for US: prices are in USD
            elif stock['currency'] == 'USD':
                stock['appraisement'] = float(stock['holdings']) * float(stock['price'])

            else:
                logger.error(f'Currently only KRW or USD are supported as currencies, but {stock["currency"]} given.')

    def update_all(self):  # call order is crucial
        self._update_holdings()
        self._derive_appraisement()  # after _update_holdings
        self._update_ca_invested()  # after _derive_appraisement

    def get_stockgrp(self) -> dict:
        return self.stockgrp_info


class KisStock(BaseStock):
    # KIS constants
    # - General
    URL_BASE_REAL = 'https://openapi.koreainvestment.com:9443'
    URL_BASE_TEST = 'https://openapivts.koreainvestment.com:29443'  # test domain
    URL_BASE = URL_BASE_REAL
    BASE_HEADER = {'content-type': 'application/json'}

    # - Service paths
    DOM_PRICE_INQUIRY_PATH = 'uapi/domestic-stock/v1/quotations/inquire-price'
    US_PRICE_INQUIRY_PATH = 'uapi/overseas-price/v1/quotations/price'
    DOM_HOLDINGS_INQUIRY_PATH = 'uapi/domestic-stock/v1/trading/inquire-balance'
    DOM_PENSION_HOLDINGS_INQUIRY_PATH = 'uapi/domestic-stock/v1/trading/pension/inquire-balance'
    US_HOLDINGS_INQUIRY_PATH = 'uapi/overseas-stock/v1/trading/inquire-balance'

    # - TR_ID (service identifiers)
    TR_ID_CURR_DOM_PRICE = 'FHKST01010100'
    TR_ID_CURR_US_PRICE = 'HHDFS00000300'
    TR_ID_CURR_DOM_HOLDINGS_REAL = 'TTTC8434R'
    TR_ID_CURR_DOM_HOLDINGS_TEST = 'VTTC8434R'
    TR_ID_CURR_DOM_HOLDINGS = TR_ID_CURR_DOM_HOLDINGS_REAL
    TR_ID_CURR_DOM_HOLDINGS_PENSION = 'TTTC2208R'
    TR_ID_CURR_US_HOLDINGS_REAL = 'TTTS3012R'
    TR_ID_CURR_US_HOLDINGS_TEST = 'VTTS3012R'

    # - Prices queries
    EXCD_NIGHT2DAY_DICT = {
        'NYS': 'BAY',
        'NAS': 'BAQ',
        'AMS': 'BAA'
    }

    # - Holdings queries
    # = DOM
    AFHR_FLPR_YN = 'N'
    OFL_YN = 'N'
    INQR_DVSN = '02'
    UNPR_DVSN = '01'
    FUND_STTL_ICLD_YN = 'N'
    FNCG_AMT_AUTO_RDPT_YN = 'N'
    PRCS_DVSN = '00'
    # = DOM PENSION
    INQR_DVSN_PENSION = '00'
    ACCA_DVSN_CD = '00'

    # = US
    OVRS_EXCG_CD = 'NASD'  # NYS + NAS
    TR_CRCY_CD = 'USD'  # Currency for the trading
    # = Paging
    MAX_HOLDINGS_PAGES = 100

    def __init__(self, exchange_rate: float, ref_exchange_rate: float, secrets_fname: str, tokens_fname: str, stockgrp_info: dict):
        super().__init__(exchange_rate, ref_exchange_rate, stockgrp_info)

        with open(secrets_fname, 'r') as f_secret:
            f_secret_loaded = json.load(f_secret)
            self.APP_KEY = f_secret_loaded['KisSecrets']['APP_KEY']
            self.APP_SECRET = f_secret_loaded['KisSecrets']['APP_SECRET']

        try:
            with open(tokens_fname, 'r') as f_token:
                f_token_loaded = json.load(f_token)
                # check if access_token is already in f_token
                KisTokens = f_token_loaded['KisTokens']
                if 'ACCESS_TOKEN' in KisTokens.keys() and 'ACCESS_TOKEN_TIME' in KisTokens.keys():
                    timediff = datetime.today() - datetime.strptime(KisTokens['ACCESS_TOKEN_TIME'], '%Y-%m-%d %H:%M:%S')
                    # access token expires after 24H
                    if timediff.days > 0:
                        self.access_token = None
                    else:
                        self.access_token = KisTokens['ACCESS_TOKEN']
                else:
                    self.access_token = None
        except FileNotFoundError:
            self.access_token = None

        # if there's no valid token, re-issue it
        if self.access_token is None:
            f_token_loaded = {}
            f_token_loaded['KisTokens'] = {}
            self._issue_access_token()
            # dump newly issued token to secrets.json
            f_token_loaded['KisTokens']['ACCESS_TOKEN'] = self.access_token
            f_token_loaded['KisTokens']['ACCESS_TOKEN_TIME'] = self.access_token_time
            with open(tokens_fname, 'w') as f_token:
                json.dump(f_token_loaded, f_token, indent=4)

    def _issue_access_token(self):
        self.BASE_BODY = {
            'grant_type': 'client_credentials',
            'appkey': self.APP_KEY,
            'appsecret': self.APP_SECRET
        }

        access_token_issue_headers = copy.deepcopy(KisStock.BASE_HEADER)
        access_token_issue_body = json.dumps(copy.deepcopy(self.BASE_BODY))
        access_token_issue_path = 'oauth2/tokenP'
        access_token_issue_url = f'{KisStock.URL_BASE}/{access_token_issue_path}'
        access_token_issue_res = self._postWrapper(
            access_token_issue_url,
            access_token_issue_headers,
            access_token_issue_body
        )
        self.access_token = access_token_issue_res.json()['access_token']
        self.access_token_time = datetime.strftime(datetime.today(), '%Y-%m-%d %H:%M:%S')

    def _collect_prices(self):
        # domestic
        dom_price_inquiry_url = f'{KisStock.URL_BASE}/{KisStock.DOM_HOLDINGS_INQUIRY_PATH}'
        dom_price_inquiry_headers = copy.deepcopy(KisStock.BASE_HEADER)
        dom_price_inquiry_headers['authorization'] = f'Bearer {self.access_token}'
        dom_price_inquiry_headers['appkey'] = self.APP_KEY
        dom_price_inquiry_headers['appsecret'] = self.APP_SECRET
        dom_price_inquiry_headers['tr_id'] = KisStock.TR_ID_CURR_DOM_PRICE

        # US
        us_price_inquiry_url = f'{KisStock.URL_BASE}/{KisStock.US_PRICE_INQUIRY_PATH}'
        us_price_inquiry_headers = copy.deepcopy(KisStock.BASE_HEADER)
        us_price_inquiry_headers['authorization'] = f'Bearer {self.access_token}'
        us_price_inquiry_headers['appkey'] = self.APP_KEY
        us_price_inquiry_headers['appsecret'] = self.APP_SECRET
        us_price_inquiry_headers['tr_id'] = KisStock.TR_ID_CURR_US_PRICE

        for stockkey, stock in self.stockgrp_info['stocks'].items():
            if stock['market'] == 'DOM':
                price_inquiry_params = {
                    'fid_cond_mrkt_div_code': 'J',
                    'fid_input_iscd': stockkey
                }
                res = self._getWrapper(dom_price_inquiry_url, dom_price_inquiry_headers, price_inquiry_params)

                # check success
                if res.json()['rt_cd'] != '0':
                    error_msg = f'dom price query for stock {stockkey} failed.'
                    logger.error(error_msg)
                    raise Exception(error_msg)

                stock['price'] = float(res.json()['output']['stck_prpr'])  # update price as this month's value

            elif stock['market'] == 'NYS' or stock['market'] == 'NAS' or stock['market'] == 'AMS':
                price_inquiry_params = {
                    'AUTH': '',
                    'EXCD': stock['market'],
                    'SYMB': stockkey
                }
                daytime_tried = False
                while True:
                    res = self._getWrapper(us_price_inquiry_url, us_price_inquiry_headers, price_inquiry_params)

                    stockprice = res.json()['output']['last']

                    # check success
                    if res.json()['rt_cd'] != '0':
                        error_msg = f'US price query for stock {stockkey} failed.'
                        logger.error(error_msg)
                        raise Exception(error_msg)

                    if stockprice == '':  # this happens when there's no such a stock within the given market
                        # when night EXCD fails try once more this daytime EXCD
                        if daytime_tried:
                            error_msg = f'price query for {stockkey} failed'
                            logger.error(error_msg)
                            raise Exception(error_msg)
                        daytime_tried = True
                        price_inquiry_params['EXCD'] = KisStock.EXCD_NIGHT2DAY_DICT[price_inquiry_params['EXCD']]
                    else:  # query successful
                        stock['price'] = float(stockprice)  # update price as this month's price
                        break
            else:
                logger.error(f'stock[\'market\'] only supports one of DOM, NYS, and NAS, but {stock["market"]} given')
                raise ValueError

            logger.info(f'Current price of stock {stockkey} is {stock["price"]} {stock["currency"]}')

    def _collect_holdings(self):
        # extract CANO and ACNT_PRDT_CD from accountNo
        self.CANO, self.ACNT_PRDT_CD = self.stockgrp_info['accountNo'].split('-')

        # N.B. although KIS API supports collection of actual invested amount of each stock, we only collect the holdings
        # because this is different from cumSumCaInvested which represents cum sum of invested amount determined by CA
        # In contrast what KIS API offers is the result of VA, which practically mixes up CA as well)

        if self.ACNT_PRDT_CD == '29':
            # pension (domestic only)
            dom_holdings_inquiry_url = f'{KisStock.URL_BASE}/{KisStock.DOM_PENSION_HOLDINGS_INQUIRY_PATH}'
            dom_holdings_inquiry_headers = copy.deepcopy(KisStock.BASE_HEADER)
            dom_holdings_inquiry_headers['authorization'] = f'Bearer {self.access_token}'
            dom_holdings_inquiry_headers['appkey'] = self.APP_KEY
            dom_holdings_inquiry_headers['appsecret'] = self.APP_SECRET
            dom_holdings_inquiry_headers['tr_id'] = KisStock.TR_ID_CURR_DOM_HOLDINGS_PENSION
            dom_holdings_inquiry_headers['custtype'] = 'P'  # Individual Customer
            dom_holdings_inquiry_params = {
                'CANO': self.CANO,
                'ACNT_PRDT_CD': self.ACNT_PRDT_CD,
                'ACCA_DVSN_CD': KisStock.ACCA_DVSN_CD,
                'INQR_DVSN': KisStock.INQR_DVSN_PENSION,
                'CTX_AREA_FK100': '',
                'CTX_AREA_NK100': ''
            }
        else:
            # domestic
            dom_holdings_inquiry_url = f'{KisStock.URL_BASE}/{KisStock.DOM_HOLDINGS_INQUIRY_PATH}'
            dom_holdings_inquiry_headers = copy.deepcopy(KisStock.BASE_HEADER)
            dom_holdings_inquiry_headers['authorization'] = f'Bearer {self.access_token}'
            dom_holdings_inquiry_headers['appkey'] = self.APP_KEY
            dom_holdings_inquiry_headers['appsecret'] = self.APP_SECRET
            dom_holdings_inquiry_headers['tr_id'] = KisStock.TR_ID_CURR_DOM_HOLDINGS
            dom_holdings_inquiry_params = {
                'CANO': self.CANO,
                'ACNT_PRDT_CD': self.ACNT_PRDT_CD,
                'AFHR_FLPR_YN': KisStock.AFHR_FLPR_YN,
                'OFL_YN': KisStock.OFL_YN,
                'INQR_DVSN': KisStock.INQR_DVSN,
                'UNPR_DVSN': KisStock.UNPR_DVSN,
                'FUND_STTL_ICLD_YN': KisStock.FUND_STTL_ICLD_YN,
                'FNCG_AMT_AUTO_RDPT_YN': KisStock.FNCG_AMT_AUTO_RDPT_YN,
                'PRCS_DVSN': KisStock.PRCS_DVSN,
                'CTX_AREA_FK100': '',
                'CTX_AREA_NK100': ''
            }

        # a fully sold stock is not returned by the API, so reset holdings first. otherwise it keeps the ref report's holdings
        self._reset_holdings(('DOM',))

        # query the holdings
        is_all = False
        num_pages = 0
        while not is_all:
            num_pages = self._count_page(num_pages)
            res = self._getWrapper(dom_holdings_inquiry_url, dom_holdings_inquiry_headers, dom_holdings_inquiry_params)

            # check success
            if res.json()['rt_cd'] != '0':
                error_msg = 'dom holdings query failed.'
                logger.error(error_msg)
                raise Exception(error_msg)

            # get holdings amount to corresponding stock and derive the increment from ref_report
            stocks = res.json()['output1']
            for stock in stocks:
                stockkey = stock['pdno']

                # if the stockkey is not enlisted in stockgrp_info, pass that stock because it's not the target of autoinv
                if stockkey not in self.stockgrp_info['stocks'].keys():
                    continue

                # check if each stock has actualInvestedInUnits item and if so print warning
                if 'actualInvestedInUnits' in self.stockgrp_info['stocks'][stockkey].keys():
                    logger.warning('KisStock does not utilize actualInvestedInUnits, '
                                   f'but value of {self.stockgrp_info["stocks"][stockkey]["actualInvestedInUnits"]} '
                                   f'given for {stockkey}. Thus, given value is ignored and deleted from this report.')
                    del self.stockgrp_info['stocks'][stockkey]['actualInvestedInUnits']

                self.stockgrp_info['stocks'][stockkey]['holdings'] = int(stock['hldg_qty'])

            # determine whether to continue querying
            tr_cont = res.headers['tr_cont']
            if tr_cont == 'F' or tr_cont == 'M':
                continue  # query not finished
            elif tr_cont == 'D' or tr_cont == 'E':
                is_all = True  # query finished
            else:
                logger.error(f'Invalid tr_cont value ({tr_cont}) in querying holdings')
                raise ValueError

        # US
        us_holdings_inquiry_url = f'{KisStock.URL_BASE}/{KisStock.US_HOLDINGS_INQUIRY_PATH}'
        us_holdings_inquiry_headers = copy.deepcopy(KisStock.BASE_HEADER)
        us_holdings_inquiry_headers['authorization'] = f'Bearer {self.access_token}'
        us_holdings_inquiry_headers['appkey'] = self.APP_KEY
        us_holdings_inquiry_headers['appsecret'] = self.APP_SECRET
        us_holdings_inquiry_headers['tr_id'] = KisStock.TR_ID_CURR_US_HOLDINGS_REAL
        us_holdings_inquiry_headers['custtype'] = 'P'  # Private Customer
        us_holdings_inquiry_params = {
            'CANO': self.CANO,
            'ACNT_PRDT_CD': self.ACNT_PRDT_CD,
            'OVRS_EXCG_CD': KisStock.OVRS_EXCG_CD,
            'TR_CRCY_CD': KisStock.TR_CRCY_CD,
            'CTX_AREA_FK200': '',
            'CTX_AREA_NK200': ''
        }

        self._reset_holdings(('NYS', 'NAS', 'AMS'))

        # query the holdings
        is_all = False
        num_pages = 0
        while not is_all:
            num_pages = self._count_page(num_pages)
            res = self._getWrapper(us_holdings_inquiry_url, us_holdings_inquiry_headers, us_holdings_inquiry_params)

            if res.json()['rt_cd'] != '0':
                error_msg = 'us holdings query failed.'
                logger.error(error_msg)
                raise Exception(error_msg)

            # add holdings amount to corresponding stock
            stocks = res.json()['output1']
            for stock in stocks:
                stockkey = stock['ovrs_pdno']

                # if the stockkey is not enlisted in stockgrp_info, pass that stock because it's not the target of autoinv
                if stockkey not in self.stockgrp_info['stocks'].keys():
                    continue

                self.stockgrp_info['stocks'][stockkey]['holdings'] = int(stock['ovrs_cblc_qty'])

            # determine whether to continue querying
            tr_cont = res.headers['tr_cont']
            if tr_cont == 'F' or tr_cont == 'M':
                continue
            elif tr_cont == 'D' or tr_cont == 'E':
                is_all = True
            else:
                logger.error(f'Invalid tr_cont value ({tr_cont}) in querying holdings')
                raise ValueError

        for stockkey, stock in self.stockgrp_info['stocks'].items():
            if stock['holdings'] == 0 and self.ref_stockgrp_info['stocks'][stockkey].get('holdings', 0) > 0:
                logger.warning(f'{stockkey} is no longer held (holdings {self.ref_stockgrp_info["stocks"][stockkey]["holdings"]} -> 0)')

    def _reset_holdings(self, markets: tuple):
        for stock in self.stockgrp_info['stocks'].values():
            if stock['market'] in markets:
                stock['holdings'] = 0

    def _count_page(self, num_pages: int) -> int:
        # N.B. continuation requests are identical to the first one, so a server that keeps answering 'F'/'M' would loop forever
        num_pages += 1
        if num_pages > KisStock.MAX_HOLDINGS_PAGES:
            error_msg = f'holdings query exceeded {KisStock.MAX_HOLDINGS_PAGES} pages'
            logger.error(error_msg)
            raise Exception(error_msg)
        return num_pages

    def update_all(self):  # call order is crucial
        self._collect_prices()
        self._collect_holdings()
        self._derive_appraisement()  # after _collect_prices and _collect_holdings
        self._update_ca_invested()  # after _derive_appraisement


class CryptoStock(BaseStock):
    # Prices are queried directly from exchanges (no aggregator, no API key).
    # Each coin's price is the median over the venues that answered, so a single venue being down or off doesn't matter.
    # A missing venue entry means the venue doesn't list that coin (e.g. Upbit has no KRW-BNB).
    VENUE_SYMBS = {
        'BTC': {
            'coinbase': 'BTC-USD', 'kraken': ('XBTUSD', 'XXBTZUSD'), 'binanceus': 'BTCUSD',
            'upbit': 'KRW-BTC', 'bithumb': 'KRW-BTC', 'coinone': 'BTC', 'korbit': 'btc_krw'
        },
        'ETH': {
            'coinbase': 'ETH-USD', 'kraken': ('ETHUSD', 'XETHZUSD'), 'binanceus': 'ETHUSD',
            'upbit': 'KRW-ETH', 'bithumb': 'KRW-ETH', 'coinone': 'ETH', 'korbit': 'eth_krw'
        },
        'BNB': {
            'coinbase': 'BNB-USD', 'kraken': ('BNBUSD', 'BNBUSD'), 'binanceus': 'BNBUSD',
            'bithumb': 'KRW-BNB', 'coinone': 'BNB', 'korbit': 'bnb_krw'
        },
    }
    INTERNATIONAL_VENUES = ('coinbase', 'kraken', 'binanceus')  # quoted in USD
    DOMESTIC_VENUES = ('upbit', 'bithumb', 'coinone', 'korbit')  # quoted in KRW

    MIN_INTERNATIONAL_VENUES = 2  # price drives appraisement, so require agreement of at least two venues
    MAX_VENUE_DEVIATION = 0.02  # warn when a venue deviates from the median more than this
    REQUEST_TIMEOUT_IN_SECS = 10
    BASE_HEADER = {'content-type': 'application/json', 'User-Agent': 'vaCaCalculator'}

    def _get_json(self, URL, params=None):
        res = self._getWrapper(URL, CryptoStock.BASE_HEADER, params, timeout=CryptoStock.REQUEST_TIMEOUT_IN_SECS)
        res.raise_for_status()
        return res.json()

    def _venue_symbs(self, venue: str) -> dict:
        # {coin_symb: venue-specific symbol} for the target coins the venue lists
        return {
            coin_symb: CryptoStock.VENUE_SYMBS[coin_symb][venue]
            for coin_symb in self.stockgrp_info['stocks'].keys()
            if venue in CryptoStock.VENUE_SYMBS[coin_symb]
        }

    def _fetch_coinbase(self) -> dict:
        prices = {}
        for coin_symb, product_id in self._venue_symbs('coinbase').items():
            ticker = self._get_json(f'https://api.exchange.coinbase.com/products/{product_id}/ticker')
            prices[coin_symb] = float(ticker['price'])
        return prices

    def _fetch_kraken(self) -> dict:
        venue_symbs = self._venue_symbs('kraken')
        res_json = self._get_json(
            'https://api.kraken.com/0/public/Ticker',
            {'pair': ','.join([pair for pair, _ in venue_symbs.values()])}
        )
        if res_json['error']:
            raise ValueError(f'Kraken returned errors: {res_json["error"]}')
        # the result is keyed by Kraken's internal pair names (e.g. XBTUSD -> XXBTZUSD); 'c' is [last trade price, lot volume]
        return {coin_symb: float(res_json['result'][result_key]['c'][0]) for coin_symb, (_, result_key) in venue_symbs.items()}

    def _fetch_binanceus(self) -> dict:
        venue_symbs = self._venue_symbs('binanceus')
        tickers = self._get_json(
            'https://api.binance.us/api/v3/ticker/price',
            {'symbols': json.dumps(list(venue_symbs.values()), separators=(',', ':'))}
        )
        symb2price = {ticker['symbol']: float(ticker['price']) for ticker in tickers}
        return {coin_symb: symb2price[symbol] for coin_symb, symbol in venue_symbs.items()}

    def _fetch_upbit_style(self, URL: str, venue: str) -> dict:
        # Upbit and Bithumb share this schema. N.B. an unlisted market makes Upbit 404 the whole request, hence _venue_symbs
        venue_symbs = self._venue_symbs(venue)
        tickers = self._get_json(URL, {'markets': ','.join(venue_symbs.values())})
        market2price = {ticker['market']: float(ticker['trade_price']) for ticker in tickers}
        return {coin_symb: market2price[market] for coin_symb, market in venue_symbs.items()}

    def _fetch_upbit(self) -> dict:
        return self._fetch_upbit_style('https://api.upbit.com/v1/ticker', 'upbit')

    def _fetch_bithumb(self) -> dict:
        return self._fetch_upbit_style('https://api.bithumb.com/v1/ticker', 'bithumb')

    def _fetch_coinone(self) -> dict:
        prices = {}
        for coin_symb, symbol in self._venue_symbs('coinone').items():
            res_json = self._get_json(f'https://api.coinone.co.kr/public/v2/ticker_new/KRW/{symbol}')
            if res_json['result'] != 'success':
                raise ValueError(f'Coinone returned error code {res_json["error_code"]}')
            prices[coin_symb] = float(res_json['tickers'][0]['last'])
        return prices

    def _fetch_korbit(self) -> dict:
        venue_symbs = self._venue_symbs('korbit')
        res_json = self._get_json('https://api.korbit.co.kr/v2/tickers', {'symbol': ','.join(venue_symbs.values())})
        if not res_json['success']:
            raise ValueError('Korbit returned success=false')
        symb2price = {ticker['symbol']: float(ticker['close']) for ticker in res_json['data']}
        return {coin_symb: symb2price[symbol] for coin_symb, symbol in venue_symbs.items()}

    def _collect_venue_prices(self, venues: tuple) -> dict:
        # returns {coin_symb: {venue: price}}; a failing venue is skipped with a warning
        venue_prices = {coin_symb: {} for coin_symb in self.stockgrp_info['stocks'].keys()}
        for venue in venues:
            try:
                prices = getattr(self, f'_fetch_{venue}')()
            except (requests.RequestException, KeyError, IndexError, ValueError, TypeError) as e:
                logger.warning(f'Failed to collect crypto prices from {venue}, skipping it: {e!r}')
                continue

            for coin_symb, price in prices.items():
                if price <= 0:
                    logger.warning(f'{venue} returned a non-positive price for {coin_symb} ({price}), ignoring it')
                    continue
                venue_prices[coin_symb][venue] = price

        # warn about venues far off the median. median itself is robust to a single outlier, so they are kept
        for coin_symb, prices in venue_prices.items():
            if not prices:
                continue
            median_price = median(prices.values())
            for venue, price in prices.items():
                if abs(price / median_price - 1) > CryptoStock.MAX_VENUE_DEVIATION:
                    logger.warning(f'{coin_symb} price on {venue} ({price}) deviates more than '
                                   f'{CryptoStock.MAX_VENUE_DEVIATION:.0%} from the median ({median_price})')

        return venue_prices

    def _collect_international_prices(self):
        for coin_symb in self.stockgrp_info['stocks'].keys():
            if coin_symb not in CryptoStock.VENUE_SYMBS:
                error_msg = f'{coin_symb} is not supported. Add it to CryptoStock.VENUE_SYMBS'
                logger.error(error_msg)
                raise ValueError(error_msg)

        venue_prices = self._collect_venue_prices(CryptoStock.INTERNATIONAL_VENUES)
        for coin_symb, prices in venue_prices.items():
            if len(prices) < CryptoStock.MIN_INTERNATIONAL_VENUES:
                error_msg = (f'Only {len(prices)} venue(s) returned a USD price for {coin_symb} ({prices}); '
                             f'at least {CryptoStock.MIN_INTERNATIONAL_VENUES} are required')
                logger.error(error_msg)
                raise Exception(error_msg)

            self.stockgrp_info['stocks'][coin_symb]['price'] = median(prices.values())
            logger.info(f'{coin_symb} price: {self.stockgrp_info["stocks"][coin_symb]["price"]} USD (median of {prices})')

    def _collect_domestic_prices(self):
        # ROK prices are only used for the Kimchi premium, so missing ones are tolerated
        venue_prices = self._collect_venue_prices(CryptoStock.DOMESTIC_VENUES)
        for coin_symb, prices in venue_prices.items():
            stock = self.stockgrp_info['stocks'][coin_symb]
            stock.pop('priceROK', None)  # don't carry over the reference report's value
            if not prices:
                logger.warning(f'No domestic price collected for {coin_symb}')
                continue

            # apply exchange rate so that the ROK price is in USD
            stock['priceROK'] = median(prices.values()) / self.exchange_rate

    def _derive_kimchi_premium(self):
        for coin_symb, coin_value in self.stockgrp_info['stocks'].items():
            coin_value.pop('kimchi', None)  # don't carry over the reference report's value
            if 'price' not in coin_value.keys() or 'priceROK' not in coin_value.keys():
                logger.warning(f'Skipping Kimchi premium for {coin_symb}: price or priceROK is missing')
                continue

            coin_value['kimchi'] = float(coin_value['priceROK']) / float(coin_value['price'])
            if coin_value['kimchi'] > 1.05:
                logger.warning(
                    f'Kimchi premium for {coin_symb} is larger than 5% ({coin_value["kimchi"]}). '
                    'Consider using foreign exchanges'
                )

    def update_all(self):  # call order is crucial
        self._update_holdings()  # before _derive_appraisement and prices collection
        self._collect_international_prices()
        self._collect_domestic_prices()
        self._derive_kimchi_premium()  # after _collect_international_prices and _collect_domestic_prices
        self._derive_appraisement()
        self._update_ca_invested()  # after _derive_appraisement


class KrxStock(KisStock):
    # KRX gold spot "금 99.99_1kg" (KRW per gram). data.krx.co.kr now requires an API key, so the price comes from the KIS
    # domestic price inquiry, which lists the gold market under its KRX short code.
    # N.B. the 'M' prefix is required: '04020000' is answered with rt_cd '0' and a price of 0
    GOLD_ISCD = {'GLD': 'M04020000'}

    # unofficial Naver quote, used only to cross-check the KIS price
    CROSS_CHECK_URL = 'https://m.stock.naver.com/front-api/marketIndex/productDetail'
    CROSS_CHECK_PARAMS = {'category': 'metals', 'reutersCode': 'M04020000'}
    MAX_CROSS_CHECK_DEVIATION = 0.01  # warn when the cross-check price deviates from the KIS price more than this
    REQUEST_TIMEOUT_IN_SECS = 10

    def _collect_prices(self):
        price_inquiry_url = f'{KisStock.URL_BASE}/{KisStock.DOM_PRICE_INQUIRY_PATH}'
        price_inquiry_headers = copy.deepcopy(KisStock.BASE_HEADER)
        price_inquiry_headers['authorization'] = f'Bearer {self.access_token}'
        price_inquiry_headers['appkey'] = self.APP_KEY
        price_inquiry_headers['appsecret'] = self.APP_SECRET
        price_inquiry_headers['tr_id'] = KisStock.TR_ID_CURR_DOM_PRICE

        for stockkey, stock in self.stockgrp_info['stocks'].items():
            if stockkey not in KrxStock.GOLD_ISCD:
                error_msg = f'KrxStock currently supports only \'GLD\' as a stocks member. However {stockkey} given'
                logger.error(error_msg)
                raise Exception(error_msg)

            price_inquiry_params = {
                'fid_cond_mrkt_div_code': 'J',
                'fid_input_iscd': KrxStock.GOLD_ISCD[stockkey]
            }
            res = self._getWrapper(price_inquiry_url, price_inquiry_headers, price_inquiry_params,
                                   timeout=KrxStock.REQUEST_TIMEOUT_IN_SECS)

            # check success
            if res.json()['rt_cd'] != '0':
                error_msg = f'KRX gold price query for {stockkey} failed: {res.json()["msg1"]}'
                logger.error(error_msg)
                raise Exception(error_msg)

            price = float(res.json()['output']['stck_prpr'])
            if price <= 0:  # an unknown code is answered with a zero price rather than an error
                error_msg = f'KRX gold price query for {stockkey} returned a non-positive price ({price})'
                logger.error(error_msg)
                raise Exception(error_msg)

            stock['price'] = price
            logger.info(f'Current price of {stockkey} is {stock["price"]} {stock["currency"]}')

    def _cross_check_price(self):
        # informational only: any failure is logged and skipped
        for stockkey, stock in self.stockgrp_info['stocks'].items():
            try:
                res = self._getWrapper(KrxStock.CROSS_CHECK_URL, {'User-Agent': 'vaCaCalculator'}, KrxStock.CROSS_CHECK_PARAMS,
                                       timeout=KrxStock.REQUEST_TIMEOUT_IN_SECS)
                res.raise_for_status()
                check_price = float(res.json()['result']['closePrice'].replace(',', ''))
            except (requests.RequestException, KeyError, TypeError, ValueError, AttributeError) as e:
                logger.warning(f'Failed to cross-check the {stockkey} price, skipping it: {e!r}')
                continue

            if abs(check_price / stock['price'] - 1) > KrxStock.MAX_CROSS_CHECK_DEVIATION:
                logger.warning(f'{stockkey} price from KIS ({stock["price"]}) deviates more than '
                               f'{KrxStock.MAX_CROSS_CHECK_DEVIATION:.0%} from the cross-check price ({check_price})')
            else:
                logger.info(f'{stockkey} price cross-checked ({check_price})')

    def update_all(self):  # call order is crucial
        self._update_holdings()  # before _derive_appraisement and prices collection. holdings are manual (no KIS balance query)
        self._collect_prices()  # before _derive_appraisement
        self._cross_check_price()  # after _collect_prices
        self._derive_appraisement()
        self._update_ca_invested()  # after _derive_appraisement
