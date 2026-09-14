export default async function handler(req, res) {
  const isWebReq = (req instanceof Request) || (req && typeof req.headers?.get === 'function' && !res?.status);

  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-User-Id, X-User-Email',
    'Content-Type': 'application/json'
  };

  let method = req.method;
  let queryParams = {};
  let bodyData = {};

  if (isWebReq) {
    const urlObj = new URL(req.url);
    for (const [k, v] of urlObj.searchParams.entries()) {
      queryParams[k] = v;
    }
    if (method === 'POST') {
      try {
        bodyData = await req.json();
      } catch (e) {}
    }
  } else {
    queryParams = req.query || {};
    bodyData = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
  }

  function sendJson(status, data) {
    if (isWebReq) {
      return new Response(JSON.stringify(data), { status, headers: corsHeaders });
    }
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-User-Id, X-User-Email');
    return res.status(status).json(data);
  }

  if (method === 'OPTIONS') {
    if (isWebReq) return new Response(null, { status: 200, headers: corsHeaders });
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-User-Id, X-User-Email');
    return res.status(200).end();
  }

  const targetUrl = (bodyData.url || queryParams.url || '').trim();
  const userInstruction = (bodyData.instruction || queryParams.instruction || '').trim();
  const cfgOverrides = bodyData.config || {};

  if (!targetUrl) {
    return sendJson(400, { ok: false, error: 'URL parameter is required.' });
  }

  let formattedUrl = targetUrl;
  if (!formattedUrl.startsWith('http://') && !formattedUrl.startsWith('https://')) {
    formattedUrl = 'https://' + formattedUrl;
  }

  let title = 'Character';
  let pageDesc = '';
  let imageUrl = '';
  let cleanText = '';

  // 1. Wikipedia Summary API direct check
  const wikiMatch = formattedUrl.match(/wikipedia\.org\/wiki\/([^#?]+)/i);
  if (wikiMatch) {
    try {
      const pageTitle = decodeURIComponent(wikiMatch[1]);
      const wres = await fetch(`https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(pageTitle)}`, {
        headers: { 'User-Agent': 'BotSaaS/1.0 (personality-puller)' }
      });
      if (wres.ok) {
        const wdata = await wres.json();
        title = wdata.title || pageTitle.replace(/_/g, ' ');
        pageDesc = wdata.description || '';
        cleanText = wdata.extract || '';
        imageUrl = (wdata.originalimage || wdata.thumbnail || {}).source || '';
      }
    } catch (we) {}
  }

  // 2. Fetch raw HTML if not fully resolved
  if (!cleanText) {
    try {
      const response = await fetch(formattedUrl, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
      });

      if (!response.ok) {
        return sendJson(400, { ok: false, error: `Failed to fetch URL: HTTP ${response.status}` });
      }

      const html = await response.text();

      // Extract metadata
      const titleMatch = html.match(/<meta\s+property=["']og:title["']\s+content=["'](.*?)["']/i) ||
                         html.match(/<meta\s+name=["']twitter:title["']\s+content=["'](.*?)["']/i) ||
                         html.match(/<title[^>]*>(.*?)<\/title>/i);
      if (titleMatch) {
        let t = titleMatch[1].trim();
        for (const sep of [' - ', ' | ', ' – ', ' — ']) {
          if (t.includes(sep)) t = t.split(sep)[0].trim();
        }
        if (t) title = t;
      }

      const descMatch = html.match(/<meta\s+(?:name|property)=["'](?:description|og:description|twitter:description)["']\s+content=["'](.*?)["']/i);
      if (descMatch) pageDesc = descMatch[1].trim();

      const imgMatch = html.match(/<meta\s+(?:property|name)=["'](?:og:image|twitter:image)["']\s+content=["'](.*?)["']/i) ||
                       html.match(/<img[^>]+class=["'][^"']*(?:pi-image-thumbnail|infobox-image|character-image|thumbimage)[^"']*["'][^>]+src=["'](.*?)["']/i);
      if (imgMatch) {
        imageUrl = imgMatch[1].trim();
        if (imageUrl.startsWith('//')) imageUrl = 'https:' + imageUrl;
      }

      // Clean HTML to text
      let cleaned = html.replace(/<(script|style|noscript|svg|nav|footer|header|aside|form|iframe)[^>]*>[\s\S]*?<\/\1>/gi, ' ');
      cleaned = cleaned.replace(/<!--[\s\S]*?-->/g, ' ');
      cleaned = cleaned.replace(/<div[^>]*class=["'][^"']*(?:navbox|toc|mw-jump-link|mw-editsection)[^"']*["'][^>]*>[\s\S]*?<\/div>/gi, ' ');
      cleaned = cleaned.replace(/<h[1-6][^>]*>(.*?)<\/h[1-6]>/gi, '\n\n# $1\n');
      cleaned = cleaned.replace(/<p[^>]*>(.*?)<\/p>/gi, '\n$1\n');
      cleaned = cleaned.replace(/<li[^>]*>(.*?)<\/li>/gi, '\n* $1');
      cleaned = cleaned.replace(/<br\s*\/?>/gi, '\n');
      cleaned = cleaned.replace(/<[^>]+>/g, ' ');
      cleaned = cleaned.replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
      cleanText = cleaned.split('\n').map(l => l.replace(/[ \t]+/g, ' ').trim()).filter(Boolean).join('\n').slice(0, 20000);
    } catch (fe) {
      return sendJson(500, { ok: false, error: `Error fetching URL content: ${fe.message}` });
    }
  }

  // 3. AI synthesis or heuristic fallback
  const GROQ_KEY = cfgOverrides.groq_key || process.env.GROQ_KEY || '';
  const MISTRAL_KEY = cfgOverrides.mistral_key || process.env.MISTRAL_KEY || '';
  const GEMINI_KEY = cfgOverrides.gemini_key || process.env.GEMINI_KEY || process.env.GOOGLE_API_KEY || '';

  const promptContent = `Character / Subject Name: ${title}
Source URL: ${formattedUrl}
Meta Description: ${pageDesc}

Article Content:
${cleanText.slice(0, 20000)}

${userInstruction ? `Special User Instructions: ${userInstruction}` : ''}

Please analyze this character data and output a rich, accurate Character Persona Card in STRICT JSON FORMAT.
JSON format:
{
  "name": "${title}",
  "role": "Role / Archetype tag (e.g. Yandere Companion, Sorceress, Detective, Caretaker)",
  "desc": "Short 1-2 sentence description (under 140 chars)",
  "personality": "Comprehensive personality specification & system prompt for an AI roleplay bot. Detail demeanor, psychology, behavioral nuances, speaking mannerisms, speech quirks, and interaction rules.",
  "greeting": "An expressive, immersive first greeting message in character (using *actions* and spoken dialogue).",
  "scenario": "Setting / initial context",
  "example_dialogue": "Short dialogue example using <START> {{user}}: ... {{char}}: ... format",
  "tags": ["Tag1", "Tag2"],
  "avatar_url": "${imageUrl}"
}
Return ONLY valid JSON with no markdown backticks.`;

  let synthesized = null;

  // Try Mistral API
  if (MISTRAL_KEY) {
    try {
      const mres = await fetch('https://api.mistral.ai/v1/chat/completions', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${MISTRAL_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'mistral-small-latest',
          messages: [
            { role: 'system', content: 'You are an expert AI persona architect and character card creator. You convert wiki articles into rich character card JSON.' },
            { role: 'user', content: promptContent }
          ],
          temperature: 0.7,
          response_format: { type: 'json_object' }
        })
      });
      if (mres.ok) {
        const mdata = await mres.json();
        const rawJson = mdata.choices?.[0]?.message?.content;
        if (rawJson) synthesized = JSON.parse(rawJson);
      }
    } catch (me) {}
  }

  // Fallback to heuristic
  if (!synthesized || typeof synthesized !== 'object') {
    let roleGuess = 'AI Companion';
    const lower = cleanText.toLowerCase();
    if (lower.includes('yandere')) roleGuess = 'Yandere Companion';
    else if (lower.includes('tsundere')) roleGuess = 'Tsundere Companion';
    else if (lower.includes('caretaker')) roleGuess = 'Caretaker Companion';
    else if (lower.includes('detective')) roleGuess = 'Detective';

    const shortD = pageDesc ? pageDesc.slice(0, 140) : (cleanText ? cleanText.slice(0, 137) + '...' : `${title} — ${roleGuess}`);
    const greet = `*looks up and greets you calmly* Hello, I am ${title}. What would you like to talk about today?`;
    const fullPrompt = `[Character: ${title}]\n[Role: ${roleGuess}]\n[Description & Lore:\n${cleanText.slice(0, 3000)}]`;

    synthesized = {
      name: title,
      role: roleGuess,
      desc: shortD,
      personality: fullPrompt,
      greeting: greet,
      scenario: `You are interacting with ${title}.`,
      example_dialogue: `<START>\n{{user}}: Hello ${title}!\n{{char}}: ${greet}`,
      tags: [roleGuess],
      avatar_url: imageUrl
    };
  }

  if (!synthesized.avatar_url && imageUrl) {
    synthesized.avatar_url = imageUrl;
  }

  return sendJson(200, { ok: true, character: synthesized });
}
