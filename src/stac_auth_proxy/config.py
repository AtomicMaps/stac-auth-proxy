"""Configuration for the STAC Auth Proxy."""

from typing import Any, Callable, Literal, Optional, Sequence, TypeAlias, Union

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.networks import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

from stac_auth_proxy.filters.scope_based_item_filter import scope_based_filter

METHODS = Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
EndpointMethods: TypeAlias = dict[str, Sequence[METHODS]]
EndpointMethodsWithScope: TypeAlias = dict[
    str, Sequence[Union[METHODS, tuple[METHODS, str]]]
]

_PREFIX_PATTERN = r"^/.*$"

ALLOWED_MODULE_PREFIXES: tuple[str, ...] = ("stac_auth_proxy.",)


def str2list(x: Optional[str] = None) -> Optional[Sequence[str]]:
    """Convert string to list based on , delimiter."""
    if x:
        return x.replace(" ", "").split(",")

    return None


class CorsSettings(BaseModel):
    """CORS configuration settings."""

    allow_origins: Sequence[str] = ["*"]
    allow_methods: Sequence[str] = ["*"]
    allow_headers: Sequence[str] = ["*"]
    allow_credentials: bool = True
    expose_headers: Sequence[str] = []
    max_age: int = 600

    @field_validator(
        "allow_origins",
        "allow_methods",
        "allow_headers",
        "expose_headers",
        mode="before",
    )
    @classmethod
    def parse_list(cls, v):
        """Parse a comma-separated string into a list."""
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


class Settings(BaseSettings):
    """Configuration settings for the STAC Auth Proxy."""

    # External URLs
    upstream_url: HttpUrl
    oidc_discovery_url: HttpUrl
    oidc_discovery_internal_url: HttpUrl
    allowed_jwt_audiences: Optional[Sequence[str]] = None

    root_path: str = ""
    override_host: bool = True
    healthz_prefix: str = Field(pattern=_PREFIX_PATTERN, default="/healthz")
    wait_for_upstream: bool = True
    check_conformance: bool = True
    enable_compression: bool = True
    proxy_options: bool = False
    cors: CorsSettings = Field(default_factory=CorsSettings)

    # OpenAPI / Swagger UI
    openapi_spec_endpoint: Optional[str] = Field(
        pattern=_PREFIX_PATTERN, default="/api"
    )
    openapi_auth_scheme_name: str = "oidcAuth"
    openapi_auth_scheme_override: Optional[dict] = None
    swagger_ui_endpoint: Optional[str] = Field(
        pattern=_PREFIX_PATTERN, default="/api.html"
    )
    swagger_ui_init_oauth: dict = Field(default_factory=dict)

    # Auth
    enable_authentication_extension: bool = True
    default_public: bool = False
    public_endpoints: EndpointMethods = {
        r"^/api.html$": ["GET"],
        r"^/api$": ["GET"],
        r"^/conformance$": ["GET"],
        r"^/docs/oauth2-redirect": ["GET"],
        r"^/healthz": ["GET"],
        r"^/_mgmt/ping": ["GET"],
        r"^/_mgmt/health": ["GET"],
    }
    private_endpoints: EndpointMethodsWithScope = {
        r"^/(.*)$": [("GET", "read:stac")],
        r"^/search$": [("POST", "read:stac")],
        r"^/aggregate$": [("POST", "read:stac")],
        r"^/collections/aggregate$": [("POST", "read:stac")],
        r"^/collections$": [("POST", "create:stac")],
        r"^/collections/([^/]+)$": [
            ("PUT", "update:stac"),
            ("PATCH", "update:stac"),
            ("POST", "create:stac"),
            ("DELETE", "delete:stac"),
        ],
        r"^/admin/([^/]+)$": [("POST", "create:stac")],
    }

    # Filters
    items_filter: Optional[Callable] = Field(default_factory=scope_based_filter)
    items_filter_path: str = r"^(/collections/([^/]+)/items(/[^/]+)?$|/search$|/aggregate$|/collections/([^/]+)/tiles/[^/]+/[^/]+/[^/]+\.mvt$)"
    collections_filter: Optional[Callable] = None
    collections_filter_path: str = r"^/collections(/[^/]+)?$"

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
    )

    @model_validator(mode="before")
    @classmethod
    def _default_oidc_discovery_internal_url(cls, data: Any) -> Any:
        """Set the internal OIDC discovery URL to the public URL if not set."""
        if not data.get("oidc_discovery_internal_url"):
            data["oidc_discovery_internal_url"] = data.get("oidc_discovery_url")
        return data

    @field_validator("allowed_jwt_audiences", mode="before")
    @classmethod
    def parse_audience(cls, v) -> Optional[Sequence[str]]:
        """Parse a comma separated string list of audiences into a list."""
        return str2list(v)
