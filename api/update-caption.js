export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const token = (process.env.GH_TOKEN || '').replace(/^﻿/, '').trim();
  if (!token) return res.status(500).json({ error: 'GH_TOKEN nao configurado' });

  const { videoId, newTitle } = req.body || {};
  if (!videoId || !newTitle) return res.status(400).json({ error: 'videoId e newTitle sao obrigatorios' });

  const response = await fetch(
    'https://api.github.com/repos/assessoriafindjubs-ai/youtube-shorts-scheduler/actions/workflows/update-caption.yml/dispatches',
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ref: 'main', inputs: { video_id: videoId, new_title: newTitle } }),
    }
  );

  if (response.status === 204) return res.status(200).json({ ok: true });
  const body = await response.json().catch(() => ({}));
  return res.status(response.status).json({ error: body.message || 'Erro ao disparar workflow' });
}
