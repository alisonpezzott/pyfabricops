"""
Example demonstrating the new custom logging system for pyfabricops.

This script shows different ways to configure and use the logging system.
"""

import pyfabricops

# Example 1: Default logging (minimal output)
print('=== Example 1: Default logging ===')
print('By default, pyfabricops uses minimal logging to avoid noise')

# Example 2: Enable standard logging
print('\n=== Example 2: Standard logging ===')
pyfabricops.setup_logging(
    level='INFO',
    format_style='standard',
    include_colors=True,
    include_module=True,
)

# Create a logger to test
logger = pyfabricops.get_logger('example')
logger.info('This is an INFO message with standard formatting')
logger.warning('This is a WARNING message')
logger.error('This is an ERROR message')

# Example 3: Debug mode for development
print('\n=== Example 3: Debug mode ===')
pyfabricops.enable_debug_mode(include_external=False)

logger.debug('This is a DEBUG message (only visible in debug mode)')
logger.info('This is an INFO message in debug mode')

# Example 4: Minimal formatting
print('\n=== Example 4: Minimal formatting ===')
pyfabricops.setup_logging(
    level='INFO', format_style='minimal', include_colors=True
)

logger.info('This is a minimal format message')
logger.warning('This is a minimal format warning')

# Example 5: Detailed formatting
print('\n=== Example 5: Detailed formatting ===')
pyfabricops.setup_logging(
    level='INFO',
    format_style='detailed',
    include_colors=True,
    include_module=True,
)

logger.info('This is a detailed format message')
logger.warning('This is a detailed format warning')

# Example 6: File logging
print('\n=== Example 6: File logging ===')
pyfabricops.setup_logging(
    level='DEBUG',
    format_style='standard',
    include_colors=True,
    log_file='logs/pyfabricops.log',
    max_file_size=1024 * 1024,  # 1MB
    backup_count=3,
)

logger.info('This message will appear both in console and file')
logger.debug('This debug message will also be in the file')

# Example 7: No colors (for CI/CD environments)
print('\n=== Example 7: No colors ===')
pyfabricops.setup_logging(
    level='INFO',
    format_style='standard',
    include_colors=False,
    include_module=True,
)

logger.info('This message has no colors (good for CI/CD)')
logger.warning('This warning also has no colors')

# Example 8: Include external library logs
print('\n=== Example 8: Include external logs ===')
pyfabricops.setup_logging(
    level='DEBUG',
    format_style='standard',
    include_colors=True,
    include_external=True,
)

logger.info("Now you'll also see logs from requests, urllib3, etc.")

# Example 9: Disable logging completely
print('\n=== Example 9: Disable logging ===')
pyfabricops.disable_logging()

logger.info('This message will not appear')
logger.error('Neither will this error message')

# Example 10: Reset to default
print('\n=== Example 10: Reset to default ===')
pyfabricops.reset_logging()

logger.info('Back to default logging behavior')

print('\n=== All examples completed ===')
print("Check the 'logs/pyfabricops.log' file to see the file logging output.")
