import logging


def setup_logger(logger_name, log_level):
    logging.basicConfig(level=logging._nameToLevel[log_level.upper()],
                        format='[%(asctime)s - %(filename)s - %(levelname)s] %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger(logger_name)

    return logger
