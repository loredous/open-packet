# open_packet/store/exporter.py
from __future__ import annotations
import os
from open_packet.store.models import Message, Bulletin


def export_messages(messages: list[Message], base_path: str) -> None:
    for msg in messages:
        if msg.sent:
            folder = os.path.join(base_path, "sent")
        else:
            folder = os.path.join(base_path, "inbox", msg.to_call.upper())
        os.makedirs(folder, exist_ok=True)
        date_str = msg.timestamp.strftime("%Y-%m-%d") if msg.timestamp else "0000-00-00"
        safe_subject = "".join(c if c.isalnum() or c in "-_ " else "_" for c in msg.subject)[:40]
        filename = f"{date_str}-{msg.bbs_id}-{safe_subject}.txt".replace(" ", "-")
        path = os.path.join(folder, filename)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(f"From:    {msg.from_call}\n")
                f.write(f"To:      {msg.to_call}\n")
                f.write(f"Subject: {msg.subject}\n")
                f.write(f"Date:    {msg.timestamp.isoformat() if msg.timestamp else ''}\n")
                f.write("-" * 40 + "\n")
                f.write(msg.body)


def export_bulletins(bulletins: list[Bulletin], base_path: str) -> None:
    for bul in bulletins:
        if bul.body is None:
            continue  # header-only; body not yet retrieved
        folder = os.path.join(base_path, "bulletins", bul.category.upper())
        os.makedirs(folder, exist_ok=True)
        date_str = bul.timestamp.strftime("%Y-%m-%d") if bul.timestamp else "0000-00-00"
        safe_subject = "".join(c if c.isalnum() or c in "-_ " else "_" for c in bul.subject)[:40]
        filename = f"{date_str}-{bul.bbs_id}-{safe_subject}.txt".replace(" ", "-")
        path = os.path.join(folder, filename)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(f"Category: {bul.category}\n")
                f.write(f"From:     {bul.from_call}\n")
                f.write(f"Subject:  {bul.subject}\n")
                f.write(f"Date:     {bul.timestamp.isoformat() if bul.timestamp else ''}\n")
                f.write("-" * 40 + "\n")
                f.write(bul.body)
