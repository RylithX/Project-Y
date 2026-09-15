/**
 * Studio Suite — Android Kotlin Native Bridge
 * Seamless integration between Bot SaaS Studio and Android OS features
 */
(function() {
  if (typeof window === 'undefined') return;

  console.log('[StudioNative] Android Kotlin Bridge Initializing...');

  // Hook into native speech recognition
  window.addEventListener('native_speech_result', function(e) {
    const text = e.detail;
    if (!text) return;
    
    // Find chat input
    const chatInput = document.getElementById('chatInput') || 
                      document.querySelector('textarea.chat-input') ||
                      document.querySelector('textarea[placeholder*="message" i]');
    if (chatInput) {
      const prev = chatInput.value ? chatInput.value.trim() + ' ' : '';
      chatInput.value = prev + text;
      chatInput.dispatchEvent(new Event('input', { bubbles: true }));
      chatInput.focus();
    }
  });

  // Polyfill or override Web Speech API / Mic button if on Android
  window.triggerNativeVoiceInput = function() {
    if (window.AndroidBridge && typeof window.AndroidBridge.startSpeechRecognition === 'function') {
      window.AndroidBridge.startSpeechRecognition();
      return true;
    }
    return false;
  };

  // Provide direct helper for native Android TTS
  window.speakWithAndroidTTS = function(text, pitch, rate) {
    if (window.AndroidBridge && typeof window.AndroidBridge.speakText === 'function') {
      window.AndroidBridge.speakText(text, '', pitch || 1.0, rate || 1.0);
      return true;
    }
    return false;
  };

  // Save Doodle directly to Android Gallery
  window.saveDoodleToGallery = function(canvasId, filename) {
    const canvas = document.getElementById(canvasId || 'doodleCanvas');
    if (!canvas) return;
    const dataUrl = canvas.toDataURL('image/png');
    if (window.AndroidBridge && typeof window.AndroidBridge.saveDoodle === 'function') {
      window.AndroidBridge.saveDoodle(dataUrl, filename || 'doodle_' + Date.now() + '.png');
    } else {
      // Fallback standard browser download
      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = filename || 'doodle.png';
      a.click();
    }
  };

  // Export bot card directly to Android Downloads
  window.exportBotCardToDownloads = function(botData, filename) {
    const jsonStr = typeof botData === 'string' ? botData : JSON.stringify(botData, null, 2);
    const safeName = (filename || 'bot_export') + '.json';
    if (window.AndroidBridge && typeof window.AndroidBridge.exportBotCard === 'function') {
      window.AndroidBridge.exportBotCard(jsonStr, safeName);
    } else {
      const blob = new Blob([jsonStr], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = safeName;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  // Haptic feedback helper
  window.haptic = function(type) {
    if (window.AndroidBridge && typeof window.AndroidBridge.vibrate === 'function') {
      window.AndroidBridge.vibrate(type || 'tick', 15);
    }
  };

  // Auto-wire existing mic buttons when DOM is loaded
  document.addEventListener('DOMContentLoaded', function() {
    console.log('[StudioNative] Attaching Android Native handlers');

    // Voice input mic button (if explicitly added for chat input)
    const micBtn = document.getElementById('chatMicBtn');
    if (micBtn && window.AndroidBridge) {
      micBtn.addEventListener('click', function(e) {
        if (window.triggerNativeVoiceInput()) {
          e.preventDefault();
          e.stopPropagation();
        }
      }, true);
    }

    // Add Android App badge to sidebar bottom if present
    const sidebarBottom = document.querySelector('.sidebar-bottom-group');
    if (sidebarBottom && window.AndroidBridge) {
      const androidBtn = document.createElement('div');
      androidBtn.className = 'sidebar-icon-btn';
      androidBtn.title = 'Android App Settings';
      androidBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M6 18c0 .55.45 1 1 1h1v3.5c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5V19h2v3.5c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5V19h1c.55 0 1-.45 1-1V8H6v10zM3.5 8C2.67 8 2 8.67 2 9.5v7c0 .83.67 1.5 1.5 1.5S5 17.33 5 16.5v-7C5 8.67 4.33 8 3.5 8zm17 0c-.83 0-1.5.67-1.5 1.5v7c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5v-7c0-.83-.67-1.5-1.5-1.5zm-4.97-4.84l1.3-1.3c.2-.2.2-.51 0-.71-.2-.2-.51-.2-.71 0l-1.48 1.48C13.85 2.23 12.95 2 12 2c-.96 0-1.86.23-2.66.63L7.85.15c-.2-.2-.51-.2-.71 0-.2.2-.2.51 0 .71l1.31 1.31C6.73 3.39 5.5 5.51 5.5 8h13c0-2.49-1.23-4.61-2.97-5.84zM10 5H9V4h1v1zm5 0h-1V4h1v1z"/>
        </svg>
      `;
      androidBtn.onclick = function() {
        if (window.AndroidBridge && window.AndroidBridge.openServerSettings) {
          window.AndroidBridge.openServerSettings();
        }
      };
      sidebarBottom.prepend(androidBtn);
    }
  });

  console.log('[StudioNative] Android Kotlin Bridge Ready');
})();
