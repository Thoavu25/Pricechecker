import os


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./price_checker.db")
APP_ENV = os.getenv("APP_ENV", "development")
AUTO_APPROVE_STORES = os.getenv(
    "AUTO_APPROVE_STORES",
    "true" if APP_ENV == "development" else "false",
).casefold() in {"1", "true", "yes", "on"}
if AUTO_APPROVE_STORES and APP_ENV != "development":
    raise RuntimeError("AUTO_APPROVE_STORES is only allowed in development")
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    if APP_ENV == "production":
        raise RuntimeError("JWT_SECRET must be configured in production")
    JWT_SECRET = "development-only-change-this-secret-before-deployment"
if len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET must be at least 32 characters")
JWT_ALGORITHM = "HS256"
JWT_TOKEN_MINUTES = 60
