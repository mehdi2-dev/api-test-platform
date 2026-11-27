"""Use case'ler: giriş, token yenileme ve token'dan kullanıcıyı bulma."""

from app.application.errors import AuthenticationFailed, InvalidToken, TooManyAttempts
from app.application.ports.auth import LoginAttemptLimiter, TokenPair, TokenService
from app.application.ports.users import PasswordHasher, UserRepository
from app.domain.users import User

INVALID_CREDENTIALS = "E-posta veya şifre hatalı"
USER_MISSING_OR_INACTIVE = "Kullanıcı bulunamadı veya pasif"


class Login:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
        limiter: LoginAttemptLimiter,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        self._limiter = limiter

    def __call__(self, email: str, password: str, client: str) -> TokenPair:
        email = User.normalize_email(email)

        # Kaba kuvvet koruması: aynı e-posta + istemci için hatalı deneme sınırı
        key = f"{client}|{email}"
        wait = self._limiter.retry_after(key)
        if wait:
            raise TooManyAttempts(wait)

        user = self._users.get_by_email(email)
        # Hangi bilginin yanlış olduğunu söylemiyoruz: e-posta tahmin edilmesin
        if user is None or not self._hasher.verify(password, user.hashed_password):
            self._limiter.failed(key)
            raise AuthenticationFailed(INVALID_CREDENTIALS)
        if not user.is_active:
            raise AuthenticationFailed("Hesabınız pasif durumda")

        self._limiter.succeeded(key)
        return self._tokens.issue(user)


class RefreshTokens:
    def __init__(self, users: UserRepository, tokens: TokenService) -> None:
        self._users = users
        self._tokens = tokens

    def __call__(self, refresh_token: str) -> TokenPair:
        try:
            user_id = self._tokens.user_id_from(refresh_token, "refresh")
        except InvalidToken as exc:
            raise AuthenticationFailed("Refresh token geçersiz veya süresi dolmuş") from exc

        user = self._users.get(user_id)
        if user is None or not user.is_active:
            raise AuthenticationFailed(USER_MISSING_OR_INACTIVE)
        return self._tokens.issue(user)


class AuthenticateUser:
    """Her istekte gelen access token'dan oturum açmış kullanıcıyı bulur."""

    def __init__(self, users: UserRepository, tokens: TokenService) -> None:
        self._users = users
        self._tokens = tokens

    def __call__(self, access_token: str) -> User:
        try:
            user_id = self._tokens.user_id_from(access_token, "access")
        except InvalidToken as exc:
            raise AuthenticationFailed("Token geçersiz veya süresi dolmuş") from exc

        user = self._users.get(user_id)
        if user is None or not user.is_active:
            raise AuthenticationFailed(USER_MISSING_OR_INACTIVE)
        return user
