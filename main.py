import os
import json
import tempfile
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from groq import Groq

# ── Configuração ────────────────────────────────────────────────────────────
BRAZIL_TZ       = ZoneInfo("America/Sao_Paulo")
SCHEDULE_SLOTS  = [(9, 0), (12, 30), (18, 0)]  # (hora, minuto) — Brasília
STATE_FILE      = "state.json"
DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]
GROQ_API_KEY    = os.environ["GROQ_API_KEY"]

DRIVE_SCOPES   = ["https://www.googleapis.com/auth/drive.readonly"]
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
                  "https://www.googleapis.com/auth/youtube.readonly"]

VIDEO_MIMETYPES = ("video/mp4", "video/quicktime", "video/x-msvideo",
                   "video/webm", "video/mpeg")

# ── Estado ──────────────────────────────────────────────────────────────────
def load_state() -> dict:
    if Path(STATE_FILE).exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"processed": [], "scheduled_slots": []}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ── Agendamento ─────────────────────────────────────────────────────────────
def get_youtube_booked_slots(yt) -> set[str]:
    """
    Retorna todos os horários já agendados no canal via playlist de uploads.
    Usa playlist em vez de search para garantir que vídeos privados/agendados
    apareçam independentemente do volume total de vídeos no canal.
    """
    booked = set()
    try:
        # 1. Descobre a playlist de uploads do canal
        ch = yt.channels().list(part="contentDetails", mine=True).execute()
        if not ch.get("items"):
            return booked
        uploads_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # 2. Pagina pela playlist para pegar todos os IDs (máx 200 para não gastar quota)
        video_ids = []
        next_page = None
        while True:
            pl = yt.playlistItems().list(
                part="contentDetails",
                playlistId=uploads_id,
                maxResults=50,
                pageToken=next_page
            ).execute()
            video_ids += [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
            next_page = pl.get("nextPageToken")
            if not next_page or len(video_ids) >= 200:
                break

        if not video_ids:
            return booked

        # 3. Verifica publishAt de cada vídeo em lotes de 50
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            resp = yt.videos().list(part="status", id=",".join(batch)).execute()
            for video in resp.get("items", []):
                publish_at = video.get("status", {}).get("publishAt")
                if publish_at:
                    dt_utc = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
                    dt_br  = dt_utc.astimezone(BRAZIL_TZ)
                    booked.add(dt_br.strftime("%Y-%m-%dT%H:00:00"))

        print(f"  {len(booked)} slot(s) ocupado(s) encontrado(s) no YouTube.")
    except Exception as e:
        print(f"  Aviso: nao foi possivel verificar slots do YouTube: {e}")
    return booked


def next_available_slot(state: dict, yt_booked: set[str]) -> datetime | None:
    now = datetime.now(BRAZIL_TZ)
    # slots já registrados pelo bot
    state_booked = set(state.get("scheduled_slots", []))

    for day_offset in range(60):
        date = now.date() + timedelta(days=day_offset)
        for hour, minute in SCHEDULE_SLOTS:
            slot = datetime(date.year, date.month, date.day,
                            hour, minute, 0, tzinfo=BRAZIL_TZ)
            slot_key  = slot.isoformat()                    # para state.json
            slot_hkey = slot.strftime("%Y-%m-%dT%H:00:00") # para comparar com YouTube

            if (slot > now + timedelta(minutes=15)
                    and slot_key  not in state_booked
                    and slot_hkey not in yt_booked):
                return slot
    return None


# ── Google APIs ─────────────────────────────────────────────────────────────
def _creds_from_file(token_file: str, scopes: list[str]) -> Credentials:
    creds = Credentials.from_authorized_user_file(token_file, scopes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return creds


def drive_service():
    return build("drive", "v3",
                 credentials=_creds_from_file("drive_token.json", DRIVE_SCOPES),
                 cache_discovery=False)


def youtube_service():
    return build("youtube", "v3",
                 credentials=_creds_from_file("youtube_token.json", YOUTUBE_SCOPES),
                 cache_discovery=False)


# ── Drive ────────────────────────────────────────────────────────────────────
def list_new_videos(drive, processed_ids: list) -> list[dict]:
    mime_filter = " or ".join(f"mimeType='{m}'" for m in VIDEO_MIMETYPES)
    query = f"'{DRIVE_FOLDER_ID}' in parents and ({mime_filter}) and trashed=false"

    result = drive.files().list(
        q=query,
        fields="files(id, name, mimeType, createdTime)",
        orderBy="createdTime"
    ).execute()

    return [f for f in result.get("files", []) if f["id"] not in processed_ids]


def download_video(drive, file_id: str, dest: str):
    request = drive.files().get_media(fileId=file_id)
    with open(dest, "wb") as fh:
        dl = MediaIoBaseDownload(fh, request, chunksize=50 * 1024 * 1024)
        done = False
        while not done:
            status, done = dl.next_chunk()
            if status:
                print(f"  Download: {int(status.progress() * 100)}%")


# ── Legenda com IA ───────────────────────────────────────────────────────────
SILENT_CAPTION = "Me segue #emagrecimento"

def transcribe_video(video_path: str, groq_client: Groq) -> str:
    """Extrai áudio do vídeo e transcreve com Whisper. Retorna '' se mudo."""
    audio_path = video_path + ".mp3"
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", video_path,
             "-vn", "-ar", "16000", "-ac", "1", "-b:a", "32k",
             audio_path, "-y", "-loglevel", "error"],
            capture_output=True, timeout=120
        )
        if result.returncode != 0 or not Path(audio_path).exists():
            return ""

        # Arquivo menor que 5KB = silêncio ou vídeo sem áudio
        if Path(audio_path).stat().st_size < 5_000:
            return ""

        with open(audio_path, "rb") as f:
            transcription = groq_client.audio.transcriptions.create(
                file=("audio.mp3", f, "audio/mpeg"),
                model="whisper-large-v3",
                language="pt",
                response_format="text"
            )

        text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
        return text

    except Exception as e:
        print(f"  Aviso na transcricao: {e}")
        return ""
    finally:
        Path(audio_path).unlink(missing_ok=True)


def generate_caption(video_path: str, groq_client: Groq) -> str:
    """Gera legenda baseada na transcrição do vídeo. Vídeo mudo = legenda padrão."""
    print("  Transcrevendo audio com Whisper...")
    transcription = transcribe_video(video_path, groq_client)

    if not transcription:
        print("  Video mudo — usando legenda padrao.")
        return SILENT_CAPTION

    print(f"  Transcricao: {transcription[:120]}{'...' if len(transcription) > 120 else ''}")

    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "Voce e especialista em conteudo para YouTube Shorts e Instagram Reels. "
                    "Com base na transcricao do video, crie uma legenda curta (max. 200 caracteres), "
                    "em portugues brasileiro, envolvente e com no maximo 3 hashtags relevantes no final. "
                    "Nao use aspas. Retorne APENAS a legenda pronta."
                ),
            },
            {
                "role": "user",
                "content": f"Transcricao do video: '{transcription[:600]}'",
            },
        ],
        max_tokens=150,
        temperature=0.85,
    )
    return resp.choices[0].message.content.strip()


# ── YouTube Upload ───────────────────────────────────────────────────────────
def upload_short(yt, video_path: str, title: str, description: str,
                 scheduled_dt: datetime) -> str:
    publish_at = (scheduled_dt.astimezone(ZoneInfo("UTC"))
                  .strftime("%Y-%m-%dT%H:%M:%S.000Z"))

    yt_title = title[:100]

    body = {
        "snippet": {
            "title": yt_title,
            "description": description,
            "tags": ["shorts", "short", "brasil"],
            "categoryId": "22",   # People & Blogs
            "defaultLanguage": "pt",
        },
        "status": {
            "privacyStatus": "private",  # torna público no horário agendado
            "publishAt": publish_at,
            "selfDeclaredMadeForKids": False,
            "madeForKids": False,
        },
    }

    ext = Path(video_path).suffix.lower()
    mime = "video/mp4" if ext in (".mp4", ".m4v") else "video/quicktime"

    media = MediaFileUpload(video_path, mimetype=mime,
                            chunksize=50 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body,
                                  media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Upload: {int(status.progress() * 100)}%")

    return response["id"]


# ── Relatório ────────────────────────────────────────────────────────────────
REPORT_FILE = "report.json"

def load_report() -> dict:
    if Path(REPORT_FILE).exists():
        with open(REPORT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"videos": []}

def save_report(report: dict):
    report["last_updated"] = datetime.now(BRAZIL_TZ).isoformat()
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

def add_to_report(report: dict, video_name: str, title: str, caption: str,
                  slot: datetime, video_id: str):
    report["videos"].insert(0, {
        "id":            video_id,
        "drive_file":    video_name,
        "title":         title,
        "caption":       caption,
        "scheduled_for": slot.isoformat(),
        "scheduled_fmt": slot.strftime("%d/%m/%Y às %Hh"),
        "thumbnail":     f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        "url":           f"https://youtube.com/shorts/{video_id}",
        "created_at":    datetime.now(BRAZIL_TZ).isoformat(),
    })


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    state  = load_state()
    report = load_report()
    groq_client = Groq(api_key=GROQ_API_KEY)
    drive = drive_service()
    yt    = youtube_service()

    new_videos = list_new_videos(drive, state["processed"])

    if not new_videos:
        print("Nenhum video novo na pasta do Drive.")
        return

    print(f"{len(new_videos)} video(s) novo(s) encontrado(s).\n")

    print("Verificando slots ja ocupados no YouTube...")
    yt_booked = get_youtube_booked_slots(yt)
    if yt_booked:
        print(f"  Slots ocupados: {sorted(yt_booked)}")

    for video in new_videos:
        slot = next_available_slot(state, yt_booked)
        if not slot:
            print("Sem slots disponiveis nos proximos 60 dias.")
            break

        print(f"> {video['name']}")
        print(f"  Agendado para: {slot.strftime('%d/%m/%Y as %Hh')} (Brasilia)")

        ext = Path(video["name"]).suffix or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name

        try:
            print("  Baixando do Drive...")
            download_video(drive, video["id"], tmp_path)

            print("  Gerando legenda com IA...")
            caption = generate_caption(tmp_path, groq_client)
            print(f"  Legenda: {caption}")

            title = caption

            print("  Enviando para o YouTube...")
            video_id = upload_short(yt, tmp_path, title, "", slot)

            print(f"  OK! youtube.com/shorts/{video_id}\n")

            state["processed"].append(video["id"])
            state["scheduled_slots"].append(slot.isoformat())
            yt_booked.add(slot.strftime("%Y-%m-%dT%H:00:00"))
            save_state(state)

            add_to_report(report, video["name"], title, caption, slot, video_id)
            save_report(report)

        except Exception as exc:
            print(f"  Erro: {exc}")
            raise
        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
