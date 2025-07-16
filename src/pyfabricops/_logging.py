"""
Custom logging configuration for pyfabricops.

T    # Colored symbols for each log level
    SYMBOLS = {
        'DEBUG':    ESC + '36m○\033[0m',      # Cyan circle
        'INFO':     ESC + '34mi\033[0m',      # Blue "i"
        'SUCCESS':  ESC + '32m✓\033[0m',      # Green check
        'WARNING':  ESC + '33m△\033[0m',      # Yellow triangle
        'ERROR':    ESC + '31m✕\033[0m',      # Red X
        'CRITICAL': ESC + '41;97m⊗\033[0m',   # Red background + bright white circled times
    }e provides a centralized logging system with customizable formatters,
handlers, and configuration options for better debugging and monitoring.
"""
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, Union

__all__ = [
    'PyFabricOpsFormatter',
    'PyFabricOpsFilter',
    'setup_logging',
    'get_logger',
    'enable_debug_mode',
    'disable_logging',
    'reset_logging',
    'SUCCESS_LEVEL',
]

# Define custom SUCCESS level (between INFO and WARNING)
SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, 'SUCCESS')


def success(self, message, *args, **kwargs):
    """Log a message with severity 'SUCCESS'."""
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kwargs)


# Add success method to Logger class
logging.Logger.success = success


class PyFabricOpsFormatter(logging.Formatter):
    """Custom formatter for pyfabricops with colored output and structured format."""

    ESC = '\x1b['

    COLORS = {
        'DEBUG': ESC + '36m',  # Cyan text
        'INFO': ESC + '34m',  # Blue text
        'SUCCESS': ESC + '32m',  # Green text
        'WARNING': ESC + '33m',  # Yellow text
        'ERROR': ESC + '31m',  # Red text
        'CRITICAL': ESC + '31m',  # Red text
        'RESET': ESC + '0m',  # Reset
    }

    # Colored symbols for each log level
    SYMBOLS = {
        'DEBUG': ESC + '36m○\033[0m',  # Cyan circle
        'INFO': ESC + '34mi\033[0m',  # Blue “i”
        'SUCCESS': ESC + '32m✓\033[0m',  # Green check
        'WARNING': ESC + '33m△\033[0m',  # Yellow triangle
        'ERROR': ESC + '31m✕\033[0m',  # Red X
        'CRITICAL': ESC + '31m⊗\033[0m',  # Red circled times
    }

    # Fallback symbols without colors (for terminals that don't support colors)
    SYMBOLS_NO_COLOR = {
        'DEBUG': '○',  # Wrench
        'INFO': 'i',  # Check mark
        'SUCCESS': '✓',  # Check mark
        'WARNING': '△',  # Warning
        'ERROR': '✕',  # X mark
        'CRITICAL': '⊗',  # Siren
    }

    def __init__(
        self,
        include_colors: bool = True,
        include_module: bool = True,
        ultra_minimal: bool = False,
        include_symbols: bool = True,
    ):
        """
        Initialize the custom formatter.

        Args:
            include_colors (bool): Whether to include colors in console output
            include_module (bool): Whether to include module name in log format
            ultra_minimal (bool): Whether to use ultra minimal format (just message)
            include_symbols (bool): Whether to include colored symbols before messages
        """
        self.include_colors = include_colors and self._supports_color()
        self.include_module = include_module
        self.ultra_minimal = ultra_minimal
        self.include_symbols = include_symbols

        # Base format without colors
        if ultra_minimal:
            base_format = '%(message)s'
        else:
            base_format = '%(asctime)s'
            if include_module:
                base_format += ' | %(name)-20s'
            base_format += ' | %(levelname)-8s | %(message)s'

        super().__init__(base_format, datefmt='%H:%M:%S')

    def _supports_color(self) -> bool:
        """Check if the current terminal supports colors."""
        # Check if we're in a terminal that supports colors
        if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
            return False

        # Check environment variables
        if os.environ.get('NO_COLOR'):
            return False

        if os.environ.get('FORCE_COLOR'):
            return True

        # Check common terminals that support colors
        term = os.environ.get('TERM', '').lower()
        return 'color' in term or term in [
            'xterm',
            'xterm-256color',
            'screen',
            'tmux',
        ]

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with optional colors and symbols."""
        # In ultra-minimal mode, format with optional symbols
        if self.ultra_minimal:
            message = record.getMessage()
            if self.include_symbols:
                if self.include_colors:
                    symbol = self.SYMBOLS.get(record.levelname, '')
                else:
                    symbol = self.SYMBOLS_NO_COLOR.get(record.levelname, '')
                return f'{symbol} {message}'
            return message

        # Create a copy of the record to avoid modifying the original
        record_copy = logging.makeLogRecord(record.__dict__)

        # Add colors if enabled
        if self.include_colors:
            level_color = self.COLORS.get(
                record_copy.levelname, self.COLORS['RESET']
            )
            record_copy.levelname = (
                f"{level_color}{record_copy.levelname}{self.COLORS['RESET']}"
            )

            # Add color to module name if it's a pyfabricops module
            if (
                hasattr(record_copy, 'name')
                and 'pyfabricops' in record_copy.name
            ):
                record_copy.name = f'\033[34m{record_copy.name}\033[0m'  # Blue

        # Format the message with the base formatter
        formatted_message = super().format(record_copy)

        # Add colored symbol prefix if enabled
        if self.include_symbols:
            if self.include_colors:
                symbol = self.SYMBOLS.get(record.levelname, '')
            else:
                symbol = self.SYMBOLS_NO_COLOR.get(record.levelname, '')
            return f'{symbol} {formatted_message}'

        return formatted_message


class PyFabricOpsFilter(logging.Filter):
    """Custom filter to control which log records are processed."""

    def __init__(self, include_external: bool = False):
        """
        Initialize the filter.

        Args:
            include_external (bool): Whether to include logs from external libraries
        """
        super().__init__()
        self.include_external = include_external

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records based on configuration."""
        # Always include pyfabricops logs
        if record.name.startswith('pyfabricops'):
            return True

        # Include external logs only if explicitly enabled
        return self.include_external


def setup_logging(
    level: Union[str, int] = logging.INFO,
    format_style: Literal['standard', 'minimal', 'detailed'] = 'standard',
    include_colors: bool = True,
    include_module: bool = True,
    include_symbols: bool = True,
    log_file: Optional[Union[str, Path]] = None,
    include_external: bool = False,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> None:
    """
    Configure logging for pyfabricops.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL or numeric)
        format_style: Format style ('standard', 'minimal', 'detailed')
                     - 'minimal': Only message (ultra-minimal)
                     - 'standard': Timestamp, level, and message
                     - 'detailed': Timestamp, module, level, and message
        include_colors: Whether to use colored output in console
        include_module: Whether to include module names in logs
        include_symbols: Whether to include colored symbols before messages (enabled by default)
        log_file: Optional file path to write logs to
        include_external: Whether to include logs from external libraries
        max_file_size: Maximum size of log file before rotation (bytes)
        backup_count: Number of backup files to keep when rotating
    """
    # Convert string level to numeric if needed
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # Get the root logger for pyfabricops
    root_logger = logging.getLogger('pyfabricops')

    # Clear existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Set the logging level
    root_logger.setLevel(level)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Create formatter based on style
    if format_style == 'minimal':
        formatter = PyFabricOpsFormatter(
            include_colors=include_colors,
            include_module=False,
            ultra_minimal=True,
            include_symbols=include_symbols,
        )
    elif format_style == 'detailed':
        formatter = PyFabricOpsFormatter(
            include_colors=include_colors,
            include_module=True,
            ultra_minimal=False,
            include_symbols=include_symbols,
        )
    else:  # standard
        formatter = PyFabricOpsFormatter(
            include_colors=include_colors,
            include_module=include_module,
            ultra_minimal=False,
            include_symbols=include_symbols,
        )

    console_handler.setFormatter(formatter)

    # Add filter
    console_filter = PyFabricOpsFilter(include_external=include_external)
    console_handler.addFilter(console_filter)

    # Add console handler
    root_logger.addHandler(console_handler)

    # Add file handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Use rotating file handler to prevent huge log files
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8',
        )
        file_handler.setLevel(level)

        # File logs don't need colors or symbols (for better readability in files)
        file_formatter = PyFabricOpsFormatter(
            include_colors=False, include_module=True, include_symbols=False
        )
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(console_filter)

        root_logger.addHandler(file_handler)

    # Prevent propagation to root logger to avoid duplicate messages
    root_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.

    Args:
        name: The logger name (usually __name__)

    Returns:
        logging.Logger: Configured logger instance
    """
    # Ensure the name starts with pyfabricops
    if not name.startswith('pyfabricops'):
        if name == '__main__':
            name = 'pyfabricops.main'
        else:
            name = f'pyfabricops.{name}'

    logger = logging.getLogger(name)

    # Add NullHandler as fallback if no configuration is set
    if not logger.handlers and not logger.parent.handlers:
        logger.addHandler(logging.NullHandler())

    return logger


def enable_debug_mode(include_external: bool = True) -> None:
    """
    Quick function to enable debug logging with detailed output.

    Args:
        include_external: Whether to include logs from external libraries
    """
    setup_logging(
        level=logging.DEBUG,
        format_style='detailed',
        include_colors=True,
        include_module=True,
        include_external=include_external,
    )


def disable_logging() -> None:
    """Disable all logging output."""
    logging.getLogger('pyfabricops').setLevel(logging.CRITICAL + 1)


def reset_logging() -> None:
    """Reset logging to default configuration."""
    root_logger = logging.getLogger('pyfabricops')

    # Clear all handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add back the null handler
    root_logger.addHandler(logging.NullHandler())
    root_logger.setLevel(logging.WARNING)


# Default configuration - minimal logging to avoid noise
_default_configured = False


def _ensure_default_config():
    """Ensure default logging configuration is applied."""
    global _default_configured
    if not _default_configured:
        # Set up minimal logging by default
        root_logger = logging.getLogger('pyfabricops')
        if not root_logger.handlers:
            root_logger.addHandler(logging.NullHandler())
            root_logger.setLevel(logging.WARNING)
        _default_configured = True


# Apply default configuration on import
_ensure_default_config()
