export default async function handler(req, res) {
  // Check if Web Standard Request (Netlify v2)
  const isWebReq = (req instanceof Request) || (req && typeof req.headers?.get === 'function' && !res?.status);

  let method = req.method;
  let queryToken = '';
  let bodyToken = '';

  if (isWebReq) {
    const url = new URL(req.url);
    queryToken = url.searchParams.get('token') || '';
    if (method === 'POST') {
      try {
        const b = await req.json();
        bodyToken = b.token || '';
      } catch (e) {}
    }
  } else {
    queryToken = req.query?.token || '';
    bodyToken = req.body?.token || '';
  }

  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Content-Type': 'application/json'
  };

  if (method === 'OPTIONS') {
    if (isWebReq) return new Response(null, { status: 200, headers: corsHeaders });
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    return res.status(200).end();
  }

  function sendJson(status, data) {
    if (isWebReq) {
      return new Response(JSON.stringify(data), { status, headers: corsHeaders });
    }
    res.setHeader('Access-Control-Allow-Origin', '*');
    return res.status(status).json(data);
  }

  const token = (queryToken || bodyToken || '').trim();
  if (!token) {
    return sendJson(400, { ok: false, error: 'Missing token' });
  }

  try {
    const dRes = await fetch('https://discord.com/api/v10/users/@me', {
      headers: { 'Authorization': 'Bot ' + token }
    });

    if (!dRes.ok) {
      const errText = await dRes.text();
      return sendJson(dRes.status, { ok: false, error: 'Discord API error: ' + errText });
    }

    const d = await dRes.json();
    let avatarUrl = null;
    if (d.avatar && d.id) {
      avatarUrl = `https://cdn.discordapp.com/avatars/${d.id}/${d.avatar}.png?size=1024`;
    } else if (d.id) {
      try {
        const disc = (BigInt(d.id) >> 22n) % 6n;
        avatarUrl = `https://cdn.discordapp.com/embed/avatars/${disc}.png`;
      } catch (e) {
        avatarUrl = 'https://cdn.discordapp.com/embed/avatars/0.png';
      }
    }

    return sendJson(200, {
      ok: true,
      id: d.id,
      username: d.username,
      discriminator: d.discriminator,
      avatar: d.avatar,
      avatar_url: avatarUrl,
      bot: d.bot
    });
  } catch (err) {
    return sendJson(500, { ok: false, error: err.message || 'Internal server error' });
  }
}
