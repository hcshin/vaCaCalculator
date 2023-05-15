import portfolio
import click
from setup_logger import setup_logger


@click.command()
@click.option(
    '--debug-level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING'], case_sensitive=False),
    default='INFO',
    show_default=True,
    help='debug level for logger'
)
@click.option(
    '--savings-krw',
    type=int,
    help='amount of money to save in KRW'
)
@click.argument(
    'ref_report_path',
    type=click.Path(exists=True, dir_okay=False),
    nargs=1,
)
@click.argument(
    'output_report_path',
    type=click.Path(dir_okay=False, writable=True),
    nargs=1,
)
def main(
    debug_level,
    savings_krw,
    ref_report_path,
    output_report_path
):
    logger = setup_logger('autoinvestment_logger', debug_level)
    logger.debug('Program started')
    my_portfolio = portfolio.Portfolio(ref_report_path, savings_krw)
    my_portfolio.distribute_saving()
    my_portfolio.print_ref_report()
    my_portfolio.write_report_to_file(output_report_path)
    logger.debug('Program ended')


if __name__ == '__main__':
    main()
