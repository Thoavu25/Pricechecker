from datetime import datetime, timedelta, timezone

import jwt

from app.application.ports import TokenService
from app.domain.errors import UnauthorizedError
from app.config import JWT_ALGORITHM, JWT_SECRET, JWT_TOKEN_MINUTES


class JwtTokenService(TokenService):
    def create(self, user_id: int, role: str) -> str:
        expires = datetime.now(timezone.utc) + timedelta(minutes=JWT_TOKEN_MINUTES)
        return jwt.encode(
            {"sub": str(user_id), "role": role, "exp": expires},
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )

    def read_claims(self, token: str) -> dict:
        try:
            return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.PyJWTError:
            raise UnauthorizedError("Invalid or expired token")
