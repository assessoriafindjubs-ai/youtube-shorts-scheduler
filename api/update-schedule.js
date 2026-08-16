export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const token = (process.env.GH_TOKEN || '').replace(/^﻿/, '').trim();
  if (!token) return res.status(500).json({ error: 'GH_TOKEN nao configurado' });

  const { slots, changes } = req.body || {};
  if (!Array.isArray(slots) || slots.length === 0)
    return res.status(400).json({ error: 'slots invalido' });

  const ghHeaders = {
    'Authorization': `Bearer ${token}`,
    'Accept': 'application/vnd.github+json',
    'Content-Type': 'application/json',
  };
  const repo = 'assessoriafindjubs-ai/youtube-shorts-scheduler';
  const contentsUrl = `https://api.github.com/repos/${repo}/contents/config.json`;

  // 1. Atualiza config.json
  const getRes = await fetch(contentsUrl, { headers: ghHeaders });
  const sha = getRes.ok ? (await getRes.json()).sha : undefined;
  const content = Buffer.from(JSON.stringify({ schedule_slots: slots }, null, 2)).toString('base64');

  const putRes = await fetch(contentsUrl, {
    method: 'PUT',
    headers: ghHeaders,
    body: JSON.stringify({
      message: 'config: atualiza horarios de postagem',
      content,
      ...(sha ? { sha } : {}),
    }),
  });

  if (!putRes.ok) {
    const err = await putRes.json().catch(() => ({}));
    return res.status(putRes.status).json({ error: err.message || 'Erro ao salvar config' });
  }

  // 2. Para cada horário alterado, dispara o workflow de reagendamento
  const rescheduleErrors = [];
  if (Array.isArray(changes) && changes.length > 0) {
    for (const { old: o, new: n } of changes) {
      const dispatchRes = await fetch(
        `https://api.github.com/repos/${repo}/actions/workflows/reschedule-videos.yml/dispatches`,
        {
          method: 'POST',
          headers: ghHeaders,
          body: JSON.stringify({
            ref: 'main',
            inputs: {
              old_hour:   String(o[0]),
              old_minute: String(o[1]),
              new_hour:   String(n[0]),
              new_minute: String(n[1]),
            },
          }),
        }
      );
      if (!dispatchRes.ok) {
        const e = await dispatchRes.json().catch(() => ({}));
        rescheduleErrors.push(e.message || `Erro ao reagendar ${o[0]}:${o[1]}`);
      }
    }
  }

  if (rescheduleErrors.length > 0)
    return res.status(207).json({ ok: true, warnings: rescheduleErrors });

  return res.status(200).json({ ok: true });
}
