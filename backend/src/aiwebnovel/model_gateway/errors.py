"""Safe errors which never carry credentials, prompts, or upstream responses."""

from aiwebnovel.domain.errors import DomainError


class InvalidModelProfile(DomainError):
    message = "The model configuration is invalid."


class ModelProfileNotFound(DomainError):
    message = "The model configuration was not found."


class ModelConfigurationUnavailable(DomainError):
    message = "The model configuration could not be stored or loaded."


class ModelCredentialUnavailable(DomainError):
    message = "The protected model credential is unavailable on this device."
