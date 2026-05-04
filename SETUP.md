# Setup — YouTube Shorts Auto-Scheduler

Siga cada etapa na ordem. Leva cerca de 30 minutos na primeira vez.

---

## ETAPA 1 — Criar projeto no Google Cloud

1. Acesse https://console.cloud.google.com
2. Clique em **Select a project → New Project**
3. Dê um nome (ex: `youtube-shorts-bot`) e clique em **Create**
4. Com o projeto selecionado, vá em **APIs & Services → Library**
5. Busque e ative as duas APIs:
   - **Google Drive API** → Enable
   - **YouTube Data API v3** → Enable

---

## ETAPA 2 — Criar credenciais OAuth 2.0

1. Vá em **APIs & Services → Credentials**
2. Clique em **+ Create Credentials → OAuth client ID**
3. Se solicitado, configure a **OAuth consent screen**:
   - User Type: **External**
   - App name: qualquer nome
   - Email: seu e-mail
   - Salve e avance até o fim (não precisa publicar)
   - Em **Test users**, adicione seu e-mail do Google
4. De volta em Create Credentials → OAuth client ID:
   - Application type: **Desktop app**
   - Name: `shorts-bot`
   - Clique em **Create**
5. Clique em **Download JSON** → renomeie o arquivo para `client_secret.json`
6. Coloque o `client_secret.json` dentro da pasta `youtube-shorts-scheduler`

---

## ETAPA 3 — Instalar Python e dependências (local)

```bash
# No terminal, dentro da pasta youtube-shorts-scheduler
pip install -r requirements.txt
```

---

## ETAPA 4 — Autorizar acesso ao Drive e YouTube (local, uma vez só)

```bash
python auth.py
```

- O navegador vai abrir **duas vezes** (uma para Drive, uma para YouTube)
- Faça login com a conta Google que tem o canal do YouTube
- Aceite as permissões
- Dois arquivos serão criados: `drive_token.json` e `youtube_token.json`

> ⚠️ NUNCA suba esses arquivos para o GitHub

---

## ETAPA 5 — Obter o ID da pasta do Google Drive

1. Abra o Google Drive e navegue até a pasta onde você vai colocar os vídeos
2. Olhe a URL do navegador:  
   `https://drive.google.com/drive/folders/XXXXXXXXXXXXXXXXXXXXXXXX`
3. Copie o trecho `XXXXXXXXXXXXXXXXXXXXXXXX` — esse é o **DRIVE_FOLDER_ID**

---

## ETAPA 6 — Obter a chave da API Groq (IA de legendas)

1. Acesse https://console.groq.com
2. Crie uma conta gratuita (tem plano free generoso)
3. Vá em **API Keys → Create API Key**
4. Copie a chave — esse é o **GROQ_API_KEY**

---

## ETAPA 7 — Criar repositório no GitHub

1. Acesse https://github.com e crie uma conta se não tiver
2. Clique em **New repository**
   - Nome: `youtube-shorts-scheduler`
   - Visibilidade: **Private** (importante!)
   - Clique em **Create repository**
3. No terminal, dentro da pasta do projeto:

```bash
git init
git add .
git commit -m "setup inicial"
git remote add origin https://github.com/SEU_USUARIO/youtube-shorts-scheduler.git
git push -u origin main
```

---

## ETAPA 8 — Configurar os Secrets no GitHub

No repositório GitHub, vá em **Settings → Secrets and variables → Actions → New repository secret**

Crie os seguintes secrets (copie o conteúdo de cada arquivo):

| Secret name           | Valor                                              |
|-----------------------|----------------------------------------------------|
| `GOOGLE_CLIENT_SECRET`| Conteúdo inteiro do arquivo `client_secret.json`   |
| `DRIVE_TOKEN`         | Conteúdo inteiro do arquivo `drive_token.json`     |
| `YOUTUBE_TOKEN`       | Conteúdo inteiro do arquivo `youtube_token.json`   |
| `DRIVE_FOLDER_ID`     | ID da pasta do Drive (Etapa 5)                     |
| `GROQ_API_KEY`        | Chave da API Groq (Etapa 6)                        |
| `GH_TOKEN`            | Token do GitHub (veja abaixo)                      |

### Criar o GH_TOKEN:
1. Vá em **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. Clique em **Generate new token (classic)**
3. Marque: `repo` (escopo completo)
4. Copie o token e salve como secret `GH_TOKEN`

---

## ETAPA 9 — Ativar o GitHub Actions

1. No repositório, vá em **Actions**
2. Clique em **Enable GitHub Actions**
3. Para testar imediatamente: vá em **Actions → YouTube Shorts Auto-Scheduler → Run workflow**

A partir daí, o workflow roda **automaticamente a cada hora** verificando se há novos vídeos.

---

## Como usar no dia a dia

1. Grave seu vídeo (vertical, proporção 9:16 para Shorts)
2. Coloque na pasta do Google Drive configurada
3. Pronto! Em até 1 hora a automação detecta e agenda para o próximo slot disponível (18h ou 21h)

### Ordem de agendamento
Os vídeos são agendados sequencialmente:
- 1º vídeo → próximo slot disponível (18h ou 21h de hoje/amanhã)
- 2º vídeo → slot seguinte
- E assim por diante, sem sobreposição

### Alterar os horários
Edite a linha no `main.py`:
```python
SCHEDULE_HOURS = [18, 21]   # mude para os horários que quiser
```

---

## Estrutura de arquivos

```
youtube-shorts-scheduler/
├── main.py              # Script principal de automação
├── auth.py              # Autorização local (roda uma vez)
├── requirements.txt     # Dependências Python
├── state.json           # Controle de vídeos já processados
├── .gitignore           # Exclui credenciais do git
└── .github/
    └── workflows/
        └── scheduler.yml  # Workflow do GitHub Actions
```

---

## Solução de problemas

**"Token inválido" no GitHub Actions**  
Rode `python auth.py` novamente localmente, copie os novos tokens para os secrets.

**Vídeo não aparece como Short**  
Certifique-se que o vídeo é vertical (9:16). O YouTube define como Short automaticamente para vídeos verticais de até 60 segundos.

**Quota excedida no YouTube API**  
A API gratuita tem limite de 10.000 unidades/dia. Cada upload custa ~1.600 unidades, ou seja, até ~6 uploads/dia. Para mais, solicite aumento de quota no Google Cloud Console.
