package com.discord.studio

import org.json.JSONObject

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import android.view.View
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.util.Locale

class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener {

    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var customViewContainer: FrameLayout
    private lateinit var errorContainer: View
    private lateinit var btnRetry: Button
    private lateinit var btnLoadBundled: Button

    lateinit var config: StudioConfig
        private set
    private lateinit var bridge: StudioBridge
    private lateinit var chromeClient: StudioWebChromeClient
    private lateinit var webViewClient: StudioWebViewClient

    private var textToSpeech: TextToSpeech? = null
    private var isTtsReady = false

    private var speechRecognizer: SpeechRecognizer? = null
    private var isListening = false

    private var filePathCallback: ValueCallback<Array<Uri>>? = null
    private lateinit var fileChooserLauncher: ActivityResultLauncher<Intent>
    private lateinit var permissionsLauncher: ActivityResultLauncher<Array<String>>

    private var doubleBackToExitPressedOnce = false
    private val exitResetHandler = Handler(Looper.getMainLooper())

    companion object {
        private const val TAG = "StudioMainActivity"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Immersive edge-to-edge window styling
        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.statusBarColor = ContextCompat.getColor(this, R.color.studio_bg)
        window.navigationBarColor = ContextCompat.getColor(this, R.color.studio_bg)
        val insetsController = WindowInsetsControllerCompat(window, window.decorView)
        insetsController.isAppearanceLightStatusBars = false
        insetsController.isAppearanceLightNavigationBars = false

        setContentView(R.layout.activity_main)

        config = StudioConfig(this)
        bridge = StudioBridge(this, config)

        initViews()
        initLaunchers()
        initTtsAndStt()
        setupWebView()
        setupBackNavigation()
        requestEssentialPermissions()

        loadStudioPage()
    }

    private fun initViews() {
        webView = findViewById(R.id.studioWebView)
        progressBar = findViewById(R.id.studioProgressBar)
        customViewContainer = findViewById(R.id.customViewContainer)
        errorContainer = findViewById(R.id.errorContainer)
        btnRetry = findViewById(R.id.btnRetry)
        btnLoadBundled = findViewById(R.id.btnLoadBundled)

        btnRetry.setOnClickListener {
            loadStudioPage()
        }

        btnLoadBundled.setOnClickListener {
            config.serverMode = StudioConfig.MODE_BUNDLED
            loadStudioPage()
        }
    }

    private fun initLaunchers() {
        fileChooserLauncher = registerForActivityResult(
            ActivityResultContracts.StartActivityForResult()
        ) { result ->
            if (result.resultCode == Activity.RESULT_OK) {
                val data = result.data
                val results: Array<Uri>? = when {
                    data?.clipData != null -> {
                        val count = data.clipData!!.itemCount
                        Array(count) { i -> data.clipData!!.getItemAt(i).uri }
                    }
                    data?.data != null -> arrayOf(data.data!!)
                    else -> null
                }
                filePathCallback?.onReceiveValue(results)
            } else {
                filePathCallback?.onReceiveValue(null)
            }
            filePathCallback = null
        }

        permissionsLauncher = registerForActivityResult(
            ActivityResultContracts.RequestMultiplePermissions()
        ) { permissions ->
            val audioGranted = permissions[Manifest.permission.RECORD_AUDIO] == true
            if (audioGranted) {
                Log.d(TAG, "RECORD_AUDIO permission granted")
            }
        }
    }

    private fun requestEssentialPermissions() {
        val permissions = mutableListOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.MODIFY_AUDIO_SETTINGS
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.READ_MEDIA_IMAGES)
            permissions.add(Manifest.permission.READ_MEDIA_AUDIO)
        } else {
            permissions.add(Manifest.permission.READ_EXTERNAL_STORAGE)
        }

        val needed = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (needed.isNotEmpty()) {
            permissionsLauncher.launch(needed.toTypedArray())
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val settings: WebSettings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.mediaPlaybackRequiresUserGesture = false
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.allowFileAccessFromFileURLs = true
        settings.allowUniversalAccessFromFileURLs = true
        settings.loadWithOverviewMode = true
        settings.useWideViewPort = true
        settings.setSupportZoom(false)
        settings.cacheMode = WebSettings.LOAD_DEFAULT

        // High performance hardware acceleration
        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null)

        // Custom clients
        chromeClient = StudioWebChromeClient(this, progressBar, customViewContainer)
        webViewClient = StudioWebViewClient(this, errorContainer)
        webView.webChromeClient = chromeClient
        webView.webViewClient = webViewClient

        // Register Native JavaScript Bridge
        webView.addJavascriptInterface(bridge, "AndroidBridge")
    }

    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                // If in fullscreen custom view, exit fullscreen first
                if (customViewContainer.visibility == View.VISIBLE) {
                    chromeClient.onHideCustomView()
                    return
                }

                // If WebView can go back in its internal history
                if (webView.canGoBack()) {
                    webView.goBack()
                    return
                }

                // Double press to exit
                if (doubleBackToExitPressedOnce) {
                    finish()
                    return
                }

                doubleBackToExitPressedOnce = true
                Toast.makeText(this@MainActivity, getString(R.string.exit_confirm), Toast.LENGTH_SHORT).show()
                exitResetHandler.postDelayed({ doubleBackToExitPressedOnce = false }, 2000)
            }
        })
    }

    fun loadStudioPage() {
        val targetUrl = config.getActiveUrl()
        Log.d(TAG, "Loading Studio Suite from: $targetUrl")
        webView.loadUrl(targetUrl)
    }

    fun handleFileChooser(
        callback: ValueCallback<Array<Uri>>?,
        params: WebChromeClient.FileChooserParams?
    ): Boolean {
        filePathCallback?.onReceiveValue(null)
        filePathCallback = callback

        val intent = try {
            params?.createIntent() ?: Intent(Intent.ACTION_GET_CONTENT).apply {
                type = "*/*"
                addCategory(Intent.CATEGORY_OPENABLE)
            }
        } catch (e: Exception) {
            Intent(Intent.ACTION_GET_CONTENT).apply {
                type = "*/*"
                addCategory(Intent.CATEGORY_OPENABLE)
            }
        }

        try {
            fileChooserLauncher.launch(intent)
            return true
        } catch (e: Exception) {
            Log.e(TAG, "Cannot launch file chooser: ${e.message}")
            filePathCallback = null
            return false
        }
    }

    fun setFullscreenMode(enabled: Boolean) {
        val insetsController = WindowInsetsControllerCompat(window, window.decorView)
        if (enabled) {
            insetsController.hide(WindowInsetsCompat.Type.systemBars())
            insetsController.systemBarsBehavior =
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            webView.visibility = View.GONE
        } else {
            insetsController.show(WindowInsetsCompat.Type.systemBars())
            webView.visibility = View.VISIBLE
        }
    }

    // --- Native TTS & STT Implementation ---

    private fun initTtsAndStt() {
        textToSpeech = TextToSpeech(this, this)

        if (SpeechRecognizer.isRecognitionAvailable(this)) {
            speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
                setRecognitionListener(object : RecognitionListener {
                    override fun onReadyForSpeech(params: Bundle?) {
                        bridge.vibrate("tick", 15)
                    }
                    override fun onBeginningOfSpeech() {}
                    override fun onRmsChanged(rmsdB: Float) {}
                    override fun onBufferReceived(buffer: ByteArray?) {}
                    override fun onEndOfSpeech() {
                        isListening = false
                    }
                    override fun onError(error: Int) {
                        isListening = false
                        Log.w(TAG, "Speech recognition error code: $error")
                    }
                    override fun onResults(results: Bundle?) {
                        isListening = false
                        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        val text = matches?.firstOrNull() ?: return
                        dispatchSpeechResult(text)
                    }
                    override fun onPartialResults(partialResults: Bundle?) {
                        val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        val text = matches?.firstOrNull() ?: return
                        dispatchPartialSpeechResult(text)
                    }
                    override fun onEvent(eventType: Int, params: Bundle?) {}
                })
            }
        }
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            textToSpeech?.language = Locale.US
            textToSpeech?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {
                    runOnUiThread {
                        webView.evaluateJavascript("if (window.setVrmAnimState) window.setVrmAnimState('SPEAKING');", null)
                    }
                }
                override fun onDone(utteranceId: String?) {
                    runOnUiThread {
                        webView.evaluateJavascript("if (window.setVrmAnimState) window.setVrmAnimState('IDLE');", null)
                    }
                }
                override fun onError(utteranceId: String?) {
                    runOnUiThread {
                        webView.evaluateJavascript("if (window.setVrmAnimState) window.setVrmAnimState('IDLE');", null)
                    }
                }
            })
            isTtsReady = true
        }
    }

    fun speakText(text: String, voiceName: String, pitch: Float, rate: Float) {
        if (!isTtsReady || textToSpeech == null) return
        textToSpeech?.setPitch(if (pitch > 0) pitch else 1.0f)
        textToSpeech?.setSpeechRate(if (rate > 0) rate else 1.0f)
        textToSpeech?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "StudioUtterance_" + System.currentTimeMillis())
    }

    fun stopSpeech() {
        textToSpeech?.stop()
        webView.evaluateJavascript("if (window.setVrmAnimState) window.setVrmAnimState('IDLE');", null)
    }

    fun startSpeechRecognition() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            permissionsLauncher.launch(arrayOf(Manifest.permission.RECORD_AUDIO))
            return
        }

        if (speechRecognizer == null) {
            Toast.makeText(this, "Speech recognition is not available on this device", Toast.LENGTH_SHORT).show()
            return
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault())
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }

        isListening = true
        speechRecognizer?.startListening(intent)
        bridge.showToast("Listening...")
    }

    fun stopSpeechRecognition() {
        if (isListening) {
            speechRecognizer?.stopListening()
            isListening = false
        }
    }

    private fun dispatchSpeechResult(text: String) {
        val safeText = JSONObject.quote(text)
        val js = "window.dispatchEvent(new CustomEvent('native_speech_result', { detail: $safeText }));"
        webView.evaluateJavascript(js, null)
    }

    private fun dispatchPartialSpeechResult(text: String) {
        val safeText = JSONObject.quote(text)
        val js = "window.dispatchEvent(new CustomEvent('native_speech_partial', { detail: $safeText }));"
        webView.evaluateJavascript(js, null)
    }

    fun showServerSettingsDialog() {
        val modes = arrayOf("Bundled Offline Studio", "Local Bot Server (127.0.0.1:5000)", "Custom Server URL")
        val currentSelection = when (config.serverMode) {
            StudioConfig.MODE_LOCAL -> 1
            StudioConfig.MODE_CUSTOM -> 2
            else -> 0
        }

        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.server_settings)
            .setSingleChoiceItems(modes, currentSelection) { dialog, which ->
                when (which) {
                    0 -> {
                        config.serverMode = StudioConfig.MODE_BUNDLED
                        loadStudioPage()
                        dialog.dismiss()
                    }
                    1 -> {
                        config.serverMode = StudioConfig.MODE_LOCAL
                        loadStudioPage()
                        dialog.dismiss()
                    }
                    2 -> {
                        dialog.dismiss()
                        showCustomUrlDialog()
                    }
                }
            }
            .setNegativeButton(R.string.btn_cancel, null)
            .show()
    }

    private fun showCustomUrlDialog() {
        val input = EditText(this).apply {
            hint = "http://192.168.1.100:5000"
            setText(config.customUrl)
            setSelection(text.length)
        }

        MaterialAlertDialogBuilder(this)
            .setTitle("Enter Custom Server URL")
            .setView(input)
            .setPositiveButton(R.string.btn_save) { _, _ ->
                val url = input.text.toString().trim()
                if (url.isNotEmpty()) {
                    config.serverMode = StudioConfig.MODE_CUSTOM
                    config.customUrl = url
                    loadStudioPage()
                }
            }
            .setNegativeButton(R.string.btn_cancel, null)
            .show()
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
    }

    override fun onPause() {
        super.onPause()
        webView.onPause()
        stopSpeech()
    }

    override fun onDestroy() {
        super.onDestroy()
        stopSpeech()
        textToSpeech?.shutdown()
        speechRecognizer?.destroy()
        webView.destroy()
    }
}
