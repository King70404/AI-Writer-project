"""Stable failures without prompt, prose, endpoint, or transport details."""

from aiwebnovel.domain.errors import DomainError


class InvalidAIInput(DomainError):
    message = "AI writing input is invalid."


class AIProviderNotConfigured(DomainError):
    message = "AI provider not configured"


class AIProviderConfigurationInvalid(DomainError):
    message = "AI provider configuration is invalid."


class AIProviderUnavailable(DomainError):
    message = "AI provider connection or upstream request failed."


class AIProviderAuthFailed(DomainError):
    message = "AI provider rejected the API credential."


class AIProviderAccessDenied(DomainError):
    message = "AI provider denied access to the requested model."


class AIProviderPaymentRequired(DomainError):
    message = "AI provider account balance is insufficient."


class AIProviderRateLimited(DomainError):
    message = "AI provider request rate limit was reached."


class AIProviderEndpointInvalid(DomainError):
    message = "AI provider endpoint or model was not found."


class AIProviderRequestRejected(DomainError):
    message = "AI provider rejected the model or request parameters."


class AIProviderInvalidResponse(DomainError):
    message = "AI provider returned an invalid response."


class AIProviderTimeout(DomainError):
    message = "AI provider request timed out."


class AIContextChanged(DomainError):
    message = "Chapter context changed during reading; request a new candidate."


class AIWorkflowSchemaRequired(DomainError):
    message = "AI collaboration requires an explicit database upgrade after backup."
