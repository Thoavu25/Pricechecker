class UnauthorizedError(Exception):
    """Missing or invalid credentials."""


class ForbiddenError(Exception):
    """Authenticated account is not permitted to perform an operation."""


class ConflictError(Exception):
    """A requested resource conflicts with existing data."""


class NotFoundError(Exception):
    """Requested domain resource does not exist."""
