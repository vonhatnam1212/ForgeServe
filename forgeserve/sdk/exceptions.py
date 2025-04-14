class ForgeSdkException(Exception):
    """Base exception class for ForgeServe SDK errors."""
    pass

class ConfigurationError(ForgeSdkException):
    """Exception related to loading or validating configuration."""
    pass

class RunnerError(ForgeSdkException):
    """Exception related to the execution backend (e.g., Kubernetes API error)."""
    pass
