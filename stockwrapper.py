import logging
import requests
import copy
import json
import csv
import exchange_calendars as xcals
import pandas
from statistics import median
from datetime import datetime, timedelta
from io import StringIO


logger = logging.getLogger('autoinvestment_logger')


class BaseStock:
    def __init__(self, exchange_rate: float, stockgrp_info: dict):
        self.exchange_rate = exchange_rate
        self.stockgrp_info = stockgrp_info

    def _postWrapper(self, URL, headers=None, data=None):
        logger.debug(f'POSTing headers {headers} and data {data} to {URL}.')
        res = requests.post(URL, headers=headers, data=data)
        logger.debug(f'Got POST response: {res.text}')

        return res

    def _getWrapper(self, URL, headers=None, params=None):
        logger.debug(f'GETing headers {headers} and params {params} to {URL}.')
        res = requests.get(URL, headers=headers, params=params)
        logger.debug(f'Got GET response: {res.text}')

        return res

    def _update_holdings(self):
        for stockkey, stock in self.stockgrp_info['stocks'].items():
            if 'holdings' not in stock.keys():
                logger.error(f'{stockkey} does not have holdings item. this must be given to update holdings')
                raise ValueError

            # take account of actually invested units. add them up into holdings
            if 'actualInvestedInUnits' in stock.keys():
                stock['holdings'] += stock['actualInvestedInUnits']
                del stock['actualInvestedInUnits']

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
        self._update_holdings()  # before _derive_appraisement
        self._derive_appraisement()

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
    US_HOLDINGS_INQUIRY_PATH = 'uapi/overseas-stock/v1/trading/inquire-balance'

    # - TR_ID (service identifiers)
    TR_ID_CURR_DOM_PRICE = 'FHKST01010100'
    TR_ID_CURR_US_PRICE = 'HHDFS00000300'
    TR_ID_CURR_DOM_HOLDINGS_REAL = 'TTTC8434R'
    TR_ID_CURR_DOM_HOLDINGS_TEST = 'VTTC8434R'
    TR_ID_CURR_DOM_HOLDINGS = TR_ID_CURR_DOM_HOLDINGS_REAL
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

    # = US
    OVRS_EXCG_CD = 'NASD'  # NYS + NAS
    TR_CRCY_CD = 'USD'  # Currency for the trading

    def __init__(self, exchange_rate: float, stockgrp_info: dict):
        super().__init__(exchange_rate, stockgrp_info)

        with open('secrets.json', 'r') as f_secret:
            f_secret_loaded = json.load(f_secret)
            self.APP_KEY = f_secret_loaded['KisSecrets']['APP_KEY']
            self.APP_SECRET = f_secret_loaded['KisSecrets']['APP_SECRET']

        self.BASE_BODY = {
            'grant_type': 'client_credentials',
            'appkey': self.APP_KEY,
            'appsecret': self.APP_SECRET
        }
        self.access_token = None

    def _issue_access_token(self):
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

    def _discard_access_token(self):
        if self.access_token is None:
            return  # access_token has never been issued or already discarded

        access_token_discard_headers = copy.deepcopy(KisStock.BASE_HEADER)
        access_token_discard_body = copy.deepcopy(self.BASE_BODY)
        access_token_discard_body['token'] = self.access_token
        access_token_discard_path = 'oauth2/revokeP'
        access_token_discard_url = f'{KisStock.URL_BASE}/{access_token_discard_path}'
        self._postWrapper(
            access_token_discard_url,
            access_token_discard_headers,
            access_token_discard_body
        )
        self.access_token = None

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

        # query the holdings
        is_all = False
        while not is_all:
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

        # query the holdings
        is_all = False
        while not is_all:
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

    def update_all(self):  # call order is crucial
        self._issue_access_token()  # before _collect_prices, and _collect_holdings_and_invested
        self._collect_prices()  # before _discard_access_token
        self._collect_holdings()  # before _discard_access_token
        self._derive_appraisement()  # after _collect_prices and _collect_holdings
        self._discard_access_token()


class GeckoStock(BaseStock):
    BASE_CURRENCY = 'usd'
    SYMB2ID_DICT = {
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'BNB': 'binancecoin'
    }
    ID2SYMB_DICT = {
        'bitcoin': 'BTC',
        'ethereum': 'ETH',
        'binancecoin': 'BNB'
    }
    ROK_EXCHANGE_IDS = ('bithumb', 'upbit', 'korbit', 'coinone')

    URL_BASE = 'https://api.coingecko.com/api/v3'
    BASE_HEADER = {'content-type': 'application/json'}
    SIMPLE_PRICE_INQUIRY_PATH = '/simple/price'
    EXCHANGEWISE_PRICE_INQUIRY_PATH_HEADER = '/exchanges/'

    def _collect_international_prices(self):
        coin_symbs = self.stockgrp_info['stocks'].keys()

        international_price_inquiry_url = f'{GeckoStock.URL_BASE}{GeckoStock.SIMPLE_PRICE_INQUIRY_PATH}'
        international_price_inquiry_params = {
            'ids': ','.join([GeckoStock.SYMB2ID_DICT[coin_symb] for coin_symb in coin_symbs]),
            'vs_currencies': GeckoStock.BASE_CURRENCY
        }
        res = self._getWrapper(
            international_price_inquiry_url,
            GeckoStock.BASE_HEADER,
            international_price_inquiry_params
        )

        # extract prices from the queries
        price_results = res.json()
        for coin_id in price_results.keys():
            self.stockgrp_info['stocks'][GeckoStock.ID2SYMB_DICT[coin_id]]['price'] = \
                float(price_results[coin_id][GeckoStock.BASE_CURRENCY])

    def _collect_domestic_prices(self):
        # prepare exchange-wise price queries
        domestic_price_inquiry_url_head = f'{GeckoStock.URL_BASE}{GeckoStock.EXCHANGEWISE_PRICE_INQUIRY_PATH_HEADER}'

        # query ROK prices for Kimchi premium
        ROK_prices = {}  # dict for getting the median of the prices

        # for each target ROK exchanges
        for ROK_exchange_id in GeckoStock.ROK_EXCHANGE_IDS:
            coin_symbs = self.stockgrp_info['stocks'].keys()
            domestic_price_inquiry_url = domestic_price_inquiry_url_head + f'{ROK_exchange_id}/tickers'
            domestic_price_inquiry_params = {
                'id': ROK_exchange_id,
                'coin_ids': ','.join([GeckoStock.SYMB2ID_DICT[coin_symb] for coin_symb in coin_symbs]),
            }
            res = self._getWrapper(
                domestic_price_inquiry_url,
                GeckoStock.BASE_HEADER,
                domestic_price_inquiry_params
            )
            ROK_tickers = res.json()['tickers']
            for ROK_ticker in ROK_tickers:
                if ROK_ticker['base'] not in coin_symbs:
                    error_msg = f'Queired cryptocurrency ({ROK_ticker["base"]}) does not match any of '
                    f'target cryptocurrencies ({coin_symbs})'
                    logger.error(error_msg)
                    raise Exception(error_msg)

                if ROK_ticker['target'] != 'KRW':
                    # ignore exchange pairs that does not have KRW as the target currency
                    continue

                ROK_price = float(ROK_ticker['last'])
                if ROK_ticker['base'] in ROK_prices.keys():
                    # if there's already values for the given key
                    ROK_prices[ROK_ticker['base']].append(ROK_price)
                else:
                    # when there is no such a key, add a list as a value
                    ROK_prices[ROK_ticker['base']] = [ROK_price]

        # for each cryptocurrency, take the median as the price to be registered to stockgrp_info
        # and apply exchange rate so that the ROK price is in GeckoStock.BASE_CURRENCY
        for coin_symb, ROK_prices_list in ROK_prices.items():
            self.stockgrp_info['stocks'][coin_symb]['priceROK'] = median(ROK_prices_list) / self.exchange_rate

    def _derive_kimchi_premium(self):
        for coin_symb, coin_value in self.stockgrp_info['stocks'].items():
            if 'price' not in coin_value.keys():
                error_msg = f'price of a coin should be given in advance to derive Kimchi preimum, but got {coin_value["price"]}'
                logger.error(error_msg)
                raise Exception

            if 'priceROK' not in coin_value.keys():
                error_msg = \
                    f'priceROK of a coin should be given in advance to derive Kimchi preimum, but got {coin_value["priceROK"]}'
                logger.error(error_msg)
                raise Exception

            coin_value['kimchi'] = float(coin_value['priceROK']) / float(coin_value['price'])
            if coin_value['kimchi'] > 1.05:
                logger.warning(
                    f'Kimchi premium for {coin_symb} is larger than 5% ({coin_value["kimchi"]}). '
                    'Consider using forein exchanges'
                )

    def update_all(self):  # call order is crucial
        self._update_holdings()  # before _derive_appraisement and prices collection
        self._collect_international_prices()
        self._collect_domestic_prices()
        self._derive_kimchi_premium()  # after _collect_international_prices and _collect_domestic_prices
        self._derive_appraisement()


class KrxStock(BaseStock):
    OTP_GENERATE_URL = 'http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd'
    OTP_GENERATE_PAYLOAD_BASE = {
        'locale': 'en_US',
        'isuCd': 'KRD040200002',
        'share': '1',
        'money': '1',
        'csvxls_isNo': 'false',
        'name': 'fileDown',
        'url': 'dbms/MDC/STAT/standard/MDCSTAT15001'
    }
    PRICE_CSV_DOWNLOAD_URL = 'http://data.krx.co.kr/comm/fileDn/download_csv/download.cmd'
    PRICE_CSV_ENCODING = 'euc-kr'
    TRADING_DAY_LOOKUP_WINDOW_IN_DAYS = 10

    def _get_recent_trading_dates(self) -> pandas.DatetimeIndex:
        # instantiate xcals for KRX
        xkrx = xcals.get_calendar('XKRX')

        # query window-days of time for trading days and get the last trading day from the result
        today = datetime.today()
        window_from_date = (today - timedelta(days=KrxStock.TRADING_DAY_LOOKUP_WINDOW_IN_DAYS)).strftime('%Y-%m-%d')
        window_to_date = today.strftime('%Y-%m-%d')

        return xkrx.sessions_in_range(window_from_date, window_to_date)  # Caution not %Y-%m-%d!

    def _collect_otp(self):
        # complete OTP request payload
        otp_requeust_payload = copy.deepcopy(KrxStock.OTP_GENERATE_PAYLOAD_BASE)
        recent_trading_days = self._get_recent_trading_dates()
        otp_requeust_payload['strtDd'] = recent_trading_days[0].strftime('%Y%m%d')  # Caution not %Y-%m-%d
        otp_requeust_payload['endDd'] = recent_trading_days[-1].strftime('%Y%m%d')

        # get OTP from the response
        otp_resp = self._postWrapper(KrxStock.OTP_GENERATE_URL, None, otp_requeust_payload)
        self.otp = otp_resp.text.strip()

    def _collect_prices(self):
        # complete request for download.cmd
        download_request_headers = {'referer': KrxStock.OTP_GENERATE_URL}
        download_request_payload = {'code': self.otp}

        # get a CSV containing the price from the response
        download_resp = self._postWrapper(
            KrxStock.PRICE_CSV_DOWNLOAD_URL,
            download_request_headers,
            download_request_payload
        )
        price_csv = StringIO(download_resp.content.decode(KrxStock.PRICE_CSV_ENCODING))
        price_csv_parsed = csv.DictReader(price_csv)

        # access stockgrp_info element
        for stockkey, stock in self.stockgrp_info['stocks'].items():
            if stockkey == 'GLD':
                # extract price from CSV. We only need the most recent price (the top row)
                for price_record in price_csv_parsed:
                    stock['price'] = float(price_record['종가'])
                    logger.info(f'Current price of {stockkey} is {stock["price"]} {stock["currency"]}')
                    break  # for the case we have more than one record (this happens when it has just passed midnight)
            else:
                error_msg = f'KrxStock currently supports only \'GLD\' as a stocks member. However {stockkey} given'
                logger.error(error_msg)
                raise Exception(error_msg)

    def update_all(self):  # call order is crucial
        self._update_holdings()  # before _derive_appraisement and prices collection
        self._collect_otp()  # before _collect_prices
        self._collect_prices()  # before _derive_appraisement
        self._derive_appraisement()
