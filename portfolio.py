import json
import logging
import os
import requests
import stockwrapper
from tabulate import tabulate
from datetime import datetime, timedelta


logger = logging.getLogger('autoinvestment_logger')


class Portfolio:
    BASE_CURRENCY = 'USD'
    EXCHANGERATE_LOOKUP_URL = 'https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON'
    EXCHANGERATE_LOOKUP_DATA = 'AP01'
    # resolve relative to this module so the tool can be run from any cwd
    EXCHANGERATE_CERT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'koreaexim.pem')
    # stock keys renamed when rebalancing was introduced. old reports are migrated on load
    LEGACY_STOCK_KEYS = {
        'weight': 'targ_weight',
        'cumSumCaInvested': 'cumSumIdealInvested',
        'cumSumCaInvestedInKRW': 'cumSumIdealInvestedInKRW',
        'cumSumCaInvestedInUSD': 'cumSumIdealInvestedInUSD',
    }

    def __init__(self, *args) -> None:
        # constructor 1: simple constructor just for printing ref_report
        if (len(args) == 1 and isinstance(args[0], str)):
            logger.debug('Portfolio simple constructor called')
            ref_report_fname = args[0]

            with open(ref_report_fname, 'r') as f:
                self.ref_report = json.load(f)
            self._migrate_legacy_keys(self.ref_report)
        # constructor 2: regular constructor for deriving new reports
        elif (
               len(args) == 5 and
               isinstance(args[0], str) and
               isinstance(args[1], str) and
               isinstance(args[2], str) and
               isinstance(args[3], float) and
               isinstance(args[4], float)
        ):
            logger.debug('Portfolio constructor called')
            ref_report_fname = args[0]
            self.secrets_fname = args[1]
            self.tokens_fname = args[2]
            savingInKRW = args[3]
            savingInUSD = args[4]

            # open and decrypt secrets
            with open(self.secrets_fname, 'r') as f_secret:
                self.EXCHANGERATE_LOOKUP_AUTHKEY = json.load(f_secret)['ExchangerateSecrets']['AUTH_KEY']

            # open and parse reference report file
            with open(ref_report_fname, 'r') as f:
                # first get the exchange rate to convert savingKRW to USD
                self.exchange_rate = self._get_exchange_rate()
                self.savingInKRW = savingInKRW
                self.savingInUSD = savingInUSD
                self.saving = savingInKRW / self.exchange_rate + savingInUSD

                # refer to root_ref_report.json for report format
                self.ref_report = json.load(f)
                self._migrate_legacy_keys(self.ref_report)

                # start verifying
                # sum of all target weights of all stocks should be equal to 1.0
                stock_sum_of_weights = 0.0
                for stockgroup in self.ref_report['stockgroups'].values():
                    for stock in stockgroup['stocks'].values():
                        stock_sum_of_weights += stock['targ_weight']
                assert round(stock_sum_of_weights, 4) == 1.0
                self._validate_rebalance()

                # instantiate this_report
                self.this_report = {}
        else:
            logger.error('wrong form of Portfolio constructor called')
            raise TypeError

    @staticmethod
    def _migrate_legacy_keys(report: dict):
        # rename legacy stock keys in place, keeping the key order
        for stockgroup in report['stockgroups'].values():
            for stockkey, stock in list(stockgroup['stocks'].items()):
                for old_key, new_key in Portfolio.LEGACY_STOCK_KEYS.items():
                    if old_key in stock.keys() and new_key in stock.keys():
                        error_msg = f'{stockkey} has both {old_key} (legacy) and {new_key}. keep only {new_key}'
                        logger.error(error_msg)
                        raise KeyError(error_msg)

                stockgroup['stocks'][stockkey] = {Portfolio.LEGACY_STOCK_KEYS.get(key, key): value for key, value in stock.items()}

    def _validate_rebalance(self):
        rebalance = self.ref_report.get('rebalance', False)
        if not isinstance(rebalance, bool):
            error_msg = f'rebalance must be true or false, but {rebalance!r} given'
            logger.error(error_msg)
            raise ValueError(error_msg)

        if rebalance:
            steps_left = self.ref_report.get('rebalanceStepsLeft')
            # N.B. bool is a subclass of int
            if not isinstance(steps_left, int) or isinstance(steps_left, bool) or steps_left < 1:
                error_msg = f'rebalance is on, so rebalanceStepsLeft must be an integer >= 1, but {steps_left!r} given'
                logger.error(error_msg)
                raise ValueError(error_msg)

    def _get_exchange_rate(self) -> float:
        querydate = datetime.today()
        empty_response = True
        while empty_response:
            resp = requests.get(
                Portfolio.EXCHANGERATE_LOOKUP_URL,
                params={'authkey': self.EXCHANGERATE_LOOKUP_AUTHKEY,
                        'searchdate': querydate.strftime('%Y%m%d'),
                        'data': Portfolio.EXCHANGERATE_LOOKUP_DATA},
                verify=Portfolio.EXCHANGERATE_CERT_PATH
            )

            # between 00:00--11:00 each day the API returns an empty list
            # in that case we should query the rate
            if len(resp.json()) != 0:
                empty_response = False
            else:
                querydate -= timedelta(days=1)

        for ele in reversed(resp.json()):
            if ele.get('cur_unit') == Portfolio.BASE_CURRENCY:
                try:
                    return float(ele['deal_bas_r'].replace(',', ''))  # key for trading standard rate
                except ValueError:
                    error_msg = f'invalid exchange rate for {Portfolio.BASE_CURRENCY}: {ele["deal_bas_r"]}'
                    logger.error(error_msg)
                    raise ValueError(error_msg)

        error_msg = f'no exchange rate for {Portfolio.BASE_CURRENCY} in the response: {resp.json()}'
        logger.error(error_msg)
        raise ValueError(error_msg)

    def _days_since_ref_report(self) -> int:
        if 'date' not in self.ref_report.keys():
            error_msg = 'the reference report has no date, needed to accrue interest. add "date": "YYYY-MM-DD" (the day it was derived)'
            logger.error(error_msg)
            raise KeyError(error_msg)

        days = (datetime.strptime(self.this_report['date'], '%Y-%m-%d') - datetime.strptime(self.ref_report['date'], '%Y-%m-%d')).days
        if days < 0:
            error_msg = f'the reference report date {self.ref_report["date"]} is in the future'
            logger.error(error_msg)
            raise ValueError(error_msg)

        return days

    def _derive_total_appraisement(self):
        # do nothing if this_report['total_appraisement'] already exists
        if 'total_appraisement' not in self.this_report.keys():
            total_appraisement = 0.0
            for stockgroup in self.this_report['stockgroups'].values():
                for stock in stockgroup['stocks'].values():
                    total_appraisement += stock['appraisement']

            self.this_report['total_appraisement'] = total_appraisement

    def _derive_cur_weight(self):
        # current weight of each stock at derivation time (before this period's trades)
        for stockgroup in self.this_report['stockgroups'].values():
            for stock in stockgroup['stocks'].values():
                if self.this_report['total_appraisement'] != 0:
                    stock['cur_weight'] = stock['appraisement'] / self.this_report['total_appraisement']
                else:
                    stock['cur_weight'] = 0.0

    def _print_report(self, report_to_print: dict):
        logger.debug('_print_report called')

        # seed reports have no total_appraisement. only derived reports can be printed
        if 'total_appraisement' not in report_to_print.keys():
            error_msg = 'report has no total_appraisement. only derived reports can be printed'
            logger.error(error_msg)
            raise KeyError(error_msg)

        print(f'Strategy: {report_to_print["strategy"]}')
        if report_to_print.get('rebalance', False):
            print(f'Rebalance: on, {report_to_print["rebalanceStepsLeft"]} step(s) left')
        print(f'Total Appraisement: {report_to_print["total_appraisement"]:.2f}')

        table_header = ('stock',
                        'priceUsd',
                        'holdings',
                        'appraisement',
                        'cumSumIdealInvested',
                        'need2invest',
                        'need2investInUnits',
                        'targ_weight',
                        'cur_weight',
                        'cum_inv_deviation'
                        )
        table_data = []
        for stockgroupkey, stockgroup in report_to_print['stockgroups'].items():
            for stockkey, stock in stockgroup['stocks'].items():
                # get priceUsd value prepared
                priceUsd = 'N/A'
                if 'price' in stock.keys():
                    priceUsd = stock['price']
                    if stock['currency'] == 'KRW':
                        priceUsd /= report_to_print['exchange_rate']  # use exchange rate in the report itself

                table_data.append([
                    stockkey,
                    priceUsd  # if no priceUsd print it as is
                    if priceUsd == 'N/A' else
                    f'{priceUsd:.4f}'  # if stockkey is KRW print up to 4th digit below decimal point
                    if isinstance(priceUsd, float) and stock['currency'] == 'KRW' else
                    f'{priceUsd:.2f}',  # else up to 2nd digit below decimal point
                    stock['holdings']
                    if 'holdings' in stock.keys() else 'N/A',
                    f'{stock["appraisement"]:.2f}'
                    if 'appraisement' in stock.keys() else 'N/A',
                    f'{stock["cumSumIdealInvested"]:.2f}'
                    if 'cumSumIdealInvested' in stock.keys() else 'N/A',
                    f'{stock["need2invest"]:.2f}'
                    if 'need2invest' in stock.keys() else 'N/A',
                    f'{stock["need2investInUnits"]}'
                    if 'need2investInUnits' in stock.keys() else 'N/A',
                    stock['targ_weight'],
                    f'{stock["cur_weight"]:.2f}'
                    if 'cur_weight' in stock.keys() else  # reports derived before cur_weight was stored
                    f'{stock["appraisement"] / report_to_print["total_appraisement"]:.2f}'
                    if report_to_print["total_appraisement"] != 0 else '0',
                    f'{stock["cum_inv_deviation"]:.2f}'
                    if 'cum_inv_deviation' in stock.keys() else 'N/A',
                ])

                # print fractional units for cryptocurrencies
                if stockgroupkey == 'CoinGecko':
                    if 'holdings' in stock.keys():
                        table_data[-1][2] = f'{stock["holdings"]:.8f}'
                    if 'need2investInUnits' in stock.keys():
                        table_data[-1][-4] = f'{stock["need2investInUnits"]:.8f}'

        print(tabulate(table_data,
                       headers=table_header,
                       tablefmt='pretty',
                       colalign=('left',),
                       numalign='right'
                       ))

    def _derive_cum_inv_deviation(self):
        # get the deviation between need2invest and actual investment in terms of ref_report
        for stockgroupkey in self.ref_report['stockgroups'].keys():
            ref_stockgroup = self.ref_report['stockgroups'][stockgroupkey]
            this_stockgroup = self.this_report['stockgroups'][stockgroupkey]

            for stockkey in ref_stockgroup['stocks'].keys():
                ref_stock = ref_stockgroup['stocks'][stockkey]
                this_stock = this_stockgroup['stocks'][stockkey]

                # for holdings
                if 'holdings' in ref_stock.keys():
                    actualInvestedInUnits = this_stock['holdings'] - ref_stock['holdings']
                else:
                    actualInvestedInUnits = 0

                # for prices
                if 'price' in ref_stock.keys():
                    actual_inv_increment = ref_stock['price'] * actualInvestedInUnits
                else:  # if ref_stock does not have price info, use that of this_stock instead
                    actual_inv_increment = this_stock['price'] * actualInvestedInUnits
                # if currency is KRW divide actual_inv_increment by exchange_rate
                # N.B. use ref_report's exchange rate, the one ref_report's need2invest was derived with
                if this_stock['currency'] == 'KRW':
                    actual_inv_increment /= self.ref_report['exchange_rate']

                if 'need2invest' in ref_stock.keys():
                    inv_deviation = ref_stock['need2invest'] - actual_inv_increment
                else:
                    inv_deviation = 0.0  # assume inv_deviation == 0 if ref_report has no record of need2invest

                # add up the difference between need2invest and added_investment to cum_inv_deviation
                if 'cum_inv_deviation' in ref_stock.keys():
                    this_stock['cum_inv_deviation'] = ref_stock['cum_inv_deviation'] + inv_deviation
                else:
                    # assume cum_inv_deviation of ref_report is 0 if not available
                    this_stock['cum_inv_deviation'] = inv_deviation

    def _derive_units_to_invest(self):
        # get the number of units to invest for each stock
        for stockgroupkey, stockgroup in self.this_report['stockgroups'].items():
            for stockkey, stock in stockgroup['stocks'].items():
                if stock['currency'] == 'KRW':
                    if stockgroupkey == 'CoinGecko':  # Cryptocurrencies can be fractionally invested
                        stock['need2investInUnits'] = \
                            stock['need2invest'] / (stock['price'] / self.this_report['exchange_rate'])
                    else:
                        stock['need2investInUnits'] = \
                            round(stock['need2invest'] / (stock['price'] / self.this_report['exchange_rate']))
                elif stock['currency'] == 'USD':
                    if stockgroupkey == 'CoinGecko':  # Cryptocurrencies can be fractionally invested
                        stock['need2investInUnits'] = stock['need2invest'] / stock['price']
                    else:
                        stock['need2investInUnits'] = round(stock['need2invest'] / stock['price'])
                else:
                    logger.error(f'only supports KRW and USD as currency, but {stock["currency"]} given')
                    raise NotImplementedError

    def _distribute_saving_CA(self):
        # get CA amount for each stock
        for stockgroupkey, stockgroup in self.this_report['stockgroups'].items():
            for stockkey, stock in stockgroup['stocks'].items():
                stock['need2investCA'] = self.this_report['saving'] * stock['targ_weight']
                # need2investRebal copied over from a rebalancing ref_report must not advance the next cumSumIdealInvested
                if 'need2investRebal' in stock.keys():
                    del stock['need2investRebal']

                if 'cumSumIdealInvested' in stock.keys():
                    # in case cumSumIdealInvested is given, ignore cumSumIdealInvestedInKRW and cumSumIdealInvestedInUSD
                    if 'cumSumIdealInvestedInKRW' in stock.keys():
                        del stock['cumSumIdealInvestedInKRW']
                    if 'cumSumIdealInvestedInUSD' in stock.keys():
                        del stock['cumSumIdealInvestedInUSD']
                else:
                    # in case of neither cumSumIdealInvested, cumSumIdealInvestedInKRW, nor cumSumIdealInvestedInUSD exists
                    # use appraisement as previous cumSumIdealInvested
                    # N.B. this route is only for the 1st report because reports afterward all have cumSumIdealInvested
                    if 'cumSumIdealInvestedInKRW' not in stock.keys() and 'cumSumIdealInvestedInUSD' not in stock.keys():
                        stock['cumSumIdealInvested'] = stock['appraisement'] + stock['need2investCA']
                    # in case either cumSumIdealInvestedInKRW or cumSumIdealInvestedInUSD exists, use them instead
                    else:
                        stock['cumSumIdealInvested'] = stock['need2investCA']
                        if 'cumSumIdealInvestedInKRW' in stock.keys():
                            stock['cumSumIdealInvested'] += stock['cumSumIdealInvestedInKRW'] / self.exchange_rate
                            del stock['cumSumIdealInvestedInKRW']
                        if 'cumSumIdealInvestedInUSD' in stock.keys():
                            stock['cumSumIdealInvested'] += stock['cumSumIdealInvestedInUSD']
                            del stock['cumSumIdealInvestedInUSD']

                stock['need2invest'] = stock['need2investCA']

    def _distribute_saving_rebal(self, steps_left: int):
        # during rebalancing need2investRebal replaces need2investCA: it deploys the saving by targ_weight and closes
        # 1/steps_left of the gap to targ_weight, so the gap is closed after steps_left reports whatever the saving is.
        # the gap is measured on what each strategy steers to:
        #   VA: cumSumIdealInvested (ideal trajectory). need2investVA = cumSumIdealInvested + need2investRebal - appraisement
        #       turns the rebalanced trajectory into trades at current prices. measuring on appraisement would correct
        #       price deviations twice and leave the trajectory off target after rebalancing.
        #   CA: appraisement. CA never steers holdings to cumSumIdealInvested, so its shares say nothing about the portfolio
        # N.B. the gaps sum to zero, so the sum of need2investRebal is the saving
        if self.this_report['strategy'] == 'VA':
            basis_key = 'cumSumIdealInvested'
        else:
            basis_key = 'appraisement'

        basis_total = 0.0
        for stockgroup in self.this_report['stockgroups'].values():
            for stock in stockgroup['stocks'].values():
                basis_total += stock[basis_key]

        for stockgroupkey, stockgroup in self.this_report['stockgroups'].items():
            for stockkey, stock in stockgroup['stocks'].items():
                stock['need2investRebal'] = \
                    self.this_report['saving'] * stock['targ_weight'] + \
                    (stock['targ_weight'] * basis_total - stock[basis_key]) / steps_left
                # need2investCA copied over from ref_report must not advance the next cumSumIdealInvested
                if 'need2investCA' in stock.keys():
                    del stock['need2investCA']

                stock['need2invest'] = stock['need2investRebal']

    def _distribute_saving_VA(self, increment_key: str):
        # get VA amount for each stock. _distribute_saving_CA or _distribute_saving_rebal must be called first
        for stockgroupkey, stockgroup in self.this_report['stockgroups'].items():
            for stockkey, stock in stockgroup['stocks'].items():
                # derive VA amount
                #   cumSumIdealInvested: cumulative sum of ideal invested amount (need2investCA, or need2investRebal while rebalancing)
                #                        this has nothing to do with actual investment because this is an ideal target to follow
                #   increment_key: need2investCA (or need2investRebal) for this period, the ideal increment of the trajectory
                #                  this also has nothing to do with actual investment
                #   need2investVA: difference between ideal target from current actual appraisement
                stock['need2investVA'] = stock['cumSumIdealInvested'] + stock[increment_key] - stock['appraisement']

                # overwrite need2invest as need2investVA
                stock['need2invest'] = stock['need2investVA']

    def print_ref_report(self):
        logger.debug('print_ref_report called')
        self._print_report(self.ref_report)

    def print_this_report(self):
        logger.debug('print_report called')
        self._print_report(self.this_report)

    def distribute_saving(self):
        ''' all this distributed saving will be written on this_report '''

        # derive common stuffs
        self.this_report['strategy'] = self.ref_report['strategy']
        # rebalance in ref_report means this report is a rebalancing step. one step is consumed per derived report
        rebalancing = self.ref_report.get('rebalance', False)
        if rebalancing:
            self.this_report['rebalanceStepsLeft'] = self.ref_report['rebalanceStepsLeft'] - 1
            self.this_report['rebalance'] = self.this_report['rebalanceStepsLeft'] > 0
        else:
            self.this_report['rebalanceStepsLeft'] = self.ref_report.get('rebalanceStepsLeft', 0)
            self.this_report['rebalance'] = False
        self.this_report['saving'] = self.saving
        self.this_report['savingInKRW'] = self.savingInKRW
        self.this_report['savingInUSD'] = self.savingInUSD
        self.this_report['exchange_rate'] = self.exchange_rate
        self.this_report['date'] = datetime.today().strftime('%Y-%m-%d')

        # update all values of each stockgroup
        self.this_report['stockgroups'] = {}
        for stockgroupkey, stockgroup in self.ref_report['stockgroups'].items():
            if stockgroupkey == 'KIS':
                stockgroup_handler = stockwrapper.KisStock(
                    self.this_report['exchange_rate'],
                    self.ref_report['exchange_rate'],
                    self.secrets_fname,
                    self.tokens_fname,
                    stockgroup
                )

            elif stockgroupkey == 'CoinGecko':  # historical key name kept for report compatibility; prices come from exchanges
                stockgroup_handler = stockwrapper.CryptoStock(
                    self.this_report['exchange_rate'],
                    self.ref_report['exchange_rate'],
                    stockgroup
                )

            elif stockgroupkey == 'KRX':  # gold spot price comes through KIS, hence the secrets
                stockgroup_handler = stockwrapper.KrxStock(
                    self.this_report['exchange_rate'],
                    self.ref_report['exchange_rate'],
                    self.secrets_fname,
                    self.tokens_fname,
                    stockgroup
                )

            elif stockgroupkey == 'KDB':  # USD time deposits, accruing interest since the ref report
                stockgroup_handler = stockwrapper.KdbDepositStock(
                    self.this_report['exchange_rate'],
                    self.ref_report['exchange_rate'],
                    stockgroup,
                    self._days_since_ref_report()
                )

            elif stockgroupkey == 'PENSION_DEPOSIT':  # KRW 원리금보장 products in a pension account, accruing interest
                stockgroup_handler = stockwrapper.PensionDepositStock(
                    self.this_report['exchange_rate'],
                    self.ref_report['exchange_rate'],
                    stockgroup,
                    self._days_since_ref_report()
                )

            else:
                stockgroup_handler = stockwrapper.BaseStock(
                    self.this_report['exchange_rate'],
                    self.ref_report['exchange_rate'],
                    stockgroup
                )

            stockgroup_handler.update_all()
            self.this_report['stockgroups'][stockgroupkey] = stockgroup_handler.get_stockgrp()

        # derive total_appraisement and current weights (rebalancing under CA needs total_appraisement)
        self._derive_total_appraisement()
        self._derive_cur_weight()

        # distribute saving according to the strategy
        if self.this_report['strategy'] not in ('CA', 'VA'):
            logger.error('Only supports CA and VA for strategy')
            raise NotImplementedError

        # the ideal increment: need2investCA, replaced by need2investRebal while rebalancing
        if rebalancing:
            self._distribute_saving_rebal(self.ref_report['rebalanceStepsLeft'])
            increment_key = 'need2investRebal'
        else:
            self._distribute_saving_CA()
            increment_key = 'need2investCA'

        if self.this_report['strategy'] == 'VA':
            self._distribute_saving_VA(increment_key)
        self._derive_units_to_invest()

        # derive cumulative deviation from need2invest
        self._derive_cum_inv_deviation()

    def write_report_to_file(self, fname: str):
        with open(fname, 'w') as ofile:
            json.dump(self.this_report, ofile, indent=4)
