from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from ..config import get_settings

_LEDGER_PATH = Path(__file__).resolve().parents[2] / "data" / "inbox" / "ledger.json"


class ReplyRecord(BaseModel):
    user: str
    channel: str
    message_id: str = ""
    thread_id: str = ""
    date: str
    at: str
    text_preview: str = ""


class InboxLedger(BaseModel):
    replies: list[ReplyRecord] = Field(default_factory=list)


def _ledger_path() -> Path:
    s = get_settings()
    if s.inbox_ledger_path.strip():
        return Path(s.inbox_ledger_path)
    return _LEDGER_PATH


class InboxStore:
    def load(self) -> InboxLedger:
        path = _ledger_path()
        if not path.is_file():
            return InboxLedger()
        return InboxLedger.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, ledger: InboxLedger) -> None:
        path = _ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ledger.model_dump_json(indent=2), encoding="utf-8")

    def replies_on_date(self, d: date | None = None) -> list[ReplyRecord]:
        day = (d or date.today()).isoformat()
        return [r for r in self.load().replies if r.date == day]

    def user_replies_today(self, user: str, channel: str | None = None) -> int:
        u = user.lower().lstrip("@")
        today = date.today().isoformat()
        return sum(
            1
            for r in self.load().replies
            if r.date == today
            and r.user.lower() == u
            and (channel is None or r.channel == channel)
        )

    def last_reply_to_user(self, user: str) -> ReplyRecord | None:
        u = user.lower().lstrip("@")
        matches = [r for r in self.load().replies if r.user.lower() == u]
        if not matches:
            return None
        return max(matches, key=lambda r: r.at)

    def record_reply(
        self,
        *,
        user: str,
        channel: str,
        message_id: str,
        thread_id: str,
        text_sent: str,
    ) -> int:
        ledger = self.load()
        now = datetime.now(timezone.utc)
        ledger.replies.append(
            ReplyRecord(
                user=user.lower().lstrip("@"),
                channel=channel,
                message_id=message_id,
                thread_id=thread_id,
                date=now.date().isoformat(),
                at=now.isoformat(),
                text_preview=text_sent[:120],
            )
        )
        self.save(ledger)
        return self.user_replies_today(user, channel)
