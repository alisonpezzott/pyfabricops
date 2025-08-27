# Changelog

## Version 0.2.0 - Microsoft Fabric Compatibility

### 🚀 New Features

- **Azure KeyVault Lazy Loading**: Implemented on-demand loading system to resolve Microsoft Fabric compatibility issues
- **`get_available_auth_providers()` Function**: New function to diagnose which authentication providers are available in the current environment
- **Dynamic Provider Validation**: The system now automatically validates if a provider is available before attempting to use it
- **Automatic Authentication Provider**: New `'auto'` provider that automatically detects and uses available credentials

### 🔧 Technical Changes

#### `src/pyfabricops/api/auth.py`
- Removed direct import of `azure.keyvault.secrets.SecretClient`
- Added `_get_keyvault_client()` function for lazy loading
- Modified `_get_credentials_from_keyvault()` to use lazy loading
- Added `get_available_auth_providers()` function
- Added `AutoCredentialProvider` class for automatic authentication
- Improved validation in `set_auth_provider()` to check KeyVault availability

#### `src/pyfabricops/__init__.py`
- Exported new `get_available_auth_providers` function
- Updated `__all__` list

### 📚 Documentation

- **`FABRIC_COMPATIBILITY.md`**: Complete documentation about Microsoft Fabric compatibility
- **`fabric_example.py`**: Practical usage example for Fabric notebooks
- **`fabric_auto_auth_example.py`**: Example showcasing automatic authentication
- **`test_fabric_compatibility.py`**: Basic compatibility tests
- **`test_fabric_simulation.py`**: Tests simulating Fabric environment
- **`AUTO_AUTH_GUIDE.md`**: Complete guide for automatic authentication
- **README.md**: Added section about Fabric compatibility

### 🐛 Problem Resolved

**Original Error**:
```
ImportError: cannot import name 'AccessTokenInfo' from 'azure.core.credentials'
```

**Cause**: Microsoft Fabric uses an older version of `azure-core` without the `AccessTokenInfo` class

**Solution**: Lazy loading allows the library to work even when KeyVault is not available

### ✅ Compatibility

| Environment | Status | Supported Providers |
|-------------|--------|-------------------|
| Microsoft Fabric | ✅ | `auto`, `env`, `oauth` |
| Local Development | ✅ | `auto`, `env`, `oauth`, `vault` |
| Azure DevOps | ✅ | `auto`, `env`, `oauth`, `vault` |
| GitHub Actions | ✅ | `auto`, `env`, `oauth`, `vault` |

### 🔄 Migration

**For existing users**: No changes required - all existing functionality continues to work.

**For new Fabric users**: Use the following pattern:
```python
import pyfabricops as pf

# Method 1: Automatic (recommended for Fabric)
pf.set_auth_provider('auto')

# Method 2: Intelligent strategy with fallbacks
providers = pf.get_available_auth_providers()
if providers['auto']:
    pf.set_auth_provider('auto')
elif providers['env']:
    pf.set_auth_provider('env')
else:
    pf.set_auth_provider('oauth')
```

### 🧪 Tests

- 4 new compatibility tests
- Microsoft Fabric environment simulation
- Authentication fallback validation
- All existing tests continue to pass

### 📈 Experience Improvements

- **Automatic Detection**: Automatically knows which providers are available
- **Clear Messages**: Specific errors when a provider is not available
- **Graceful Fallbacks**: Allows configuring multiple auth strategies
- **Easy Diagnostics**: Function to check environment status
- **Zero Configuration**: Works automatically in authenticated environments like Microsoft Fabric
