import os
import logging
import inspect

log_file_path = "./bot/bot_logs.log"

class Logger:

    def __init__(self):
        try:
            logging.getLogger().removeHandler(logging.getLogger().handlers[0])
        except:
            pass
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        logging.getLogger("pyrogram").setLevel(logging.WARNING)
        logging.getLogger("pymongo").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("aiohttp").setLevel(logging.WARNING)
        logging.getLogger("charset_normalizer").setLevel(logging.WARNING)
        logging.getLogger("Librespot:Session").setLevel(logging.WARNING)
        logging.getLogger("Librespot:MercuryClient").setLevel(logging.WARNING)
        logging.getLogger("Librespot:TokenProvider").setLevel(logging.WARNING)
        logging.getLogger("librespot.audio").setLevel(logging.WARNING)
        logging.getLogger("Librespot:ApiClient").setLevel(logging.WARNING)
        logging.getLogger("pydub").setLevel(logging.WARNING)
        logging.getLogger("spotipy").setLevel(logging.WARNING)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # Create file handler
        file_handler = logging.FileHandler(log_file_path, 'a', 'utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def debug(self, message, *args, **kwargs):
        caller_frame = inspect.currentframe().f_back
        caller_filename = os.path.basename(caller_frame.f_globals['__file__'])
        self.logger.debug(f'{caller_filename} - {message}', *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self.logger.info(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        caller_frame = inspect.currentframe().f_back
        caller_filename = os.path.basename(caller_frame.f_globals['__file__'])
        self.logger.error(f'{caller_filename} - {message}', *args, **kwargs)

LOGGER = Logger()
