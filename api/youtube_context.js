// YouTube Context and Transcript Fetcher Endpoint
import https from 'https';

function httpsGetJson(url, headers = {}) {
  return new Promise((resolve) => {
    try {
      const u = new URL(url);
      const req = https.get({
        hostname: u.hostname,
        path: u.pathname + u.search,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          ...headers
        },
        timeout: 10000
      }, (res) => {
        let data = '';
        res.on('data', chunk => { data += chunk; });
        res.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch(e) {
            resolve({ rawText: data });
          }
        });
      });
      req.on('error', () => resolve(null));
      req.on('timeout', () => { req.destroy(); resolve(null); });
    } catch(e) {
      resolve(null);
    }
  });
}

function extractYouTubeId(urlOrId) {
  if (!urlOrId) return '';
  const str = String(urlOrId).trim();
  if (/^[a-zA-Z0-9_-]{11}$/.test(str)) {
    return str;
  }
  let m = str.match(/youtu\.be\/([a-zA-Z0-9_-]{11})/i);
  if (m) return m[1];
  m = str.match(/[?&]v=([a-zA-Z0-9_-]{11})/i);
  if (m) return m[1];
  m = str.match(/youtube\.com\/(?:embed|shorts|v|live)\/([a-zA-Z0-9_-]{11})/i);
  if (m) return m[1];
  m = str.match(/(?:v=|\/embed\/|\/shorts\/|youtu\.be\/|\/v\/|\/e\/|watch\?v=|\&v=)([a-zA-Z0-9_-]{11})/i);
  if (m) return m[1];
  return str;
}

const _ytCache = new Map();

export default async function handler(req, res) {
  const isWebReq = (req instanceof Request) || (req && typeof req.headers?.get === 'function' && !res?.status);

  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Content-Type': 'application/json'
  };

  let method = req.method;
  let body = {};

  if (isWebReq) {
    const url = new URL(req.url);
    for (const [k, v] of url.searchParams.entries()) {
      body[k] = v;
    }
    if (method === 'POST') {
      try {
        const json = await req.json();
        body = { ...body, ...json };
      } catch (e) {}
    }
  } else {
    body = req.method === 'POST' ? (typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {})) : (req.query || {});
  }

  function sendJson(status, data) {
    if (isWebReq) {
      return new Response(JSON.stringify(data), { status, headers: corsHeaders });
    }
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    return res.status(status).json(data);
  }

  if (method === 'OPTIONS') {
    if (isWebReq) return new Response(null, { status: 200, headers: corsHeaders });
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    return res.status(200).end();
  }

  const rawUrl = (body.url || body.video_id || body.v || '').trim();
  const timestamp = parseFloat(body.timestamp || body.time || 0);

  if (!rawUrl) {
    return sendJson(400, { ok: false, error: 'No YouTube URL or ID provided' });
  }

  const videoId = extractYouTubeId(rawUrl);
  const now = Date.now();

  let cached = _ytCache.get(videoId);
  if (!cached || (now - cached.ts) > 3600000) {
    try {
      const oembedUrl = `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`;
      const oembed = await httpsGetJson(oembedUrl);

      const title = (oembed && oembed.title) ? oembed.title : 'YouTube Video';
      const author = (oembed && oembed.author_name) ? oembed.author_name : 'Creator';
      const thumb = `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;

      cached = {
        video_id: videoId,
        title: title,
        artist: author,
        thumb: thumb,
        duration: 0,
        transcript: [],
        full_transcript: '',
        ts: now
      };

      _ytCache.set(videoId, cached);
    } catch (e) {
      console.warn('YouTube context fetch notice:', e);
    }
  }

  const resultData = cached || {
    video_id: videoId,
    title: 'YouTube Video',
    artist: 'Creator',
    duration: 0,
    transcript: [],
    full_transcript: ''
  };

  let curDialogue = '';
  if (Array.isArray(resultData.transcript) && resultData.transcript.length > 0) {
    const matching = resultData.transcript.filter(t => Math.abs(timestamp - (t.start || 0)) <= 15);
    if (matching.length > 0) {
      curDialogue = matching.map(m => m.text).join(' ');
    }
  }

  return sendJson(200, {
    ok: true,
    video_id: resultData.video_id,
    title: resultData.title,
    artist: resultData.artist,
    duration: resultData.duration,
    timestamp: timestamp,
    dialogue: curDialogue,
    full_transcript: resultData.full_transcript || ''
  });
}
