import json
import logging
import requests
import stockwrapper
import copy
from tabulate import tabulate
from datetime import datetime, timedelta


logger = logging.getLogger('autoinvestment_logger')


class Portfolio:
    BASE_CURRENCY = 'USD'
    EXCHANGERATE_LOOKUP_URL = 'https://www.koreaexim.go.kr/site/program/financial/exchangeJSON'
    EXCHANGERATE_LOOKUP_DATA = 'AP01'

    def __init__(self, *args) -> None:
        if (len(args) == 1 and isinstance(args[0], str)):  # simple constructor just for printing ref_report
            logger.debug('Portfolio simple constructor called')
            ref_report_fname = args[0]

            with open(ref_report_fname, 'r') as f:
                self.ref_report = json.load(f)
        elif (
               len(args) == 3 and
               isinstance(args[0], str) and
               isinstance(args[1], float) and
               isinstance(args[2], float)
        ):
            logger.debug('Portfolio constructor called')
            ref_report_fname = args[0]
            savingInKRW = args[1]
            savingInUSD = args[2]

            # open and decrypt secrets
            with open('secrets.json', 'r') as f_secret:
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

                # start verifying
                # sum of all weights of all stocks should be equal to 1.0
                stock_sum_of_weights = 0.0
                for stockgroup in self.ref_report['stockgroups'].values():
                    for stock in stockgroup['stocks'].values():
                        stock_sum_of_weights += stock['weight']
                assert round(stock_sum_of_weights, 4) == 1.0

                # instantiate this_report
                self.this_report = {}
        else:
            logger.error('wrong form of Portfolio constructor called')
            raise TypeError

    def _get_exchange_rate(self) -> float:
        querydate = datetime.today()
        empty_response = True
        while empty_response:
            resp = requests.get(
                Portfolio.EXCHANGERATE_LOOKUP_URL,
                params={'authkey': self.EXCHANGERATE_LOOKUP_AUTHKEY,
                        'searchdate': querydate.strftime('%Y%m%d'),
                        'data': Portfolio.EXCHANGERATE_LOOKUP_DATA}
            )

            # between 00:00--11:00 each day the API returns an empty list
            # in that case we should query the rate
            if len(resp.json()) != 0:
                empty_response = False
            else:
                querydate -= timedelta(days=1)

        for ele in resp.json()[-1:0:-1]:
            if ele['cur_unit'] == Portfolio.BASE_CURRENCY:
                try:
                    return float(ele['deal_bas_r'].replace(',', ''))  # key for trading standard rate
                except ValueError:
                    return 0.0

        return 0.0

    def _derive_total_appraisement(self):
        # do nothing if this_report['total_appraisement'] already exists
        if 'total_appraisement' not in self.this_report.keys():
            total_appraisement = 0.0
            for stockgroup in self.this_report['stockgroups'].values():
                for stock in stockgroup['stocks'].values():
                    total_appraisement += stock['appraisement']

            self.this_report['total_appraisement'] = total_appraisement

    def _print_report(self, report_to_print: dict):
        logger.debug('_print_report called')

        print(f'Strategy: {report_to_print["strategy"]}')

        # print total_appraisement if available
        if 'total_appraisement' in report_to_print.keys():
            print(f'Total Appraisement: {report_to_print["total_appraisement"]:.2f}')

        table_header = ('stock',
                        'priceUsd',
                        'holdings',
                        'appraisement',
                        'cumSumCaInvested',
                        'need2invest',
                        'need2investInUnits',
                        'targetweight',
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
                    f'{priceUsd:.4f}'  # if stockkey is KRW print up to 4th digit below decimal point
                    if stockkey == 'KRW' else
                    f'{priceUsd:.2f}'  # if priceUsd is a float print up to 2nd digit below decimal point
                    if isinstance(priceUsd, float) else priceUsd,
                    stock['holdings']
                    if 'holdings' in stock.keys() else 'N/A',
                    f'{stock["appraisement"]:.2f}'
                    if 'appraisement' in stock.keys() else 'N/A',
                    f'{stock["cumSumCaInvested"]:.2f}'
                    if 'cumSumCaInvested' in stock.keys() else 'N/A',
                    f'{stock["need2invest"]:.2f}'
                    if 'need2invest' in stock.keys() else 'N/A',
                    f'{stock["need2investInUnits"]}'
                    if 'need2investInUnits' in stock.keys() else 'N/A',
                    stock['weight'],
                    f'{stock["appraisement"] / report_to_print["total_appraisement"]:.2f}'
                    if 'appraisement' in stock.keys() and 'total_appraisement' in report_to_print.keys()
                    else 'N/A',
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
                if this_stock['currency'] == 'KRW':
                    actual_inv_increment /= self.exchange_rate

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
                stock['need2investCA'] = self.this_report['saving'] * stock['weight']

                if 'cumSumCaInvested' in stock.keys():
                    # in case cumSumCaInvested is given, ignore cumSumCaInvestedInKRW and cumSumCaInvestedInUSD
                    if 'cumSumCaInvestedInKRW' in stock.keys():
                        del stock['cumSumCaInvestedInKRW']
                    if 'cumSumCaInvestedInUSD' in stock.keys():
                        del stock['cumSumCaInvestedInUSD']
                else:
                    # in case of neither cumSumCaInvested, cumSumCaInvestedInKRW, nor cumSumCaInvestedInUSD exists
                    # use appraisement as previous cumSumCaInvested
                    if 'cumSumCaInvestedInKRW' not in stock.keys() and 'cumSumCaInvestedInUSD' not in stock.keys():
                        stock['cumSumCaInvested'] = stock['appraisement'] + stock['need2investCA']
                    # in case either cumSumCaInvestedInKRW or cumSumCaInvestedInUSD exists, use them instead
                    else:
                        stock['cumSumCaInvested'] = stock['need2investCA']
                        if 'cumSumCaInvestedInKRW' in stock.keys():
                            stock['cumSumCaInvested'] += stock['cumSumCaInvestedInKRW'] / self.exchange_rate
                            del stock['cumSumCaInvestedInKRW']
                        if 'cumSumCaInvestedInUSD' in stock.keys():
                            stock['cumSumCaInvested'] += stock['cumSumCaInvestedInUSD']
                            del stock['cumSumCaInvestedInUSD']

                stock['need2invest'] = stock['need2investCA']

    def _distribute_saving_VA(self):
        # do CA first
        self._distribute_saving_CA()

        # get VA amount for each stock
        for stockgroupkey, stockgroup in self.this_report['stockgroups'].items():
            for stockkey, stock in stockgroup['stocks'].items():
                # derive VA amount
                #   cumSumCaInvested: cumulative sum of CA invested amount.
                #                     this has nothing to do with actual investment because this is an ideal target to follow
                #   need2investCA: the CA amount needed to be invested in the corresponding stock
                #                  this also has nothing to do with actual investment
                #   need2investVA: difference between ideal target from current actual appraisement
                stock['need2investVA'] = stock['cumSumCaInvested'] + stock['need2investCA'] - stock['appraisement']

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
        self.this_report['saving'] = self.saving
        self.this_report['savingInKRW'] = self.savingInKRW
        self.this_report['savingInUSD'] = self.savingInUSD
        self.this_report['exchange_rate'] = self.exchange_rate

        # update all values of each stockgroup
        self.this_report['stockgroups'] = {}
        for stockgroupkey, stockgroup in self.ref_report['stockgroups'].items():
            if stockgroupkey == 'KIS':
                stockgroup_handler = stockwrapper.KisStock(
                    self.this_report['exchange_rate'],
                    copy.deepcopy(stockgroup)
                )

            elif stockgroupkey == 'CoinGecko':
                stockgroup_handler = stockwrapper.GeckoStock(
                    self.this_report['exchange_rate'],
                    copy.deepcopy(stockgroup)
                )

            elif stockgroupkey == 'KRX':
                stockgroup_handler = stockwrapper.KrxStock(
                    self.this_report['exchange_rate'],
                    copy.deepcopy(stockgroup)
                )

            else:
                stockgroup_handler = stockwrapper.BaseStock(
                    self.this_report['exchange_rate'],
                    copy.deepcopy(stockgroup)
                )

            stockgroup_handler.update_all()
            self.this_report['stockgroups'][stockgroupkey] = stockgroup_handler.get_stockgrp()

        # distribute saving according to the strategy
        if self.this_report['strategy'] == 'CA':
            self._distribute_saving_CA()
        elif self.this_report['strategy'] == 'VA':
            self._distribute_saving_VA()
        else:
            logger.error('Only supports CA and VA for strategy')
            raise NotImplementedError
        self._derive_units_to_invest()

        # derive cumulative deviation from need2invest
        self._derive_cum_inv_deviation()

        # derive total_appraisement
        self._derive_total_appraisement()

    def write_report_to_file(self, fname: str):
        with open(fname, 'w') as ofile:
            json.dump(self.this_report, ofile, indent=4)
