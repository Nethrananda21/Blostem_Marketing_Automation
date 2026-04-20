from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from apps.api.app.config import Settings


class EmailService:
    """
    Sends outreach emails via SMTP (Gmail by default).

    In demo/test mode (DEMO_EMAIL_OVERRIDE set), ALL recipient addresses are
    replaced with the override address so no real professionals are contacted.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def _enabled(self) -> bool:
        return bool(self.settings.smtp_user and self.settings.smtp_password)

    def _resolve_recipient(self, original_to: str) -> tuple[str, bool]:
        """Return (actual_recipient, was_overridden)."""
        override = self.settings.demo_email_override
        if override:
            return override, (override != original_to)
        return original_to, False

    def send_draft(
        self,
        *,
        to_email: str,
        to_name: str,
        subject: str,
        body: str,
        account_name: str,
        persona: str,
        approved_by: str,
    ) -> dict:
        """
        Send an approved outreach draft.
        Returns a dict describing what happened (for logging/audit trail).
        """
        if not self._enabled:
            return {
                "status": "skipped",
                "reason": "SMTP not configured (set SMTP_USER + SMTP_PASSWORD)",
                "original_to": to_email,
            }

        recipient, overridden = self._resolve_recipient(to_email)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Blostem AI <{self.settings.smtp_from}>"
        msg["To"] = recipient
        if overridden:
            # Stamp a header so we can see the original recipient in the received mail
            msg["X-Blostem-Original-To"] = to_email
            msg["X-Blostem-Demo-Mode"] = "true"

        # Plain-text part
        plain_preamble = ""
        if overridden:
            plain_preamble = (
                f"[DEMO MODE — original recipient: {to_email} ({to_name}), "
                f"account: {account_name}, persona: {persona}]\n"
                f"Approved by: {approved_by}\n"
                f"{'─' * 60}\n\n"
            )
        msg.attach(MIMEText(plain_preamble + body, "plain"))

        # HTML part (same content, light formatting)
        html_preamble = ""
        if overridden:
            html_preamble = (
                f"<div style='background:#fff3cd;border:1px solid #ffc107;padding:10px 14px;"
                f"margin-bottom:16px;border-radius:6px;font-family:monospace;font-size:12px;'>"
                f"<strong>DEMO MODE</strong> — Original recipient: {to_email} ({to_name})<br>"
                f"Account: {account_name} &nbsp;|&nbsp; Persona: {persona}<br>"
                f"Approved by: {approved_by}"
                f"</div>"
            )
        html_body = f"<html><body>{html_preamble}<pre style='font-family:Georgia,serif;font-size:14px;line-height:1.6;white-space:pre-wrap'>{body}</pre></body></html>"
        msg.attach(MIMEText(html_body, "html"))

        context = ssl.create_default_context()
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(self.settings.smtp_user, self.settings.smtp_password)
            server.sendmail(self.settings.smtp_from, recipient, msg.as_string())

        return {
            "status": "sent",
            "recipient": recipient,
            "original_to": to_email,
            "overridden": overridden,
            "subject": subject,
        }
