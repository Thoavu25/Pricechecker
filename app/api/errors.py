import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError

logger = logging.getLogger("price_checker")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(UnauthorizedError)
    def unauthorized(_: Request, error: UnauthorizedError):
        return JSONResponse(status_code=401, content={"detail": str(error)})

    @app.exception_handler(ForbiddenError)
    def forbidden(_: Request, error: ForbiddenError):
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(ConflictError)
    def conflict(_: Request, error: ConflictError):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(NotFoundError)
    def not_found(_: Request, error: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(Exception)
    def unexpected(request: Request, error: Exception):
        logger.error(
            "Unhandled API error user_id=%s path=%s",
            getattr(request.state, "user_id", "anonymous"),
            request.url.path,
            exc_info=(type(error), error, error.__traceback__),
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected server error occurred"},
        )
