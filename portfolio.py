import json
import logging
import requests
import stockwrapper
from tabulate import tabulate
from datetime import datetime, timedelta


logger = logging.getLogger('autoinvestment_logger')


class Portfolio:
    BASE_CURRENCY = 'USD'
    EXCHANGERATE_LOOKUP_URL = 'https://www.koreaexim.go.kr/site/program/financial/exchangeJSON'
    EXCHANGERATE_LOOKUP_DATA = 'AP01'

    def __init__(self, ref_report_fname: str, savingInKRW: float, savingInUSD: float = 0.0):
        logger.debug('Portfolio constructor called')

        # open and decrypt secrets
        with open('secrets.json', 'r') as f_secret:
            self.EXCHANGERATE_LOOKUP_AUTHKEY = json.load(f_secret)['ExchangerateSecrets']['AUTH_KEY']

        # open and parse reference report file
        with open(ref_report_fname, 'r') as f:
            # first get the exchange rate to convert savingKRW to USD
            self.exchange_rate = self._get_exchange_rate()
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

        # get total_appraisement for printing
        self._derive_total_appraisement()
        print(f'Total Appraisement: {self.this_report["total_appraisement"]:.2f}')

        table_header = ('stock',
                        'targetweight',
                        'cur_weight',
                        'invested',
                        'appraisement',
                        'need2invest',
                        'need2investInUnits'
                        )
        table_data = []
        for stockgroup in report_to_print['stockgroups'].values():
            for stockkey, stock in stockgroup['stocks'].items():
                table_data.append((stockkey,
                                   stock['weight'],
                                   f'{stock["appraisement"] / self.this_report["total_appraisement"]:.2f}',
                                   f'{stock["invested"]:.2f}',
                                   f'{stock["appraisement"]:.2f}',
                                   f'{stock["need2invest"]:.2f}',
                                   f'{stock["need2investInUnits"]}'
                                   ))

        print(tabulate(table_data,
                       headers=table_header,
                       tablefmt='pretty',
                       colalign=('left',),
                       numalign='right'
                       ))

    def _derive_units_to_invest(self):
        # get the number of units to invest for each stock
        for stockgroupkey, stockgroup in self.this_report['stockgroups'].items():
            for stockkey, stock in stockgroup['stocks'].items():
                if stock['currency'] == 'KRW':
                    stock['need2investInUnits'] = \
                        int(stock['need2invest'] // (stock['price'] / self.this_report['exchange_rate']))
                elif stock['currency'] == 'USD':
                    stock['need2investInUnits'] = int(stock['need2invest'] // stock['price'])
                else:
                    logger.error(f'only supports KRW and USD as currency, but {stock["currency"]} given')
                    raise NotImplementedError

    def _distribute_saving_CA(self):
        # get CA amount for each stock
        for stockgroupkey, stockgroup in self.this_report['stockgroups'].items():
            for stockkey, stock in stockgroup['stocks'].items():
                stock['need2investCA'] = self.this_report['saving'] * stock['weight']
                stock['need2invest'] = stock['need2investCA']

    def _distribute_saving_VA(self):
        # do CA first
        self._distribute_saving_CA()

        # get VA amount for each stock
        for stockgroupkey, stockgroup in self.this_report['stockgroups'].items():
            for stockkey, stock in stockgroup['stocks'].items():
                # derive VA amount
                stock['need2investVA'] = stock['invested'] - stock['appraisement']

                # overwrite need2invest as CA + VA amount
                stock['need2invest'] = stock['need2investCA'] + stock['need2investVA']

    def print_ref_report(self):
        logger.debug('print_ref_report called')
        self._print_report(self.ref_report)

    def print_report(self):
        logger.debug('print_report called')
        self._print_report(self.this_report)

    def distribute_saving(self):
        ''' all this distributed saving will be written on this_report '''

        # derive common stuffs
        self.this_report['strategy'] = self.ref_report['strategy']
        self.this_report['saving'] = self.saving
        self.this_report['exchange_rate'] = self.exchange_rate

        # update all values of each stockgroup
        self.this_report['stockgroups'] = {}
        for stockgroupkey, stockgroup in self.ref_report['stockgroups'].items():
            if stockgroupkey == 'KIS':
                stockgroup_handler = stockwrapper.KisStock(
                                                        self.this_report['exchange_rate'],
                                                        stockgroup
                )

            elif stockgroupkey == 'CoinGecko':
                stockgroup_handler = stockwrapper.GeckoStock(
                                                        self.this_report['exchange_rate'],
                                                        stockgroup
                )

            elif stockgroupkey == 'KRX':
                stockgroup_handler = stockwrapper.KrxStock(
                                                        self.this_report['exchange_rate'],
                                                        stockgroup
                )

            else:
                stockgroup_handler = stockwrapper.BaseStock(
                                                        self.this_report['exchange_rate'],
                                                        stockgroup
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

    def write_report_to_file(self, fname: str):
        with open(fname, 'w') as ofile:
            json.dump(self.this_report, ofile, indent=4)
