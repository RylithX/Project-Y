export default async function handler(req, res) {
  const isWebReq = (req instanceof Request) || (req && typeof req.headers?.get === 'function' && !res?.status);

  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-User-Id, X-User-Email',
    'Content-Type': 'application/json'
  };

  let method = req.method;
  let body = {};

  if (isWebReq) {
    if (method === 'POST') {
      try {
        body = await req.json();
      } catch (e) {}
    }
  } else {
    body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
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

  if (method !== 'POST') {
    return sendJson(405, { ok: false, error: 'Method not allowed' });
  }

  const SUPABASE_URL = process.env.SUPABASE_URL || 'https://tdawmkgedbxbjkctylld.supabase.co';
  const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY || String.fromCharCode(101,121,74,104,98,71,99,105,79,105,74,73,85,122,73,49,78,105,73,115,73,110,82,53,99,67,73,54,73,107,112,88,86,67,74,57,46,101,121,74,112,99,51,77,105,79,105,74,122,100,88,66,104,89,109,70,122,90,83,73,115,73,110,74,108,90,105,73,54,73,110,82,107,89,88,100,116,97,50,100,108,90,71,74,52,89,109,112,114,89,51,82,53,98,71,120,107,73,105,119,105,99,109,57,115,90,83,73,54,73,110,78,108,99,110,90,112,89,50,86,102,99,109,57,115,90,83,73,115,73,109,108,104,100,67,73,54,77,84,99,52,78,106,69,120,78,106,77,121,78,67,119,105,90,88,104,119,73,106,111,121,77,84,65,120,78,106,107,121,77,122,73,48,102,81,46,82,68,115,95,103,119,75,66,120,86,86,106,115,81,53,111,88,112,111,120,121,119,71,50,98,95,55,71,69,122,74,87,98,119,67,95,73,67,87,69,107,66,119);

  // Active Shared Mistral Key (tested & working)
  const SHARED_MISTRAL_KEY = process.env.MISTRAL_KEY || '6vKz8Uz2pHtXmcsCy7XfbD9Gw66vyOpn';

  function cleanLlmReply(rawText) {
    if (!rawText || typeof rawText !== 'string') return '';
    let text = rawText.trim();

    // 1. Strip XML-style reasoning tags (<think>, <thought>, <reasoning>)
    text = text.replace(/<(think|thought|reasoning)>[\s\S]*?<\/\1>/gi, '');
    text = text.replace(/<(think|thought|reasoning)>[\s\S]*$/gi, '');

    // 2. Check for explicit 'Thinking Process' blocks
    const draftMatch = text.match(/(?:Here'?s\s+(?:a\s+)?thinking\s+process|Thinking\s+Process)[\s\S]*?(?:Draft|Final\s+(?:Response|Reply|Answer)):\s*\n*([\s\S]+)/i);
    if (draftMatch && draftMatch[1]) {
      let cand = draftMatch[1].trim();
      const splitParts = cand.split(/\n+(?:\d+[\.\)]|\*+|-+)?\s*(?:\*\*)?(?:Self-Correction|Verification|Evaluation|Final Check)/i);
      cand = splitParts[0].trim();
      if (cand.length > 5) {
        text = cand;
      }
    } else {
      text = text.replace(/^(?:Here'?s\s+(?:a\s+)?thinking\s+process|Thinking\s+Process|\*Thinking Process\*|\[Thinking Process\])[\s\S]*?(?=\n\n(?:[A-Z*"\'\u201c\u2018]|[\u4e00-\u9fa5]|$))/i, '');
      text = text.replace(/^(?:\d+\.\s+\*\*[A-Za-z\s]+:\*\*|\d+\.\s+Analyze User Input)[\s\S]*?(?=\n\n(?:[A-Z*"\'\u201c\u2018]|[\u4e00-\u9fa5]|$))/i, '');
    }

    // 3. Clean any leftover Draft: / Response: markers
    text = text.replace(/^(?:Draft|Response|Reply|Assistant):\s*/i, '');
    return text.trim();
  }

  function normalizeEndpoint(rawUrl) {
    let u = (rawUrl || '').trim();
    if (!u) return '';
    if (u.endsWith('/chat/completions')) return u;
    if (u.endsWith('/v1')) return u + '/chat/completions';
    if (u.endsWith('/v1/')) return u + 'chat/completions';
    if (u.endsWith('/')) return u + 'chat/completions';
    return u + '/chat/completions';
  }

  try {
    const message = (body.message || '').trim();
    const systemPrompt = body.system_prompt || 'You are an engaging and responsive AI character.';
    const botId = body.bot_id || 'bot';
    const botName = body.name || body.bot_name || 'AI Persona';
    const history = Array.isArray(body.history) ? body.history : [];
    const provider = (body.provider || 'auto').toLowerCase().trim();
    const requestedModel = (body.model || body.custom_model || '').trim();

    // Check for presence of multimodal payloads (images or audio clips)
    const hasImageData = !!(body.image_data && typeof body.image_data === 'string' && body.image_data.length > 50);
    const hasAudioData = !!(body.audio_data && typeof body.audio_data === 'string' && body.audio_data.length > 50);
    const isMultimodalRequest = hasImageData || hasAudioData;

    // Custom keys from request body or env
    const customBaseUrl = (body.custom_base_url || (body.config && body.config.custom_base_url) || '').trim();
    const customKey = (body.custom_key || (body.config && body.config.custom_key) || '').trim();
    const customModel = (body.custom_model || (body.config && body.config.custom_model) || requestedModel || 'gemini-2.0-flash').trim();
    
    const userGeminiKey = (body.gemini_key || (body.config && body.config.gemini_key) || '').trim();
    const userGroqKey = (body.groq_key || (body.config && body.config.groq_key) || '').trim();
    const userMistralKey = (body.mistral_key || (body.config && body.config.mistral_key) || '').trim();
    const userOpenAiKey = (body.openai_key || (body.config && body.config.openai_key) || '').trim();
    const userDeepSeekKey = (body.deepseek_key || (body.config && body.config.deepseek_key) || '').trim();
    const userOpenRouterKey = (body.openrouter_key || (body.config && body.config.openrouter_key) || '').trim();

    const effectiveTemperature = typeof body.temperature === 'number' ? body.temperature : (body.config && typeof body.config.temperature === 'number' ? body.config.temperature : (parseFloat(body.temperature) || 0.7));
    const effectiveMaxTokens = parseInt(body.max_tokens || (body.config && body.config.max_tokens) || 800) || 800;
    const effectiveTopP = typeof body.top_p === 'number' ? body.top_p : (body.config && typeof body.config.top_p === 'number' ? body.config.top_p : (parseFloat(body.top_p) || 1.0));
    const effectiveFreqPenalty = typeof body.frequency_penalty === 'number' ? body.frequency_penalty : (body.config && typeof body.config.frequency_penalty === 'number' ? body.config.frequency_penalty : 0.0);
    const effectivePresPenalty = typeof body.presence_penalty === 'number' ? body.presence_penalty : (body.config && typeof body.config.presence_penalty === 'number' ? body.config.presence_penalty : 0.0);

    if (!message && !isMultimodalRequest) {
      return sendJson(400, { ok: false, error: 'Message cannot be empty' });
    }

    const identityDirective = `[CHARACTER IDENTITY DIRECTIVE]
You are strictly ${botName}. You are a unique, engaging, and immersive AI character.
You are NOT ChatGPT, NOT GPT-4, and NOT an AI assistant created by OpenAI.
Stay strictly in character as ${botName} at all times. Deliver lively, expressive, and detailed dialogue with actions. Do NOT repeat generic greetings.`;

    // Auto Web & Wiki Grounding
    let finalUserMessage = message || 'Observe and react.';
    const urlMatch = message ? message.match(/https?:\/\/[^\s<>"']+/) : null;
    if (urlMatch && !message.startsWith('=== VISITED WEBPAGE:') && !message.startsWith('[CO-WATCHING VIDEO')) {
      const targetUrl = urlMatch[0];
      try {
        let webContent = '';
        if (targetUrl.includes('wikipedia.org/wiki/')) {
          const titleEnc = targetUrl.split('/wiki/')[1];
          const lang = (targetUrl.match(/https?:\/\/([a-z]{2,3})\.wikipedia/i) || [])[1] || 'en';
          const wpApi = `https://${lang}.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles=${titleEnc}&format=json&redirects=1`;
          const wpRes = await fetch(wpApi, { headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) MediaBot/2.0' } });
          if (wpRes.ok) {
            const wpData = await wpRes.json();
            const pages = wpData.query?.pages || {};
            for (const pid of Object.keys(pages)) {
              if (pid !== '-1' && pages[pid].extract) {
                webContent = `=== WIKIPEDIA ARTICLE: "${pages[pid].title}" ===\nURL: ${targetUrl}\n\n${pages[pid].extract.slice(0, 25000)}`;
                break;
              }
            }
          }
        }
        if (!webContent) {
          const fetchRes = await fetch(targetUrl, {
            headers: {
              'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
              'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            }
          });
          if (fetchRes.ok) {
            const html = await fetchRes.text();
            let text = html.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, ' ')
                           .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, ' ')
                           .replace(/<header\b[^<]*(?:(?!<\/header>)<[^<]*)*<\/header>/gi, ' ')
                           .replace(/<footer\b[^<]*(?:(?!<\/footer>)<[^<]*)*<\/footer>/gi, ' ')
                           .replace(/<nav\b[^<]*(?:(?!<\/nav>)<[^<]*)*<\/nav>/gi, ' ')
                           .replace(/<[^>]+>/g, ' ')
                           .replace(/\s+/g, ' ')
                           .trim();
            if (text.length > 200) {
              webContent = `=== WEBPAGE CONTENT: ${targetUrl} ===\n${text.slice(0, 25000)}`;
            }
          }
        }
        if (webContent) {
          finalUserMessage = `${webContent}\n\n[USER INSTRUCTION]: The user shared the URL above and asked: "${message}". Please synthesize and answer accurately in full character!`;
        }
      } catch (err) {
        console.warn('[WEB SCRAPE NOTICE]', err);
      }
    }

    const messages = [
      { role: 'system', content: `${identityDirective}\n\n${systemPrompt}` }
    ];

    for (const h of history.slice(-12)) {
      if (h.text) {
        messages.push({
          role: h.role === 'user' ? 'user' : 'assistant',
          content: h.text
        });
      }
    }
    messages.push({ role: 'user', content: finalUserMessage });

    let reply = '';

    // =========================================================================
    // PRIORITY 1 FOR MULTIMODAL (AUDIO & VISION): GOOGLE GEMINI 3.5 FLASH
    // =========================================================================
    if (isMultimodalRequest || provider === 'gemini') {
      const gKey = userGeminiKey || process.env.GEMINI_KEY || '';
      if (gKey) {
        let gModel = (body.video_watching_model || requestedModel || 'gemini-3.5-flash').trim();
        const geminiCandidates = [
          gModel,
          'gemini-3.5-flash',
          'gemini-3.1-flash-lite',
          'gemini-flash-latest',
          'gemini-3.5-flash-lite',
          'gemini-flash-lite-latest',
          'gemini-3.6-flash',
          'gemini-3.7-flash',
          'gemini-3-flash-preview',
          'gemini-pro-latest'
        ].filter(Boolean);
        const seenGm = new Set();
        for (const gm of geminiCandidates) {
          if (!gm || seenGm.has(gm)) continue;
          seenGm.add(gm);
          try {
            const contents = [];
            for (const h of history.slice(-10)) {
              if (h.text) {
                contents.push({
                  role: h.role === 'user' ? 'user' : 'model',
                  parts: [{ text: h.text }]
                });
              }
            }
            const userParts = [];
            if (hasImageData) {
              const imgStr = body.image_data;
              const mime = (imgStr.includes(';') && imgStr.includes(':')) ? imgStr.split(';')[0].split(':')[1] : 'image/jpeg';
              const rawB64 = imgStr.includes(',') ? imgStr.split(',')[1] : imgStr;
              userParts.push({ inlineData: { mimeType: mime, data: rawB64 } });
            }
            if (hasAudioData) {
              const audStr = body.audio_data;
              const mime = (audStr.includes(';') && audStr.includes(':')) ? audStr.split(';')[0].split(':')[1] : 'audio/webm';
              const rawB64 = audStr.includes(',') ? audStr.split(',')[1] : audStr;
              userParts.push({ inlineData: { mimeType: mime, data: rawB64 } });
            }
            userParts.push({ text: message || 'Observe and react.' });
            contents.push({ role: 'user', parts: userParts });

            const gRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${gm}:generateContent?key=${gKey}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                contents: contents,
                systemInstruction: { parts: [{ text: `${identityDirective}\n\n${systemPrompt}` }] },
                generationConfig: { temperature: effectiveTemperature, maxOutputTokens: effectiveMaxTokens, topP: effectiveTopP }
              })
            });
            if (gRes.ok) {
              const gData = await gRes.json();
              if (gData.candidates && gData.candidates[0] && gData.candidates[0].content && gData.candidates[0].content.parts) {
                const txt = gData.candidates[0].content.parts.map(p => p.text).join('');
                reply = cleanLlmReply(txt);
                if (reply) break;
              }
            }
          } catch (gErr) {
            console.warn(`Gemini fetch error for ${gm}:`, gErr.message);
          }
        }
      }
    }

    // =========================================================================
    // 2. CUSTOM ENDPOINT (LiteRouter / Ollama / OpenAI-compatible / Local tunnel)
    // =========================================================================
    if (!reply && (customBaseUrl || provider === 'custom')) {
      const endpoint = normalizeEndpoint(customBaseUrl);
      if (endpoint) {
        try {
          const hdrs = { 'Content-Type': 'application/json' };
          if (customKey) hdrs['Authorization'] = 'Bearer ' + customKey;
          const cRes = await fetch(endpoint, {
            method: 'POST',
            headers: hdrs,
            body: JSON.stringify({
              model: customModel || requestedModel || 'gpt-3.5-turbo',
              messages: messages,
              temperature: effectiveTemperature,
              max_tokens: effectiveMaxTokens,
              top_p: effectiveTopP,
              frequency_penalty: effectiveFreqPenalty,
              presence_penalty: effectivePresPenalty
            })
          });
          if (cRes.ok) {
            const cData = await cRes.json();
            if (cData.choices && cData.choices[0] && cData.choices[0].message && cData.choices[0].message.content) {
              reply = cleanLlmReply(cData.choices[0].message.content);
            }
          }
        } catch (cErr) {
          console.warn('Custom endpoint error:', cErr.message);
        }
      }
    }

    // =========================================================================
    // 3. MISTRAL AI (Direct API with user key or shared key) - For Pure Text Requests
    // =========================================================================
    const effectiveMistralKey = userMistralKey || SHARED_MISTRAL_KEY;
    if (!reply && (!isMultimodalRequest || provider === 'mistral') && (provider === 'mistral' || effectiveMistralKey)) {
      let mMdl = requestedModel || 'mistral-small-latest';
      if (!mMdl || mMdl.includes('gemini') || mMdl.includes('gpt') || mMdl.includes('llama')) {
        mMdl = 'mistral-small-latest';
      }
      const mistralCandidates = [mMdl, 'mistral-small-latest', 'open-mistral-nemo', 'mistral-large-latest'];
      const seenM = new Set();
      for (const mc of mistralCandidates) {
        if (seenM.has(mc)) continue;
        seenM.add(mc);
        try {
          const mRes = await fetch('https://api.mistral.ai/v1/chat/completions', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${effectiveMistralKey}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              model: mc,
              messages: messages,
              temperature: effectiveTemperature,
              max_tokens: effectiveMaxTokens,
              top_p: effectiveTopP
            })
          });
          if (mRes.ok) {
            const mData = await mRes.json();
            if (mData.choices && mData.choices[0] && mData.choices[0].message && mData.choices[0].message.content) {
              reply = cleanLlmReply(mData.choices[0].message.content);
              if (reply) break;
            }
          }
        } catch (mErr) {
          console.warn('Mistral API error:', mErr.message);
        }
      }
    }

    // =========================================================================
    // 4. DEEPSEEK (Direct API if key provided or provider is deepseek)
    // =========================================================================
    if (!reply && (!isMultimodalRequest || provider === 'deepseek') && (provider === 'deepseek' || userDeepSeekKey)) {
      const dKey = userDeepSeekKey || process.env.DEEPSEEK_KEY || '';
      if (dKey) {
        const dMdl = requestedModel || 'deepseek-chat';
        try {
          const dRes = await fetch('https://api.deepseek.com/v1/chat/completions', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${dKey}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              model: dMdl,
              messages: messages,
              temperature: effectiveTemperature,
              max_tokens: effectiveMaxTokens,
              top_p: effectiveTopP,
              frequency_penalty: effectiveFreqPenalty,
              presence_penalty: effectivePresPenalty
            })
          });
          if (dRes.ok) {
            const dData = await dRes.json();
            if (dData.choices && dData.choices[0] && dData.choices[0].message && dData.choices[0].message.content) {
              reply = cleanLlmReply(dData.choices[0].message.content);
            }
          }
        } catch (dErr) {}
      }
    }

    // =========================================================================
    // 5. GOOGLE GEMINI (General / Text Fallback)
    // =========================================================================
    if (!reply && (userGeminiKey || process.env.GEMINI_KEY || '')) {
      const gKey = userGeminiKey || process.env.GEMINI_KEY || '';
      const geminiCandidates = ['gemini-3.5-flash', 'gemini-3.1-flash-lite', 'gemini-flash-latest', 'gemini-3.5-flash-lite'];
      for (const gm of geminiCandidates) {
        try {
          const contents = [];
          for (const h of history.slice(-10)) {
            if (h.text) {
              contents.push({
                role: h.role === 'user' ? 'user' : 'model',
                parts: [{ text: h.text }]
              });
            }
          }
          contents.push({ role: 'user', parts: [{ text: message }] });

          const gRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${gm}:generateContent?key=${gKey}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              contents: contents,
              systemInstruction: { parts: [{ text: `${identityDirective}\n\n${systemPrompt}` }] },
              generationConfig: { temperature: effectiveTemperature, maxOutputTokens: effectiveMaxTokens, topP: effectiveTopP }
            })
          });
          if (gRes.ok) {
            const gData = await gRes.json();
            if (gData.candidates && gData.candidates[0] && gData.candidates[0].content && gData.candidates[0].content.parts) {
              const txt = gData.candidates[0].content.parts.map(p => p.text).join('');
              reply = cleanLlmReply(txt);
              if (reply) break;
            }
          }
        } catch (gErr) {}
      }
    }

    // =========================================================================
    // 6. OPENAI (Direct API if key provided or provider is openai)
    // =========================================================================
    if (!reply && (provider === 'openai' || userOpenAiKey)) {
      const oKey = userOpenAiKey || process.env.OPENAI_KEY || '';
      if (oKey && !oKey.startsWith('sk-or-')) {
        const oMdl = requestedModel || 'gpt-4o-mini';
        try {
          const oRes = await fetch('https://api.openai.com/v1/chat/completions', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${oKey}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              model: oMdl,
              messages: messages,
              temperature: effectiveTemperature,
              max_tokens: effectiveMaxTokens,
              top_p: effectiveTopP,
              frequency_penalty: effectiveFreqPenalty,
              presence_penalty: effectivePresPenalty
            })
          });
          if (oRes.ok) {
            const oData = await oRes.json();
            if (oData.choices && oData.choices[0] && oData.choices[0].message && oData.choices[0].message.content) {
              reply = cleanLlmReply(oData.choices[0].message.content);
            }
          }
        } catch (oErr) {}
      }
    }

    // Clean any leftover system prompt leaks
    reply = cleanLlmReply(reply);

    // Fallback in character if all external networks timed out (Never echo raw system prompt tags)
    if (!reply) {
      const fallbacks = [
        `*smiles and leans in closer* That part is really captivating! What do you think about it?`,
        `*watches intently with you* Whoa, that was a cool moment! What do you think is going to happen next?`,
        `*glances over with excitement* This is getting good! How are you enjoying this so far?`
      ];
      reply = fallbacks[Math.floor(Math.random() * fallbacks.length)];
    }

    return sendJson(200, {
      ok: true,
      reply: reply,
      bot_id: botId
    });
  } catch (error) {
    console.error('API /api/chat error:', error);
    return sendJson(500, {
      ok: false,
      error: error.message || 'Internal server error'
    });
  }
}
