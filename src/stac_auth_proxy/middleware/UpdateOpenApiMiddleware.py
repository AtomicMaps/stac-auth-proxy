"""Middleware to add auth information to the OpenAPI spec served by upstream API."""

import re
from dataclasses import dataclass
from typing import Any, Optional

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ..config import EndpointMethods
from ..utils.middleware import JsonResponseMiddleware
from ..utils.requests import find_match
from ..utils.stac import ensure_type

SWAGGER_SPLASH_HTML = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
        <style>
            *, *::before, *::after {{ box-sizing: border-box; }}
            body {{
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #fafafa;
            }}

            /* ── Splash screen ── */
            .splash-overlay {{
                position: fixed;
                inset: 0;
                z-index: 9999;
                display: flex;
                align-items: center;
                justify-content: center;
                background: rgba(0, 0, 0, 0.45);
                backdrop-filter: blur(4px);
            }}
            .splash-card {{
                background: #fff;
                border-radius: 12px;
                box-shadow: 0 8px 30px rgba(0,0,0,0.18);
                padding: 2.5rem 2rem 2rem;
                width: 460px;
                max-width: 92vw;
                text-align: center;
            }}
            .splash-card h2 {{
                margin: 0 0 0.25rem;
                font-size: 1.4rem;
                color: #1b1b1b;
            }}
            .splash-card p {{
                margin: 0 0 1.5rem;
                color: #555;
                font-size: 0.92rem;
                line-height: 1.45;
            }}
            .splash-card label {{
                display: block;
                text-align: left;
                font-weight: 600;
                font-size: 0.85rem;
                color: #333;
                margin-bottom: 0.4rem;
            }}
            .splash-card textarea {{
                width: 100%;
                min-height: 90px;
                padding: 0.6rem 0.75rem;
                border: 1px solid #ccc;
                border-radius: 6px;
                font-family: 'SF Mono', SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace;
                font-size: 0.82rem;
                resize: vertical;
                transition: border-color 0.15s;
            }}
            .splash-card textarea:focus {{
                outline: none;
                border-color: #49cc90;
                box-shadow: 0 0 0 3px rgba(73, 204, 144, 0.18);
            }}
            .splash-card button {{
                margin-top: 1.1rem;
                width: 100%;
                padding: 0.7rem;
                border: none;
                border-radius: 6px;
                background: #49cc90;
                color: #fff;
                font-size: 0.95rem;
                font-weight: 600;
                cursor: pointer;
                transition: background 0.15s;
            }}
            .splash-card button:hover {{ background: #3db87e; }}
            .splash-card button:disabled {{
                background: #b8e6d0;
                cursor: not-allowed;
            }}
            .splash-error {{
                margin-top: 0.75rem;
                color: #e53e3e;
                font-size: 0.85rem;
                min-height: 1.2em;
            }}

            /* ── Swagger UI container (hidden until authed) ── */
            #swagger-ui {{ display: none; }}
        </style>
    </head>
    <body>

    <!-- Splash Screen -->
    <div class="splash-overlay" id="splash">
        <div class="splash-card">
            <h2>{title}</h2>
            <p>Paste your JWT token below to load the docs.</p>
            <label for="jwt-input">Bearer Token</label>
            <textarea id="jwt-input" placeholder="eyJhbGciOiJSUzI1NiIs..." spellcheck="false"></textarea>
            <button id="auth-btn" onclick="authenticate()">Authenticate &amp; Load Docs</button>
            <div class="splash-error" id="splash-error"></div>
        </div>
    </div>

    <!-- Swagger UI (rendered after successful auth) -->
    <div id="swagger-ui"></div>

    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        const SPEC_URL = "{spec_url}";
        const AUTH_SCHEME = "{auth_scheme_name}";

        async function authenticate() {{
            const btn = document.getElementById("auth-btn");
            const errEl = document.getElementById("splash-error");
            const token = document.getElementById("jwt-input").value.trim();

            errEl.textContent = "";

            if (!token) {{
                errEl.textContent = "Please enter a token.";
                return;
            }}

            btn.disabled = true;
            btn.textContent = "Loading…";

            try {{
                const resp = await fetch(SPEC_URL, {{
                    headers: {{ "Authorization": "Bearer " + token }}
                }});

                if (!resp.ok) {{
                    const detail = await resp.text();
                    throw new Error(
                        resp.status === 401 || resp.status === 403
                            ? "Invalid or expired token. Please try again."
                            : `Failed to load spec (HTTP ${{resp.status}}): ${{detail}}`
                    );
                }}

                const spec = await resp.json();

                // Hide splash, show Swagger UI
                document.getElementById("splash").style.display = "none";
                document.getElementById("swagger-ui").style.display = "block";

                // Render Swagger UI with the fetched spec
                const ui = SwaggerUIBundle({{
                    spec: spec,
                    dom_id: "#swagger-ui",
                    deepLinking: true,
                    presets: [
                        SwaggerUIBundle.presets.apis,
                        SwaggerUIBundle.SwaggerUIStandalonePreset,
                    ],
                    layout: "BaseLayout",
                }});

                // Pre-authorize so the user doesn't have to paste the token again
                ui.preauthorizeApiKey(AUTH_SCHEME, token);

            }} catch (err) {{
                errEl.textContent = err.message;
                btn.disabled = false;
                btn.textContent = "Authenticate & Load Docs";
            }}
        }}

        // Allow Ctrl/Cmd+Enter to submit
        document.getElementById("jwt-input").addEventListener("keydown", function(e) {{
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {{
                authenticate();
            }}
        }});
    </script>
    </body>
    </html>
"""


@dataclass(frozen=True)
class OpenApiMiddleware(JsonResponseMiddleware):
    """Middleware to add the OpenAPI spec to the response."""

    app: ASGIApp
    openapi_spec_path: str
    oidc_discovery_url: str
    private_endpoints: EndpointMethods
    public_endpoints: EndpointMethods
    default_public: bool
    root_path: str = ""
    auth_scheme_name: str = "oidcAuth"
    auth_scheme_override: Optional[dict] = None

    items_filter_path: Optional[str] = None
    collections_filter_path: Optional[str] = None
    swagger_ui_path: Optional[str] = None
    swagger_ui_title: str = "STAC API Docs"

    json_content_type_expr: str = r"application/(vnd\.oai\.openapi\+json?|json)"

    def should_transform_response(self, request: Request, scope: Scope) -> bool:
        """Only transform responses for the OpenAPI spec path."""
        return (
            all(
                re.match(expr, val)
                for expr, val in [
                    (self.openapi_spec_path, request.url.path),
                    (
                        self.json_content_type_expr,
                        Headers(scope=scope).get("content-type", ""),
                    ),
                ]
            )
            and 200 <= scope["status"] < 300
        )

    def transform_json(self, data: dict[str, Any], request: Request) -> dict[str, Any]:
        """Augment the OpenAPI spec with auth information."""
        # Remove any existing servers field from upstream API
        # This ensures we don't have conflicting server declarations
        if "servers" in data:
            del data["servers"]

        # Add servers field with root path if root_path is set
        if self.root_path:
            data["servers"] = [{"url": self.root_path}]

        # Add security scheme
        components = ensure_type(data, "components", dict)
        securitySchemes = ensure_type(components, "securitySchemes", dict)
        securitySchemes[self.auth_scheme_name] = self.auth_scheme_override or {
            "type": "openIdConnect",
            "openIdConnectUrl": self.oidc_discovery_url,
        }

        # Add security to private endpoints and filtered endpoints
        for path, method_config in data["paths"].items():
            for method, config in method_config.items():
                if method == "options":
                    # OPTIONS requests are not authenticated, https://fetch.spec.whatwg.org/#cors-protocol-and-credentials
                    continue
                match = find_match(
                    path,
                    method,
                    self.private_endpoints,
                    self.public_endpoints,
                    self.default_public,
                    items_filter_path=self.items_filter_path,
                    collections_filter_path=self.collections_filter_path,
                )
                if match.uses_auth:
                    security = ensure_type(config, "security", list)
                    security.append({self.auth_scheme_name: match.required_scopes})
        return data
<<<<<<< HEAD
=======

    def _path_has_filter(self, path: str) -> bool:
        """Check if a path matches any configured CQL2 filter path."""
        for filter_path in (self.items_filter_path, self.collections_filter_path):
            if filter_path and re.match(filter_path, path):
                return True
        return False

    def _build_splash_html(self) -> str:
        """Build the splash screen HTML with the configured spec URL and auth scheme."""
        spec_url = self.root_path + self.openapi_spec_path
        return SWAGGER_SPLASH_HTML.format(
            title=self.swagger_ui_title,
            spec_url=spec_url,
            auth_scheme_name=self.auth_scheme_name,
        )

    def _is_swagger_ui_request(self, scope: Scope) -> bool:
        """Check if this is a request for the Swagger UI docs page."""
        if not self.swagger_ui_path:
            return False
        request = Request(scope)
        return (
            request.url.path == self.swagger_ui_path
            and scope.get("method", "GET").upper() == "GET"
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process the request/response, serving splash screen for Swagger UI path."""
        if scope["type"] == "http" and self._is_swagger_ui_request(scope):
            response = HTMLResponse(self._build_splash_html())
            await response(scope, receive, send)
            return
        await super().__call__(scope, receive, send)
>>>>>>> atomicmaps
