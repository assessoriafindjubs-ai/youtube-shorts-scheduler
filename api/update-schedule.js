export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const token = (process.env.GH_TOKEN || '').replace(/^﻿/, '').trim();
  if (!token) return res.status(500).json({ error: 'GH_TOKEN nao configurado' });

  const { slots } = req.body || {};
  if (!Array.isArray(slots) || slots.length === 0)
    return res.status(400).json({ error: 'slots invalido' });

  const headers = {
    'Authorization': `Bearer ${token}`,
    'Accept': 'application/vnd.github+json',
    'Content-Type': 'application/json',
  };
  const contentsUrl = 'https://api.github.com/repos/assessoriafindjubs-ai/youtube-shorts-scheduler/contents/config.json';

  // Busca SHA atual do arquivo (necessário para update)
  const getRes = await fetch(contentsUrl, { headers });
  const sha = getRes.ok ? (await getRes.json()).sha : undefined;

  const body = JSON.stringify({ schedule_slots: slots }, null, 2);
  const content = Buffer.from(body).toString('base64');

  const putRes = await fetch(contentsUrl, {
    method: 'PUT',
    headers,
    body: JSON.stringify({
      message: 'config: atualiza horarios de postagem',
      content,
      ...(sha ? { sha } : {}),
    }),
  });

  if (putRes.ok) return res.status(200).json({ ok: true });
  const err = await putRes.json().catch(() => ({}));
  return res.status(putRes.status).json({ error: err.message || 'Erro ao salvar' });
}
