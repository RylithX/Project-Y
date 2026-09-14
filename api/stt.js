// Serverless STT Endpoint (Groq Whisper / OpenAI Whisper)
const https = require('https');

exports.handler = async (event, context) => {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Methods': 'POST, OPTIONS'
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ ok: false, error: 'Method Not Allowed' }) };
  }

  try {
    let body = {};
    try {
      body = JSON.parse(event.body || '{}');
    } catch (e) {}

    let audioBase64 = body.audio || body.audio_data || body.file || '';
    if (audioBase64.includes(',')) {
      audioBase64 = audioBase64.split(',')[1];
    }

    if (!audioBase64) {
      return { statusCode: 400, headers, body: JSON.stringify({ ok: false, error: 'No audio data provided' }) };
    }

    const SHARED_GROQ_KEY = process.env.GROQ_KEY || '';
    const groqKey = body.groq_key || SHARED_GROQ_KEY;
    if (!groqKey) {
      return { statusCode: 400, headers, body: JSON.stringify({ ok: false, error: 'Groq API key not configured for STT' }) };
    }

    const audioBuffer = Buffer.from(audioBase64, 'base64');
    const boundary = '----WhisperFormBoundary' + Math.random().toString(36).substring(2);

    let formHeader = `--${boundary}\r\n`;
    formHeader += `Content-Disposition: form-data; name="file"; filename="audio.webm"\r\n`;
    formHeader += `Content-Type: audio/webm\r\n\r\n`;

    let formModel = `\r\n--${boundary}\r\n`;
    formModel += `Content-Disposition: form-data; name="model"\r\n\r\n`;
    formModel += `whisper-large-v3\r\n`;
    formModel += `--${boundary}--\r\n`;

    const payload = Buffer.concat([
      Buffer.from(formHeader, 'utf8'),
      audioBuffer,
      Buffer.from(formModel, 'utf8')
    ]);

    return new Promise((resolve) => {
      const req = https.request({
        hostname: 'api.groq.com',
        path: '/openai/v1/audio/transcriptions',
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${groqKey}`,
          'Content-Type': `multipart/form-data; boundary=${boundary}`,
          'Content-Length': payload.length
        }
      }, (res) => {
        let data = '';
        res.on('data', chunk => { data += chunk; });
        res.on('end', () => {
          try {
            const parsed = JSON.parse(data);
            if (res.statusCode >= 200 && res.statusCode < 300 && parsed.text) {
              resolve({
                statusCode: 200,
                headers,
                body: JSON.stringify({ ok: true, text: parsed.text.trim() })
              });
            } else {
              resolve({
                statusCode: 500,
                headers,
                body: JSON.stringify({ ok: false, error: parsed.error ? parsed.error.message : 'Transcription failed' })
              });
            }
          } catch (err) {
            resolve({ statusCode: 500, headers, body: JSON.stringify({ ok: false, error: data }) });
          }
        });
      });

      req.on('error', (err) => {
        resolve({ statusCode: 500, headers, body: JSON.stringify({ ok: false, error: err.message }) });
      });

      req.write(payload);
      req.end();
    });
  } catch (err) {
    return { statusCode: 500, headers, body: JSON.stringify({ ok: false, error: err.message }) };
  }
};
