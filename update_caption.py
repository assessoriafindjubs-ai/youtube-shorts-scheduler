"""
Atualiza o título/legenda de um vídeo no YouTube e no report.json.
Chamado pelo workflow update-caption.yml via GitHub Actions.
"""
import os
import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def main():
    video_id  = os.environ["VIDEO_ID"]
    new_title = os.environ["NEW_TITLE"].strip()[:100]

    creds = Credentials.from_authorized_user_file("youtube_token.json", YOUTUBE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open("youtube_token.json", "w") as f:
            f.write(creds.to_json())

    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    resp = yt.videos().list(part="snippet", id=video_id).execute()
    if not resp.get("items"):
        raise SystemExit(f"Video {video_id} não encontrado no canal.")

    snippet = resp["items"][0]["snippet"]
    snippet["title"] = new_title

    yt.videos().update(
        part="snippet",
        body={"id": video_id, "snippet": snippet},
    ).execute()
    print(f"  Título atualizado: {new_title}")

    report_path = Path("report.json")
    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
        for v in report.get("videos", []):
            if v.get("id") == video_id:
                v["title"]   = new_title
                v["caption"] = new_title
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print("  report.json atualizado.")


if __name__ == "__main__":
    main()
