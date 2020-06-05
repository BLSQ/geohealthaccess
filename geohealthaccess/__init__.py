import logging
import tempfile


root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    '%(asctime)s %(levelname)s [%(module)s]: %(message)s',
    '%Y-%m-%d %H:%M:%S'
)

file_handler = logging.FileHandler('geohealthaccess.log')
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

root_logger.addHandler(file_handler)
root_logger.addHandler(stream_handler)
