"""Environment-backed application settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic.aliases import AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Demo settings containing no production credentials."""

    model_config = SettingsConfigDict(
        env_prefix="RTMC_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    environment: str = "local"
    service_name: str = "rtmc-ai-assistant"
    version: str = "0.2.0"
    log_level: str = "INFO"
    privacy_notice_version: str = "demo-privacy-v1"
    governed_complaint_workflow_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "GOVERNED_COMPLAINT_WORKFLOW_ENABLED",
            "RTMC_GOVERNED_COMPLAINT_WORKFLOW_ENABLED",
        ),
    )
    governed_consent_wording_version: str = Field(
        default="synthetic-consent-v1",
        min_length=1,
        max_length=100,
        validation_alias=AliasChoices(
            "GOVERNED_CONSENT_WORDING_VERSION",
            "RTMC_GOVERNED_CONSENT_WORDING_VERSION",
        ),
    )
    llm_generation_limit_per_session: int = Field(
        default=10,
        ge=1,
        validation_alias=AliasChoices(
            "LLM_GENERATION_LIMIT_PER_SESSION",
            "RTMC_LLM_GENERATION_LIMIT_PER_SESSION",
        ),
    )
    llm_quota_window_seconds: int = Field(
        default=86400,
        ge=1,
        validation_alias=AliasChoices("LLM_QUOTA_WINDOW_SECONDS", "RTMC_LLM_QUOTA_WINDOW_SECONDS"),
    )
    request_rate_limit_per_minute: int = Field(
        default=20,
        ge=1,
        validation_alias=AliasChoices(
            "REQUEST_RATE_LIMIT_PER_MINUTE",
            "RTMC_REQUEST_RATE_LIMIT_PER_MINUTE",
        ),
    )
    approved_support_phone: str | None = Field(
        default=None,
        validation_alias=AliasChoices("APPROVED_SUPPORT_PHONE", "RTMC_APPROVED_SUPPORT_PHONE"),
    )
    approved_contact_url: HttpUrl | None = Field(
        default=None,
        validation_alias=AliasChoices("APPROVED_CONTACT_URL", "RTMC_APPROVED_CONTACT_URL"),
    )
    llm_provider: str = Field(
        default="mock",
        pattern=r"^(mock|openai)$",
        validation_alias=AliasChoices("LLM_PROVIDER", "RTMC_LLM_PROVIDER"),
    )
    llm_model: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_MODEL", "RTMC_LLM_MODEL"),
    )
    llm_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY", "RTMC_LLM_API_KEY"),
    )
    llm_timeout_seconds: float = Field(
        default=15,
        gt=0,
        le=60,
        validation_alias=AliasChoices("LLM_TIMEOUT_SECONDS", "RTMC_LLM_TIMEOUT_SECONDS"),
    )
    llm_max_output_tokens: int = Field(
        default=500,
        ge=1,
        le=2000,
        validation_alias=AliasChoices("LLM_MAX_OUTPUT_TOKENS", "RTMC_LLM_MAX_OUTPUT_TOKENS"),
    )
    llm_max_retries: int = Field(
        default=1,
        ge=0,
        le=3,
        validation_alias=AliasChoices("LLM_MAX_RETRIES", "RTMC_LLM_MAX_RETRIES"),
    )
    llm_input_cost_per_million: float = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices(
            "LLM_INPUT_COST_PER_MILLION",
            "RTMC_LLM_INPUT_COST_PER_MILLION",
        ),
    )
    llm_output_cost_per_million: float = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices(
            "LLM_OUTPUT_COST_PER_MILLION",
            "RTMC_LLM_OUTPUT_COST_PER_MILLION",
        ),
    )

    @field_validator("approved_support_phone")
    @classmethod
    def validate_approved_phone(cls, value: str | None) -> str | None:
        """Reject blank or suspicious contact configuration."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if not 5 <= len(normalized) <= 32 or any(
            character not in "+0123456789 ()-" for character in normalized
        ):
            raise ValueError("approved support phone contains unsupported characters")
        return normalized

    @field_validator("approved_contact_url", mode="before")
    @classmethod
    def empty_approved_url_is_unset(cls, value: object) -> object:
        """Treat an empty optional environment value as unconfigured."""
        return None if value == "" else value

    @field_validator("llm_api_key", mode="before")
    @classmethod
    def empty_api_key_is_unset(cls, value: object) -> object:
        """Treat an empty optional secret as unconfigured."""
        return None if value == "" else value

    @field_validator("llm_model")
    @classmethod
    def normalize_model_name(cls, value: str) -> str:
        """Strip accidental whitespace without selecting a paid model."""
        return value.strip()

    @model_validator(mode="after")
    def restrict_governed_workflow_to_safe_local_use(self) -> Settings:
        """Fail closed if the Stage 3B adapter is enabled outside a synthetic runtime."""
        if self.governed_complaint_workflow_enabled and self.environment not in {
            "local",
            "local-docker",
            "test",
            "testing",
        }:
            raise ValueError("governed complaint workflow is limited to local/test environments")
        if self.governed_complaint_workflow_enabled and self.llm_provider != "mock":
            raise ValueError("governed complaint workflow requires the mock provider")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-equivalent settings object per process."""
    return Settings()
