# config.py
import logging
import sys

# Уровень логирования можно сделать переменным
LOG_LEVEL = logging.INFO
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"

def configure_logging(module_name: str):
    logger = logging.getLogger(module_name)
    logger.setLevel(LOG_LEVEL)

    if not logger.handlers:
        formatter = logging.Formatter(LOG_FORMAT)

        # Инфо и ниже → stdout
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.addFilter(lambda record: record.levelno < logging.ERROR)
        stdout_handler.setFormatter(formatter)

        # Ошибки и выше → stderr
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.ERROR)
        stderr_handler.setFormatter(formatter)

        logger.addHandler(stdout_handler)
        logger.addHandler(stderr_handler)

    # Перехват логгера Flask/werkzeug
    flask_logger = logging.getLogger('werkzeug')
    flask_logger.setLevel(LOG_LEVEL)
    if not flask_logger.handlers:
        flask_logger.addHandler(stdout_handler)
        flask_logger.addHandler(stderr_handler)

    return logger
