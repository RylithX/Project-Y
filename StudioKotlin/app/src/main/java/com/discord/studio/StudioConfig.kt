package com.discord.studio

import android.content.Context
import android.content.SharedPreferences

class StudioConfig(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("studio_suite_prefs", Context.MODE_PRIVATE)

    companion object {
        const val KEY_SERVER_MODE = "server_mode"
        const val KEY_CUSTOM_URL = "custom_url"
        const val KEY_HAPTICS = "haptics_enabled"
        const val KEY_NATIVE_TTS = "native_tts_enabled"

        const val MODE_BUNDLED = "bundled"
        const val MODE_LOCAL = "local"
        const val MODE_CUSTOM = "custom"

        const val DEFAULT_LOCAL_URL = "http://127.0.0.1:5000"
        const val ASSET_URL = "https://appassets.androidplatform.net/assets/studio/index.html"
    }

    var serverMode: String
        get() = prefs.getString(KEY_SERVER_MODE, MODE_BUNDLED) ?: MODE_BUNDLED
        set(value) = prefs.edit().putString(KEY_SERVER_MODE, value).apply()

    var customUrl: String
        get() = prefs.getString(KEY_CUSTOM_URL, DEFAULT_LOCAL_URL) ?: DEFAULT_LOCAL_URL
        set(value) = prefs.edit().putString(KEY_CUSTOM_URL, value).apply()

    var hapticsEnabled: Boolean
        get() = prefs.getBoolean(KEY_HAPTICS, true)
        set(value) = prefs.edit().putBoolean(KEY_HAPTICS, value).apply()

    var nativeTtsEnabled: Boolean
        get() = prefs.getBoolean(KEY_NATIVE_TTS, true)
        set(value) = prefs.edit().putBoolean(KEY_NATIVE_TTS, value).apply()

    fun getActiveUrl(): String {
        return when (serverMode) {
            MODE_LOCAL -> DEFAULT_LOCAL_URL
            MODE_CUSTOM -> customUrl
            else -> ASSET_URL
        }
    }
}
