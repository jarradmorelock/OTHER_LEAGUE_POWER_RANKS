"""Tuesday power-ranking report, matching Ironbound's editorial email convention."""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from .models import LeagueConfig


def build_power_rankings_email(configs: list[LeagueConfig], *, root: Path, sender: str, recipients: list[str], week: int) -> EmailMessage:
    if not configs or not recipients:
        raise ValueError("Email requires leagues and at least one recipient")
    message = EmailMessage()
    message["From"] = f"Ironbound Publications <{sender}>"
    message["To"] = ", ".join(recipients)
    message["Subject"] = f"Other League Power Rankings — Week {week} — Tuesday Edition"
    message.set_content(
        "Official power rankings and playoff forecasts for the six other leagues.\n"
        "The attached charts and machine-readable ranking handoffs are the authority\n"
        "for each league's Editorial Desk newspaper.\n"
    )
    for config in configs:
        directory = Path(root) / config.key
        for kind, filename in (("power-rankings", "power-rankings.png"), ("playoff-forecast", "championship-odds.png")):
            image = directory / filename
            if not image.is_file():
                raise FileNotFoundError(str(image))
            message.add_attachment(image.read_bytes(), maintype="image", subtype="png",
                                   filename=f"{config.key}-{kind}-week-{week}.png")
    return message


def send_power_rankings_email(configs: list[LeagueConfig], *, root: Path, week: int) -> str:
    sender = os.environ.get("PUBLICATIONS_EMAIL_FROM", "").strip()
    to = os.environ.get("PUBLICATIONS_EMAIL_TO", "")
    password = os.environ.get("PUBLICATIONS_EMAIL_APP_PASSWORD", "").replace(" ", "")
    recipients = [value.strip() for value in to.replace(";", ",").split(",") if value.strip()]
    if not sender or not recipients or not password:
        raise ValueError("Configure PUBLICATIONS_EMAIL_FROM, PUBLICATIONS_EMAIL_TO, and PUBLICATIONS_EMAIL_APP_PASSWORD")
    message = build_power_rankings_email(configs, root=root, sender=sender, recipients=recipients, week=week)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)
    return f"Sent {len(list(message.iter_attachments()))} graphics to {len(recipients)} recipients"
