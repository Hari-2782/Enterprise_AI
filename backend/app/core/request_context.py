
from contextvars import ContextVar

# Each asynchronous request gets its own request context.
request_id_ctx: ContextVar[str] = ContextVar(
    "request_id",
    default="system",
)


def get_request_id() -> str:
    """Return the request ID for the current execution context."""
    return request_id_ctx.get()


def set_request_id(request_id: str):
    """Set the request ID and return a token for resetting it later."""
    return request_id_ctx.set(request_id)


def reset_request_id(token) -> None:
    """Restore the previous request context."""
    request_id_ctx.reset(token)
