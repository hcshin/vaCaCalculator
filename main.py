import portfolio
from setup_logger import setup_logger

if __name__ == '__main__':
    logger = setup_logger('autoinvestment_logger', 'INFO')
    logger.debug('Program started')
    my_portfolio = portfolio.Portfolio('202305.json', 1000000)
    my_portfolio.distribute_saving()
    my_portfolio.print_ref_report()
    my_portfolio.write_report_to_file('202306.json')
    logger.debug('Program ended')
