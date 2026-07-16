"""instagrapi client with session persistence and Lorena account settings."""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.parse
from pathlib import Path
from typing import Any

from ..config import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_SESSION = Path(__file__).resolve().parents[2] / "data" / "instagram" / "session.json"

_COOKIE_HELP = (
    "Password login blocked by Instagram (common with 2FA / new device / IP). "
    "Use browser cookies instead:\n"
    "  1. Log into instagram.com in Chrome\n"
    "  2. Cookie-Editor extension → Export → JSON\n"
    "  3. FRIDAY_IG_SESSION_JSON='...' in .env  OR  python -m brain.instagram.run login-cookies\n"
    "  Or set FRIDAY_IG_SESSIONID from the sessionid cookie value only."
)


def _cookies_from_editor_export(raw: str | dict | list) -> dict[str, str]:
    data = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(data, dict):
        if "cookies" in data and isinstance(data["cookies"], dict):
            return {str(k): str(v) for k, v in data["cookies"].items()}
        if "sessionid" in data:
            return {str(k): str(v) for k, v in data.items()}
    if isinstance(data, list):
        out: dict[str, str] = {}
        for row in data:
            if not isinstance(row, dict):
                continue
            domain = str(row.get("domain", ""))
            if "instagram.com" not in domain:
                continue
            name = row.get("name")
            value = row.get("value")
            if name and value is not None:
                out[str(name)] = urllib.parse.unquote(str(value))
        if out:
            return out
    raise ValueError("Unrecognized cookie JSON — export from Cookie-Editor on instagram.com")


def _user_id_from_cookies(cookies: dict[str, str]) -> str:
    if cookies.get("ds_user_id"):
        return str(cookies["ds_user_id"])
    sessionid = cookies.get("sessionid", "")
    if sessionid:
        import re

        m = re.match(r"^(\d+)", sessionid)
        if m:
            return m.group(1)
    return ""


def _apply_browser_cookies(cl: Any, cookies: dict[str, str]) -> None:
    """Apply Cookie-Editor export and wire web session into instagrapi."""
    sessionid = cookies.get("sessionid", "")
    if not sessionid:
        raise ValueError("Cookie export missing sessionid")

    user_id = _user_id_from_cookies(cookies)
    cl.settings["cookies"] = cookies
    cl.settings["authorization_data"] = {
        "ds_user_id": user_id,
        "sessionid": sessionid,
        # Web cookies authenticate via Cookie header, not Bearer Authorization.
        "should_use_header_over_cookies": False,
    }
    if cookies.get("mid"):
        cl.settings["mid"] = cookies["mid"]
    if cookies.get("rur"):
        cl.settings["ig_u_rur"] = cookies["rur"]

    cl.init()
    cl.private.headers.pop("Authorization", None)

    if cookies.get("csrftoken"):
        cl.private.headers["X-CSRFToken"] = cookies["csrftoken"]

    cl.inject_sessionid_to_public()


def _warmup_mobile_session(cl: Any) -> None:
    """Post-login mobile warmup; unlocks POST endpoints for some cookie sessions."""
    try:
        if cl.login_flow():
            logger.info("Mobile session warmup OK")
            return
    except Exception as exc:
        logger.debug("login_flow warmup failed: %s", exc)

    for label, toggled in (("auth_header", True), ("cookies", False)):
        try:
            cl.authorization_data = dict(cl.authorization_data or {})
            cl.authorization_data["should_use_header_over_cookies"] = toggled
            cl.settings["authorization_data"] = cl.authorization_data
            if toggled and cl.authorization:
                cl.private.headers["Authorization"] = cl.authorization
            else:
                cl.private.headers.pop("Authorization", None)
            cl.get_reels_tray_feed("cold_start")
            logger.info("Mobile session warmup OK (%s)", label)
            return
        except Exception as exc:
            logger.debug("reels_tray warmup (%s) failed: %s", label, exc)


_DEFAULT_COOKIES = _DEFAULT_SESSION.parent / "cookies.json"


class FridayInstagramClient:
    """Thin wrapper around instagrapi.Client with Friday defaults."""

    def __init__(self) -> None:
        self._client: Any | None = None
        self._settings = get_settings()

    @property
    def session_path(self) -> Path:
        raw = self._settings.ig_session_path.strip()
        return Path(raw) if raw else _DEFAULT_SESSION

    def _build_client(self) -> Any:
        from instagrapi import Client

        cl = Client()
        cl.delay_range = [self._settings.ig_delay_min, self._settings.ig_delay_max]
        if self._settings.ig_proxy:
            cl.set_proxy(self._settings.ig_proxy)
        self._configure_interactive_handlers(cl)
        return cl

    @staticmethod
    def _configure_interactive_handlers(cl: Any) -> None:
        def _challenge_code_handler(username: str, choice: Any = None) -> str:
            try:
                return input(
                    f"Instagram security code for @{username} ({choice or 'email/sms'}): "
                ).strip()
            except EOFError as exc:
                raise RuntimeError(
                    "Instagram sent an email/SMS challenge. Run login in an interactive terminal."
                ) from exc

        cl.challenge_code_handler = _challenge_code_handler

    def _save_session(self, cl: Any) -> None:
        path = self.session_path
        path.parent.mkdir(parents=True, exist_ok=True)
        cl.dump_settings(path)
        self._client = cl

    def login_by_cookies(self, cookie_json: str | None = None) -> Any:
        """Login from Cookie-Editor JSON or FRIDAY_IG_SESSION_JSON / FRIDAY_IG_SESSIONID."""
        cl = self._build_client()
        raw = (cookie_json or self._settings.ig_session_json or "").strip()
        sessionid = self._settings.ig_sessionid.strip()

        if raw:
            cookies = _cookies_from_editor_export(raw)
        elif sessionid:
            cookies = {"sessionid": sessionid, "ds_user_id": _user_id_from_cookies({"sessionid": sessionid})}
        elif _DEFAULT_COOKIES.is_file():
            cookies = _cookies_from_editor_export(_DEFAULT_COOKIES.read_text(encoding="utf-8"))
        else:
            raise RuntimeError(
                "Set FRIDAY_IG_SESSION_JSON, FRIDAY_IG_SESSIONID, or save cookies to "
                f"{_DEFAULT_COOKIES}"
            )

        _apply_browser_cookies(cl, cookies)
        try:
            info = cl.account_info()
        except Exception as exc:
            raise RuntimeError(
                "Browser cookies did not authenticate with Instagram. "
                "Re-export while logged in at instagram.com (Cookie-Editor → Export JSON), "
                "preferably from the same network/IP as this machine. "
                f"Underlying error: {exc}"
            ) from exc
        cl.username = getattr(info, "username", "") or cl.username
        logger.info("Cookie session verified for @%s", getattr(info, "username", "?"))
        _warmup_mobile_session(cl)
        self._save_session(cl)
        logger.info("Instagram session restored from browser cookies")
        return cl

    def login(
        self,
        *,
        verification_code: str | None = None,
        prompt_2fa: bool = False,
    ) -> Any:
        """Fresh login; handles 2FA and email challenges. Saves session on success."""
        from instagrapi.exceptions import BadPassword, TwoFactorRequired

        sessionid = self._settings.ig_sessionid.strip()
        if self._settings.ig_session_json.strip() or sessionid:
            return self.login_by_cookies()

        cl = self._build_client()
        user = self._settings.ig_username.strip()
        password = self._settings.ig_password
        if not user or not password:
            missing = []
            if not user:
                missing.append("FRIDAY_IG_USERNAME")
            if not password:
                missing.append("FRIDAY_IG_PASSWORD")
            raise RuntimeError(
                f"Missing {', '.join(missing)} — set in repo-root .env or brain/.env"
            )

        code = (verification_code or self._settings.ig_verification_code or "").strip()

        def _attempt(vc: str) -> None:
            cl.login(user, password, verification_code=vc)

        def _prompt_2fa_code() -> str:
            try:
                return input(
                    "Instagram 2FA code (6 digits from authenticator app, or backup code): "
                ).strip()
            except EOFError as exc:
                raise RuntimeError(
                    "2FA required in an interactive terminal, or use login-cookies."
                ) from exc

        try:
            _attempt(code)
        except (TwoFactorRequired, BadPassword) as exc:
            if not code and prompt_2fa:
                print(
                    "Instagram rejected password login — often 2FA/challenge, not wrong password."
                )
                code = _prompt_2fa_code()
                if not code:
                    raise RuntimeError(_COOKIE_HELP) from exc
                try:
                    _attempt(code)
                except (TwoFactorRequired, BadPassword) as exc2:
                    raise RuntimeError(
                        "Instagram still blocked login after 2FA code. "
                        "This usually means the API never entered the real 2FA flow "
                        "(Instagram wants email verification or rejects automated device login). "
                        "Your 2FA code may be fine — use browser cookies instead:\n"
                        "  python -m brain.instagram.run login-cookies --file cookies.json"
                    ) from exc2
            elif isinstance(exc, TwoFactorRequired):
                raise RuntimeError(
                    "Instagram 2FA required. Re-run: python -m brain.instagram.run login"
                ) from exc
            else:
                raise RuntimeError(f"{exc}\n\n{_COOKIE_HELP}") from exc

        self._save_session(cl)
        logger.info("Instagram login OK for @%s — session saved to %s", user, self.session_path)
        return cl

    def load(self) -> Any:
        if self._client is not None:
            return self._client

        cl = self._build_client()
        path = self.session_path

        if path.is_file():
            try:
                cl.load_settings(path)
                cl.account_info()
                self._client = cl
                logger.info("Instagram session loaded from %s", path)
                return cl
            except Exception as exc:
                logger.warning("Saved session invalid (%s) — trying cookies", exc)

        if _DEFAULT_COOKIES.is_file():
            try:
                return self.login_by_cookies(_DEFAULT_COOKIES.read_text(encoding="utf-8"))
            except Exception as exc:
                raise RuntimeError(
                    f"Cookie session expired or invalid ({exc}). "
                    "Log into instagram.com again, export fresh cookies, then:\n"
                    "  python -m brain.instagram.run login-cookies --file brain/data/instagram/cookies.json"
                ) from exc

        if self._settings.ig_session_json.strip() or self._settings.ig_sessionid.strip():
            return self.login_by_cookies()

        user = self._settings.ig_username.strip()
        password = self._settings.ig_password
        if not user or not password:
            raise RuntimeError(
                "No valid session. Export fresh browser cookies:\n"
                "  python -m brain.instagram.run login-cookies --file brain/data/instagram/cookies.json"
            )

        self.login(prompt_2fa=False)
        return self._client

    def _login_with_saved_or_password(self, cl: Any, path: Path) -> Any:
        cl.account_info()
        return cl

    def client(self) -> Any:
        return self.load()

    def me(self) -> dict[str, Any]:
        cl = self.client()
        info = cl.account_info()
        return {
            "username": getattr(info, "username", ""),
            "user_id": str(getattr(info, "pk", "")),
            "full_name": getattr(info, "full_name", ""),
        }

    def doctor(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        s = self._settings

        def row(name: str, status: str, detail: str) -> None:
            rows.append({"check": name, "status": status, "detail": detail})

        try:
            import instagrapi  # noqa: F401

            row("instagrapi", "pass", "installed")
        except ImportError:
            row("instagrapi", "fail", "pip install instagrapi")
            return rows

        has_creds = bool(
            s.ig_session_json.strip()
            or s.ig_sessionid.strip()
            or (s.ig_username and s.ig_password)
        )
        if has_creds:
            row("credentials", "pass", "username/password, sessionid, or cookie JSON configured")
        else:
            row("credentials", "fail", "Set FRIDAY_IG_* creds or FRIDAY_IG_SESSION_JSON")
            return rows

        try:
            info = self.me()
            row("login", "pass", f"@{info.get('username', '?')}")
        except Exception as exc:
            row("login", "fail", str(exc)[:200])
            row("hint", "warn", "If password login fails, use: python -m brain.instagram.run login-cookies")

        return rows

    @staticmethod
    def human_pause(min_s: float = 1.5, max_s: float = 4.0) -> None:
        time.sleep(random.uniform(min_s, max_s))


_client: FridayInstagramClient | None = None


def get_instagram_client() -> FridayInstagramClient:
    global _client
    if _client is None:
        _client = FridayInstagramClient()
    return _client
