import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Custom Log Level for "THOUGHT"
THOUGHT_LEVEL = 25
logging.addLevelName(THOUGHT_LEVEL, "THOUGHT")

def thought(self, message, *args, **kws):
    if self.isEnabledFor(THOUGHT_LEVEL):
        self._log(THOUGHT_LEVEL, message, args, **kws)

logging.Logger.thought = thought

def setup_logger(name="VIKI", log_file="log", level=logging.INFO):
    """Sets up a standardized logger for VIKI."""
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False  # Avoid duplicate logs if this is a child logger

    # Formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%H:%M:%S'
    )

    # Console Handler — use UTF-8 stream to handle emojis on Windows (cp1252 default)
    import io
    utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    console_handler = logging.StreamHandler(utf8_stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.WARNING)
    logger.addHandler(console_handler)

    # File Handler — explicit UTF-8 encoding
    file_handler = RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Suppress third-party noise
    logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
    logging.getLogger("transformers").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

    return logger

# Global logger instance
viki_logger = setup_logger()
# Logger for internal monologue
thought_logger = setup_logger("VIKI.Thought", "thoughts.log", level=THOUGHT_LEVEL)
