from fastapi import HTTPException


class AppError(HTTPException):
    """FastAPI-compatible exception that carries a machine-readable error code.

    Subclasses ``HTTPException`` so it integrates seamlessly with FastAPI's
    routing and test utilities (``pytest.raises(HTTPException)`` still works).

    A custom exception handler registered in ``app/main.py`` serialises this
    class as ``{"code": ..., "detail": ...}``.  Plain ``HTTPException`` raised
    by third-party middleware retains the default ``{"detail": ...}`` shape.

    Args:
        status_code: HTTP status code, e.g. ``400``, ``401``, ``403``, ``404``.
        code: Dot-namespaced machine-readable identifier consumed by the
            frontend ``translateApiError()`` function.  Must match a key in
            the form ``apiError.<code>`` in the frontend locale files, e.g.
            ``code="auth.invalidCredentials"`` → frontend key
            ``"apiError.auth.invalidCredentials"``.
        detail: Human-readable English string.  Stored in the response body
            for debugging; the frontend displays the translated string instead.

    Raises:
        Nothing — this is an exception class, not a function.

    Example::

        raise AppError(
            status_code=401,
            code="auth.invalidCredentials",
            detail="Invalid credentials",
        )
    """

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
