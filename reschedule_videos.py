"""
Reagenda vídeos futuros do YouTube quando um horário de postagem é alterado.
Chamado pelo workflow reschedule-videos.yml via GitHub Actions.

Env vars: OLD_HOUR, OLD_MINUTE, NEW_HOUR, NEW_MINUTE
"""
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")
UTC_TZ    = ZoneInfo("UTC")

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def main():
    old_h = int(os.environ["OLD_HOUR"])
    old_m = int(os.environ["OLD_MINUTE"])
    new_h = int(os.environ["NEW_HOUR"])
    new_m = int(os.environ["NEW_MINUTE"])

    print(f"Reagendando {old_h:02d}:{old_m:02d} → {new_h:02d}:{new_m:02d}")

    creds = Credentials.from_authorized_user_file("youtube_token.json", YOUTUBE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open("youtube_token.json", "w") as f:
            f.write(creds.to_json())

    yt  = build("youtube", "v3", credentials=creds, cache_discovery=False)
    now = datetime.now(BRAZIL_TZ)

    # ── Carrega report.json ──────────────────────────────────────────────────
    report_path = Path("report.json")
    if not report_path.exists():
        print("report.json não encontrado.")
        return
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    # ── Encontra vídeos futuros no horário antigo ────────────────────────────
    to_move = []
    for v in report.get("videos", []):
        sf = v.get("scheduled_for")
        if not sf:
            continue
        try:
            dt_br = datetime.fromisoformat(sf).astimezone(BRAZIL_TZ)
            if dt_br.hour == old_h and dt_br.minute == old_m and dt_br > now:
                to_move.append((v, dt_br))
        except Exception:
            pass

    print(f"  {len(to_move)} vídeo(s) futuro(s) encontrado(s) nesse horário.")
    if not to_move:
        return

    # ── Reagenda cada vídeo ──────────────────────────────────────────────────
    for v, old_dt in to_move:
        new_dt = old_dt.replace(hour=new_h, minute=new_m, second=0, microsecond=0)
        if new_dt <= now:
            new_dt += timedelta(days=1)

        publish_at = new_dt.astimezone(UTC_TZ).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        try:
            yt.videos().update(
                part="status",
                body={
                    "id": v["id"],
                    "status": {
                        "privacyStatus": "private",
                        "publishAt": publish_at,
                        "selfDeclaredMadeForKids": False,
                    },
                },
            ).execute()

            v["scheduled_for"] = new_dt.isoformat()
            v["scheduled_fmt"] = new_dt.strftime("%d/%m/%Y às %Hh")

            old_fmt = old_dt.strftime("%d/%m %H:%M")
            new_fmt = new_dt.strftime("%d/%m %H:%M")
            print(f"  ✓ {v.get('title','?')[:50]}  {old_fmt} → {new_fmt}")

        except Exception as e:
            print(f"  ✗ Erro em {v['id']}: {e}")

    # ── Atualiza state.json ──────────────────────────────────────────────────
    state_path = Path("state.json")
    if state_path.exists():
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)

        new_slots = []
        for slot_iso in state.get("scheduled_slots", []):
            try:
                dt_br = datetime.fromisoformat(slot_iso).astimezone(BRAZIL_TZ)
                if dt_br.hour == old_h and dt_br.minute == old_m and dt_br > now:
                    new_dt = dt_br.replace(hour=new_h, minute=new_m, second=0, microsecond=0)
                    if new_dt <= now:
                        new_dt += timedelta(days=1)
                    new_slots.append(new_dt.isoformat())
                else:
                    new_slots.append(slot_iso)
            except Exception:
                new_slots.append(slot_iso)

        state["scheduled_slots"] = new_slots
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    # ── Salva report.json ────────────────────────────────────────────────────
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("  report.json e state.json atualizados.")


if __name__ == "__main__":
    main()
