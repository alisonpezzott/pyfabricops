class PyFabricOpsError(Exception):
    """Base class for all exceptions raised by the pyfabricops package."""

    pass


class AuthenticationError(PyFabricOpsError):
    """Exception raised for authentication-related errors."""

    pass


class ResourceNotFoundError(PyFabricOpsError):
    """Exception raised when a requested resource is not found."""

    pass


class OptionNotAvailableError(PyFabricOpsError):
    """Exception raised when an option is not available."""

    pass


class RequestError(PyFabricOpsError):
    """Exception raised for errors in API requests."""

    pass


class InvalidParameterError(PyFabricOpsError):
    """Exception raised for invalid parameters."""

    pass


class ConfigurationError(PyFabricOpsError):
    """Exception raised for configuration-related errors."""

    pass


class FileNotFoundError(PyFabricOpsError):
    """Exception raised when a file is not found."""

    pass
