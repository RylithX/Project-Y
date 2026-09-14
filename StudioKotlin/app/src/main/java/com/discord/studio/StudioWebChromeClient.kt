package com.discord.studio

import android.content.DialogInterface
import android.net.Uri
import android.util.Log
import android.view.View
import android.webkit.ConsoleMessage
import android.webkit.JsPromptResult
import android.webkit.JsResult
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ProgressBar
import androidx.appcompat.app.AlertDialog
import com.google.android.material.dialog.MaterialAlertDialogBuilder

class StudioWebChromeClient(
    private val activity: MainActivity,
    private val progressBar: ProgressBar,
    private val customViewContainer: FrameLayout
) : WebChromeClient() {

    private var customView: View? = null
    private var customViewCallback: CustomViewCallback? = null

    companion object {
        private const val TAG = "StudioWebChrome"
    }

    override fun onProgressChanged(view: WebView?, newProgress: Int) {
        super.onProgressChanged(view, newProgress)
        if (newProgress < 100) {
            progressBar.visibility = View.VISIBLE
            progressBar.progress = newProgress
        } else {
            progressBar.visibility = View.GONE
        }
    }

    override fun onConsoleMessage(consoleMessage: ConsoleMessage?): Boolean {
        consoleMessage?.let {
            val logMessage = "[${it.messageLevel()}] ${it.message()} -- From line ${it.lineNumber()} of ${it.sourceId()}"
            when (it.messageLevel()) {
                ConsoleMessage.MessageLevel.ERROR -> Log.e(TAG, logMessage)
                ConsoleMessage.MessageLevel.WARNING -> Log.w(TAG, logMessage)
                else -> Log.d(TAG, logMessage)
            }
        }
        return true
    }

    override fun onPermissionRequest(request: PermissionRequest?) {
        if (request == null) return
        activity.runOnUiThread {
            // Check for Audio Capture & Video Capture for WebRTC and Microphone
            val requestedResources = request.resources
            val granted = mutableListOf<String>()
            for (resource in requestedResources) {
                if (resource == PermissionRequest.RESOURCE_AUDIO_CAPTURE ||
                    resource == PermissionRequest.RESOURCE_VIDEO_CAPTURE
                ) {
                    granted.add(resource)
                }
            }
            if (granted.isNotEmpty()) {
                request.grant(granted.toTypedArray())
            } else {
                request.deny()
            }
        }
    }

    override fun onShowFileChooser(
        webView: WebView?,
        filePathCallback: ValueCallback<Array<Uri>>?,
        fileChooserParams: FileChooserParams?
    ): Boolean {
        return activity.handleFileChooser(filePathCallback, fileChooserParams)
    }

    override fun onShowCustomView(view: View?, callback: CustomViewCallback?) {
        if (customView != null) {
            callback?.onCustomViewHidden()
            return
        }
        customView = view
        customViewCallback = callback
        customViewContainer.addView(view)
        customViewContainer.visibility = View.VISIBLE
        activity.setFullscreenMode(true)
    }

    override fun onHideCustomView() {
        if (customView == null) return
        customViewContainer.removeView(customView)
        customView = null
        customViewContainer.visibility = View.GONE
        customViewCallback?.onCustomViewHidden()
        activity.setFullscreenMode(false)
    }

    override fun onJsAlert(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {
        MaterialAlertDialogBuilder(activity)
            .setTitle("Studio Suite")
            .setMessage(message ?: "")
            .setPositiveButton("OK") { _, _ -> result?.confirm() }
            .setOnCancelListener { result?.cancel() }
            .show()
        return true
    }

    override fun onJsConfirm(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {
        MaterialAlertDialogBuilder(activity)
            .setTitle("Studio Suite")
            .setMessage(message ?: "")
            .setPositiveButton("Confirm") { _, _ -> result?.confirm() }
            .setNegativeButton("Cancel") { _, _ -> result?.cancel() }
            .setOnCancelListener { result?.cancel() }
            .show()
        return true
    }

    override fun onJsPrompt(
        view: WebView?,
        url: String?,
        message: String?,
        defaultValue: String?,
        result: JsPromptResult?
    ): Boolean {
        val input = EditText(activity).apply {
            setText(defaultValue ?: "")
            setSelection(text.length)
        }
        MaterialAlertDialogBuilder(activity)
            .setTitle(message ?: "Prompt")
            .setView(input)
            .setPositiveButton("OK") { _, _ -> result?.confirm(input.text.toString()) }
            .setNegativeButton("Cancel") { _, _ -> result?.cancel() }
            .setOnCancelListener { result?.cancel() }
            .show()
        return true
    }
}
