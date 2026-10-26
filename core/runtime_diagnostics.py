"""Persistent exit/fatal exception evidence without recording audio or credentials."""
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import threading

_logger = None
_fatal_stream = None

def install_diagnostics(directory=None):
    global _logger, _fatal_stream
    if _logger is not None:
        return
    try:
        folder = Path(directory or Path.home() / '.edith' / 'logs')
        folder.mkdir(parents=True, exist_ok=True)
        logger = logging.Logger('edith.runtime')
        handler = RotatingFileHandler(folder / 'runtime.log', maxBytes=1_000_000, backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
        _logger = logger
        _fatal_stream = (folder / 'fatal.log').open('a', encoding='utf-8')
        faulthandler.enable(file=_fatal_stream, all_threads=True)
        old = sys.excepthook
        def unhandled(kind, value, tb):
            # Exception messages may include provider credentials. Record type and
            # stack locations only; normal stderr retains Python's own traceback.
            import traceback
            logger.error('Unhandled %s\n%s', kind.__name__, ''.join(traceback.format_tb(tb)))
            old(kind, value, tb)
        sys.excepthook = unhandled
        original_thread_hook = threading.excepthook
        def thread_error(args):
            import traceback
            logger.error('Thread failure %s\n%s', args.exc_type.__name__, ''.join(traceback.format_tb(args.exc_traceback)))
            original_thread_hook(args)
        threading.excepthook = thread_error
        record_exit('Application started')
    except OSError:
        print('EDITH: runtime diagnostics directory is unavailable.')

def record_exit(message):
    if _logger:
        _logger.info('%s', message)
