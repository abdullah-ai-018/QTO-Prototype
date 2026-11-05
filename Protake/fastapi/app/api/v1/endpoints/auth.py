from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import AuthResponse, LoginRequest, RefreshRequest, TokenPair
from app.schemas.user import UserCreate, UserRead
from app.services.auth_service import AuthService
from app.utils.security import TokenError, decode_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: DbSession) -> AuthResponse:
    service = AuthService(db)
    user = service.register(payload)
    tokens = service.issue_tokens(user)
    return AuthResponse(user=UserRead.model_validate(user), **tokens.model_dump())


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: DbSession) -> AuthResponse:
    service = AuthService(db)
    user = service.authenticate(payload.email, payload.password)
    tokens = service.issue_tokens(user)
    return AuthResponse(user=UserRead.model_validate(user), **tokens.model_dump())


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    try:
        user_id = decode_token(payload.refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return AuthService(db).refresh(user_id)


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
