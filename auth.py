"""
Rode este script UMA VEZ no seu computador para gerar os tokens
de acesso ao Google Drive e ao YouTube.

Pré-requisito: ter o arquivo client_secret.json na mesma pasta.
"""
import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

DRIVE_SCOPES   = ["https://www.googleapis.com/auth/drive"]
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube",
                  "https://www.googleapis.com/auth/youtube.upload",
                  "https://www.googleapis.com/auth/youtube.readonly",
                  "https://www.googleapis.com/auth/yt-analytics.readonly"]

CLIENT_SECRET = "client_secret.json"


def authorize(scopes: list[str], token_file: str, service_name: str):
    if Path(token_file).exists():
        print(f"  {token_file} já existe — pulando {service_name}.")
        return

    print(f"\n{'='*50}")
    print(f"  Autorizando: {service_name}")
    print(f"{'='*50}")
    print("  O navegador vai abrir. Faça login com a conta Google")
    print("  que tem acesso ao Drive e ao canal do YouTube.\n")

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, scopes)
    creds = flow.run_local_server(port=0, prompt="consent",
                                  access_type="offline")

    with open(token_file, "w") as f:
        f.write(creds.to_json())

    print(f"\n  OK! Token salvo em: {token_file}")


def main():
    if not Path(CLIENT_SECRET).exists():
        print(f"ERRO: arquivo '{CLIENT_SECRET}' não encontrado.")
        print("Baixe-o do Google Cloud Console e coloque nesta pasta.")
        return

    # Drive
    authorize(DRIVE_SCOPES, "drive_token.json", "Google Drive (leitura)")

    # YouTube — pode exigir login separado se for canal diferente
    authorize(YOUTUBE_SCOPES, "youtube_token.json", "YouTube (upload)")

    print("\nAutorizacao completa!")
    print("Próximos passos:")
    print("  1. Copie o conteúdo de drive_token.json  → secret DRIVE_TOKEN no GitHub")
    print("  2. Copie o conteúdo de youtube_token.json → secret YOUTUBE_TOKEN no GitHub")
    print("  3. Guarde client_secret.json como secret GOOGLE_CLIENT_SECRET também")
    print("\nNUNCA suba esses arquivos para o repositório público.")


if __name__ == "__main__":
    main()
