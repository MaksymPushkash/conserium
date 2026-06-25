from typing import Any
from urllib.parse import urlencode

from authlib.integrations.httpx_client import AsyncOAuth2Client

from src.auth.schemas import OAuthProfile
from src.kit.exceptions import OAuthAuthenticationException


class GoogleOAuthClient:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def authorization_url(self, *, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    async def fetch_user_profile(self, *, code: str, redirect_uri: str) -> OAuthProfile:
        async with AsyncOAuth2Client(client_id=self._client_id, client_secret=self._client_secret) as client:
            await client.fetch_token(
                "https://oauth2.googleapis.com/token",
                code=code,
                redirect_uri=redirect_uri,
            )
            userinfo = await client.get("https://www.googleapis.com/oauth2/v3/userinfo")
            profile = userinfo.json()

        email = _string_value(profile.get("email"))
        if email is None:
            raise OAuthAuthenticationException("no_email", "oauth provider did not return an email")
        return OAuthProfile(email=email, display_name=_string_value(profile.get("name")) or email)


class GithubOAuthClient:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def authorization_url(self, *, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "scope": "user:email",
            "state": state,
            "redirect_uri": redirect_uri,
        }
        return f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    async def fetch_user_profile(self, *, code: str, redirect_uri: str) -> OAuthProfile:
        async with AsyncOAuth2Client(client_id=self._client_id, client_secret=self._client_secret) as client:
            token_data = await client.fetch_token(
                "https://github.com/login/oauth/access_token",
                code=code,
                redirect_uri=redirect_uri,
            )
            if not token_data.get("access_token"):
                raise OAuthAuthenticationException("no_access_token", "oauth provider did not return an access token")

            user_response = await client.get("https://api.github.com/user")
            user_info = user_response.json()

            email = _string_value(user_info.get("email"))
            if email is None:
                emails_response = await client.get("https://api.github.com/user/emails")
                email = _primary_github_email(emails_response.json())

        if email is None:
            raise OAuthAuthenticationException("no_email", "oauth provider did not return an email")
        return OAuthProfile(email=email, display_name=_string_value(user_info.get("name")) or email)


def _primary_github_email(emails: Any) -> str | None:
    if not isinstance(emails, list):
        return None
    primary = next(
        (
            email
            for email in emails
            if isinstance(email, dict) and email.get("primary") and email.get("verified")
        ),
        None,
    )
    fallback = next((email for email in emails if isinstance(email, dict)), None)
    return _string_value((primary or fallback or {}).get("email"))


def _string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


OAuthProvider = GoogleOAuthClient | GithubOAuthClient
