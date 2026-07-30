"""Provider failures with safe retry semantics and no raw secret-bearing details."""


class ProviderError(Exception):
    """Base provider failure."""

    retryable = False


class ProviderUnavailableError(ProviderError):
    """Transient network, timeout, or upstream availability failure."""

    retryable = True


class ProviderAuthenticationError(ProviderError):
    """Configured credentials were rejected."""


class ProviderConfigurationError(ProviderError):
    """A selected provider is missing required safe configuration."""


class ProviderOutputError(ProviderError):
    """Provider output did not match the trusted structured contract."""
