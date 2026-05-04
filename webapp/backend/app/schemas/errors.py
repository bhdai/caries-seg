from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error envelope returned by all AppError exception responses.

    Used as the ``responses=`` schema on FastAPI route decorators for OpenAPI
    documentation. The backend does NOT need to manually construct this model
    at runtime — the AppError exception handler serialises the response
    directly.

    Attributes:
        code: Machine-readable error identifier. Dot-namespaced, e.g.
            ``"auth.invalidCredentials"``. Stable API contract — never rename
            after release without a deprecation period.
        detail: Human-readable English description of the error. May contain
            interpolated values (e.g. job IDs) that the frontend ignores when
            a ``code`` is present.
    """

    code: str
    detail: str
