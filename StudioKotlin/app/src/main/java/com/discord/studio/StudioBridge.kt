package com.discord.studio

import android.content.ClipData
import android.content.ClipboardManager
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.provider.MediaStore
import android.util.Base64
import android.util.Log
import android.webkit.JavascriptInterface
import android.widget.Toast
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStream

class StudioBridge(
    private val activity: MainActivity,
    private val config: StudioConfig
) {
    private val handler = Handler(Looper.getMainLooper())

    companion object {
        private const val TAG = "StudioBridge"
    }

    @JavascriptInterface
    fun showToast(message: String) {
        handler.post {
            Toast.makeText(activity, message, Toast.LENGTH_SHORT).show()
        }
    }

    @JavascriptInterface
    fun copyToClipboard(text: String) {
        handler.post {
            val clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = ClipData.newPlainText("Studio Suite", text)
            clipboard.setPrimaryClip(clip)
            Toast.makeText(activity, "Copied to clipboard", Toast.LENGTH_SHORT).show()
        }
    }

    @JavascriptInterface
    fun shareText(title: String, text: String) {
        handler.post {
            val intent = Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_SUBJECT, title)
                putExtra(Intent.EXTRA_TEXT, text)
            }
            activity.startActivity(Intent.createChooser(intent, title))
        }
    }

    @JavascriptInterface
    fun vibrate(type: String, durationMs: Long) {
        if (!config.hapticsEnabled) return

        handler.post {
            try {
                val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    val manager = activity.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
                    manager?.defaultVibrator
                } else {
                    @Suppress("DEPRECATION")
                    activity.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
                }

                if (vibrator != null && vibrator.hasVibrator()) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        val effect = when (type.lowercase()) {
                            "click" -> {
                                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                                    VibrationEffect.createPredefined(VibrationEffect.EFFECT_CLICK)
                                } else {
                                    VibrationEffect.createOneShot(20, VibrationEffect.DEFAULT_AMPLITUDE)
                                }
                            }
                            "heavy_click" -> {
                                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                                    VibrationEffect.createPredefined(VibrationEffect.EFFECT_HEAVY_CLICK)
                                } else {
                                    VibrationEffect.createOneShot(45, VibrationEffect.DEFAULT_AMPLITUDE)
                                }
                            }
                            "double_click" -> {
                                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                                    VibrationEffect.createPredefined(VibrationEffect.EFFECT_DOUBLE_CLICK)
                                } else {
                                    VibrationEffect.createWaveform(longArrayOf(0, 25, 40, 25), -1)
                                }
                            }
                            "tick" -> {
                                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                                    VibrationEffect.createPredefined(VibrationEffect.EFFECT_TICK)
                                } else {
                                    VibrationEffect.createOneShot(10, 80)
                                }
                            }
                            else -> {
                                val dur = if (durationMs > 0) durationMs else 25L
                                VibrationEffect.createOneShot(dur, VibrationEffect.DEFAULT_AMPLITUDE)
                            }
                        }
                        vibrator.vibrate(effect)
                    } else {
                        @Suppress("DEPRECATION")
                        vibrator.vibrate(if (durationMs > 0) durationMs else 25L)
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "Vibration failed: ${e.message}")
            }
        }
    }

    @JavascriptInterface
    fun speakText(text: String, voiceName: String, pitch: Float, rate: Float) {
        handler.post {
            activity.speakText(text, voiceName, pitch, rate)
        }
    }

    @JavascriptInterface
    fun stopSpeech() {
        handler.post {
            activity.stopSpeech()
        }
    }

    @JavascriptInterface
    fun startSpeechRecognition() {
        handler.post {
            activity.startSpeechRecognition()
        }
    }

    @JavascriptInterface
    fun stopSpeechRecognition() {
        handler.post {
            activity.stopSpeechRecognition()
        }
    }

    @JavascriptInterface
    fun exportBotCard(jsonContent: String, fileName: String) {
        handler.post {
            try {
                val cleanName = if (fileName.endsWith(".json")) fileName else "$fileName.json"
                val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                if (!downloadsDir.exists()) downloadsDir.mkdirs()
                val targetFile = File(downloadsDir, cleanName)
                targetFile.writeText(jsonContent)
                Toast.makeText(activity, "Saved to Downloads/${targetFile.name}", Toast.LENGTH_LONG).show()
            } catch (e: Exception) {
                Log.e(TAG, "Failed to export bot card: ${e.message}")
                Toast.makeText(activity, "Export failed: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    @JavascriptInterface
    fun saveDoodle(base64Data: String, fileName: String) {
        handler.post {
            try {
                val cleanData = if (base64Data.contains(",")) base64Data.substringAfter(",") else base64Data
                val decodedBytes = Base64.decode(cleanData, Base64.DEFAULT)
                val bitmap = BitmapFactory.decodeByteArray(decodedBytes, 0, decodedBytes.size)

                val name = if (fileName.endsWith(".png")) fileName else "$fileName.png"
                val contentValues = ContentValues().apply {
                    put(MediaStore.Images.Media.DISPLAY_NAME, name)
                    put(MediaStore.Images.Media.MIME_TYPE, "image/png")
                    put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/StudioSuite")
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                        put(MediaStore.Images.Media.IS_PENDING, 1)
                    }
                }

                val uri: Uri? = activity.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, contentValues)
                if (uri != null) {
                    val stream: OutputStream? = activity.contentResolver.openOutputStream(uri)
                    stream?.use {
                        bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
                    }
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                        contentValues.clear()
                        contentValues.put(MediaStore.Images.Media.IS_PENDING, 0)
                        activity.contentResolver.update(uri, contentValues, null, null)
                    }
                    Toast.makeText(activity, "Saved doodle to Pictures/StudioSuite", Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(activity, "Could not open media store for saving", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                Log.e(TAG, "Save doodle error: ${e.message}")
                Toast.makeText(activity, "Failed to save doodle: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    @JavascriptInterface
    fun getDeviceInfo(): String {
        return try {
            val bm = activity.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager
            val batteryLevel = bm?.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY) ?: -1
            val json = JSONObject().apply {
                put("platform", "Android")
                put("osVersion", Build.VERSION.RELEASE)
                put("sdkInt", Build.VERSION.SDK_INT)
                put("manufacturer", Build.MANUFACTURER)
                put("model", Build.MODEL)
                put("batteryLevel", batteryLevel)
                put("appVersion", "1.0.0")
                put("isNativeKotlinApp", true)
            }
            json.toString()
        } catch (e: Exception) {
            "{}"
        }
    }

    @JavascriptInterface
    fun openServerSettings() {
        handler.post {
            activity.showServerSettingsDialog()
        }
    }

    @JavascriptInterface
    fun getSavedServerUrl(): String {
        return config.getActiveUrl()
    }
}
