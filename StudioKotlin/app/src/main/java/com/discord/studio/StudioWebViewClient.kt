package com.discord.studio

import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.util.Log
import android.view.View
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.webkit.WebViewAssetLoader

class StudioWebViewClient(
    private val activity: MainActivity,
    private val errorContainer: View
) : WebViewClient() {

    companion object {
        private const val TAG = "StudioWebViewClient"
    }

    private val assetLoader: WebViewAssetLoader = WebViewAssetLoader.Builder()
        .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(activity))
        .build()

    override fun shouldInterceptRequest(
        view: WebView?,
        request: WebResourceRequest?
    ): WebResourceResponse? {
        val url = request?.url ?: return null
        // Route assets cleanly through WebViewAssetLoader (bypasses CORS restrictions for local assets)
        val response = assetLoader.shouldInterceptRequest(url)
        if (response != null) return response

        return super.shouldInterceptRequest(view, request)
    }

    override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
        val uri = request?.url ?: return false
        val scheme = uri.scheme?.lowercase() ?: ""
        val host = uri.host?.lowercase() ?: ""

        // Keep local app assets and local server in-app
        if (host == "appassets.androidplatform.net" ||
            host == "127.0.0.1" ||
            host == "localhost" ||
            scheme == "file"
        ) {
            return false
        }

        // Keep Pokémon Showdown theater embedded if desired
        if (host.contains("pokemonshowdown.com")) {
            return false
        }

        // Open external domains in system browser
        return try {
            val intent = Intent(Intent.ACTION_VIEW, uri)
            activity.startActivity(intent)
            true
        } catch (e: Exception) {
            Log.w(TAG, "Failed to launch external browser for $uri: ${e.message}")
            false
        }
    }

    override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
        super.onPageStarted(view, url, favicon)
        errorContainer.visibility = View.GONE
    }

    override fun onPageFinished(view: WebView?, url: String?) {
        super.onPageFinished(view, url)
        errorContainer.visibility = View.GONE

        // Inject Native Android Bridge helpers into the web application
        val bridgeJs = """
            (function() {
                if (window.__STUDIO_NATIVE_INITIALIZED__) return;
                window.__STUDIO_NATIVE_INITIALIZED__ = true;
                console.log("[StudioNative] Kotlin Android Bridge Active");

                // Provide direct hook for native TTS
                window.speakViaAndroid = function(text, voice, pitch, rate) {
                    if (window.AndroidBridge && window.AndroidBridge.speakText) {
                        window.AndroidBridge.speakText(text, voice || '', pitch || 1.0, rate || 1.0);
                        return true;
                    }
                    return false;
                };

                // Provide direct hook for native STT
                window.listenViaAndroid = function() {
                    if (window.AndroidBridge && window.AndroidBridge.startSpeechRecognition) {
                        window.AndroidBridge.startSpeechRecognition();
                        return true;
                    }
                    return false;
                };

                // Wire up speech recognition result listener
                window.addEventListener('native_speech_result', function(e) {
                    const text = e.detail;
                    const input = document.getElementById('chatInput') || document.querySelector('textarea.chat-input');
                    if (input && text) {
                        input.value = (input.value ? input.value + ' ' : '') + text;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                });

                // Attach subtle haptic ticks to clickable items
                document.addEventListener('click', function(e) {
                    const target = e.target.closest('button, .sidebar-item, .chat-send-btn, .action-btn, .tab-btn');
                    if (target && window.AndroidBridge && window.AndroidBridge.vibrate) {
                        window.AndroidBridge.vibrate('tick', 15);
                    }
                }, true);
            })();
        """.trimIndent()

        view?.evaluateJavascript(bridgeJs, null)
    }

    override fun onReceivedError(
        view: WebView?,
        request: WebResourceRequest?,
        error: WebResourceError?
    ) {
        super.onReceivedError(view, request, error)
        if (request?.isForMainFrame == true) {
            Log.e(TAG, "Main frame failed to load: ${error?.description}")
            errorContainer.visibility = View.VISIBLE
        }
    }
}
