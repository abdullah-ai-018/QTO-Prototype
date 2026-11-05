from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPair
from app.schemas.user import UserCreate
from app.utils.security import create_access_token, create_refresh_token, hash_password, verify_password


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)

    def register(self, payload: UserCreate) -> User:
        if self.users.get_by_email(payload.email):
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
        return self.users.create(
            email=payload.email,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            role=payload.role,
        )

    def authenticate(self, email: str, password: str) -> User:
        user = self.users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")
        return user

    @staticmethod
    def issue_tokens(user: User) -> TokenPair:
        return TokenPair(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    def refresh(self, user_id: int) -> TokenPair:
        user = self.users.get_or_404(user_id)
        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")
        return self.issue_tokens(user)
