# Custom Logging System - pyfabricops

## 📋 Feature Overview

The custom logging system implemented in `pyfabricops` provides a complete and flexible solution for monitoring and debugging the library.

## ✨ Main Features

### 🎨 **Custom Formatting**
- **Automatic colors**: Different colors for each log level (DEBUG=Cyan, INFO=Green, WARNING=Yellow, ERROR=Red, CRITICAL=Magenta)
- **Multiple styles**:
  - `minimal`: Only timestamp, level and message
  - `standard`: Includes module name in compact form
  - `detailed`: Complete format with all information

### 🎛️ **Easy Configuration**
```python
import pyfabricops as pf

# Basic configuration
pf.setup_logging(level="INFO", format_style="standard")

# Debug mode for development
pf.enable_debug_mode(include_external=False)

# Disable logging completely
pf.disable_logging()

# Reset to default configuration
pf.reset_logging()
```

### 📁 **File Logging**
```python
# Save logs to file with automatic rotation
pf.setup_logging(
    level="DEBUG",
    log_file="logs/pyfabricops.log",
    max_file_size=10*1024*1024,  # 10MB
    backup_count=5
)
```

### 🔍 **Smart Filtering**
- **By default**: Shows only pyfabricops logs
- **Optional**: Include logs from external libraries (requests, urllib3, etc.)
- **Granular control**: Configuration by module

### 🖥️ **Terminal Detection**
- **Automatic colors**: Detects if terminal supports colors
- **CI/CD friendly**: Automatically disables colors in build environments
- **Environment variables**: Respects `NO_COLOR` and `FORCE_COLOR`

## 🚀 **Usage Examples**

### Basic Usage
```python
import pyfabricops as pf

# Default setup
pf.setup_logging(level="INFO")

# Use library normally
workspaces = pf.list_workspaces()
```

### Development and Debug
```python
# Complete debug mode
pf.enable_debug_mode(include_external=True)

# Execute functions - you'll see all API details
definition = pf.get_semantic_model_definition("workspace", "model")
```

### Production
```python
# Minimal logging in production
pf.setup_logging(
    level="WARNING",
    format_style="minimal",
    include_colors=False,
    log_file="/var/log/app/pyfabricops.log"
)
```

## 📊 **Benefits**

1. **🎯 Efficient Debugging**: See exactly which APIs are being called
2. **🎨 Visual Appeal**: Colors and clear formatting make reading easier
3. **⚡ Performance**: Optimized system with smart filters
4. **🔧 Flexibility**: Multiple configuration options
5. **📝 Audit**: File logs with automatic rotation
6. **🔒 Security**: Sensitive headers are automatically masked

## 🛠️ **Available Functions**

| Function | Description |
|----------|-------------|
| `setup_logging()` | Complete logging system configuration |
| `enable_debug_mode()` | Quick debug mode activation |
| `disable_logging()` | Disables all logs |
| `reset_logging()` | Returns to default configuration |
| `get_logger()` | Gets a configured logger |

## 🎨 **Visual Example**

```
13:00:25 | pyfabricops._core    | INFO     | Making GET request to https://api.fabric.microsoft.com/v1/workspaces
13:00:25 | pyfabricops._core    | DEBUG    | Headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ***'}
13:00:25 | pyfabricops._core    | DEBUG    | Response status: 200
```

## 🎯 **Use Cases**

1. **Development**: Detailed debug with colors
2. **Testing**: Structured logs for analysis
3. **Production**: Controlled logging with files
4. **CI/CD**: Logs without colors, consistent format
5. **Troubleshooting**: Complete API call tracing

---

*This system transforms the development and debugging experience with pyfabricops, offering complete visibility over library operations in an elegant and configurable way.*
