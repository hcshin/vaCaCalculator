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
    '--saving-in-krw',
    type=float,
    default=0,
    show_default=True,
    help='amount of money to save in KRW'
)
@click.option(
    '--saving-in-usd',
    type=float,
    default=0.0,
    show_default=True,
    help='amount of money to save in USD'
)
@click.option(
    '--print-report',
    is_flag=True,
    help='whether to print investment report(s)'
)
@click.option(
    '--secrets-path',
    type=click.Path(exists=True, dir_okay=False),
    default='secrets.json',
    show_default=True,
    help='path to the secrets JSON file'
)
@click.option(
    '--tokens-path',
    type=click.Path(exists=False, dir_okay=False),
    default='tokens.json',
    show_default=True,
    help='path to the tokens JSON file'
)
@click.argument(
    'ref_report_path',
    type=click.Path(exists=True, dir_okay=False),
    nargs=1
)
@click.argument(
    'output_report_path',
    type=click.Path(dir_okay=False, writable=True),
    nargs=1,
    required=False
)
def main(
    debug_level,
    saving_in_krw,
    saving_in_usd,
    print_report,
    secrets_path,
    tokens_path,
    ref_report_path,
    output_report_path
):
    logger = setup_logger('autoinvestment_logger', debug_level)
    logger.debug('Program started')

    if output_report_path is None:
        if not print_report:
            logger.error('--print-report flag must be given when not giving output_report_path')
            raise Exception
        else:
            logger.info('no output_report_path given, just printing given reference report.')
            my_portfolio = portfolio.Portfolio(ref_report_path)
            my_portfolio.print_ref_report()

    else:
        my_portfolio = portfolio.Portfolio(ref_report_path,
                                           secrets_path,
                                           tokens_path,
                                           saving_in_krw,
                                           saving_in_usd)
        my_portfolio.distribute_saving()
        my_portfolio.write_report_to_file(output_report_path)

        if print_report:
            print('Reference Report\n' + '-' * 40)
            my_portfolio.print_ref_report()
            print('\nDerived Report\n' + '-' * 40)
            my_portfolio.print_this_report()

    logger.debug('Program ended')


if __name__ == '__main__':
    main()
