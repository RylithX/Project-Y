# Studio Suite — Android Kotlin Application

Native Android Kotlin application packaging and supercharging the **Studio Suite** (Bot SaaS Studio).

## 🚀 Architecture & Overview

This project turns the entire web-based Studio Suite into a full-featured, hardware-accelerated Android native application with seamless Kotlin bridges to device hardware:

- **Package**: `com.discord.studio`
- **Language**: Kotlin 2.0.0 + Java 17
- **Min SDK**: 26 (Android 8.0 Oreo)
- **Target SDK**: 34 (Android 14)
- **Engine**: Hardware-accelerated Android WebKit with WebGL 2.0, WebAudio, and WebRTC
- **Build System**: Gradle 8.5.2 with Kotlin DSL (`build.gradle.kts`)

---

## 💎 Native Android Superpowers (StudioBridge)

The Kotlin native layer extends Studio Suite through `window.AndroidBridge`:

1. **Native Text-to-Speech (TTS)**:
   - Powered by Android's on-device `TextToSpeech` engine.
   - Zero network latency, offline operation, automatic viseme/expression syncing with 3D VRM models.

2. **Native Speech-to-Text (STT)**:
   - Powered by Android's `SpeechRecognizer` (`RecognizerIntent`).
   - Hands-free voice typing and conversational audio streaming directly into the chat input.

3. **Haptic Feedback Engine**:
   - Integrated with Android's `Vibrator` / `VibrationEffect` (`click`, `heavy_click`, `double_click`, `tick`).
   - Tactile button clicks, message receipts, and doodle brush strokes.

4. **Native File & Media Chooser**:
   - Handled via `WebChromeClient.onShowFileChooser`.
   - Select custom character avatars (JPEG/PNG/WebP/GIF) and 3D VRM models (`.vrm`, `.glb`) from Android file manager or Google Photos.

5. **Direct Media & Card Exporter**:
   - Export bot cards (`.json`) directly to `/storage/emulated/0/Download/`.
   - Save Doodle & Skribbl creations directly to `/storage/emulated/0/Pictures/StudioSuite/` (synced to Android MediaStore).

6. **Dual Mode Operation**:
   - **Bundled Offline Mode**: Runs self-contained directly from `assets/studio/index.html` with pre-bundled characters (`bots.json`).
   - **Local Bot Server Mode**: Connects to the local Termux Flask/Python backend at `http://127.0.0.1:5000`.
   - **Custom Server Mode**: Point to any remote domain or VPS.

7. **Immersive Edge-to-Edge Dark Mode**:
   - `WindowCompat.setDecorFitsSystemWindows(false)` with themed status bars and navigation bars matching the Studio dark aesthetic (`#0F0F0F`).
   - Fullscreen video support for Pokémon Showdown theater and YouTube player.

---

## 📂 Project Structure

```
StudioKotlin/
├── app/
│   ├── build.gradle.kts              # App module gradle configuration
│   ├── proguard-rules.pro            # Proguard preservation rules for JavascriptInterface
│   └── src/
│       └── main/
│           ├── AndroidManifest.xml   # Permissions (Audio, Camera, Storage, Vibrate)
│           ├── assets/
│           │   └── studio/
│           │       ├── index.html    # Full 12,600+ line Studio Suite
│           │       ├── bots.json     # Pre-bundled characters
│           │       └── studio_android_bridge.js # Bridge integration layer
│           ├── java/com/discord/studio/
│           │   ├── MainActivity.kt           # Edge-to-edge Activity, TTS/STT dispatcher
│           │   ├── StudioBridge.kt           # @JavascriptInterface native methods
│           │   ├── StudioConfig.kt           # SharedPreferences & URL management
│           │   ├── StudioWebChromeClient.kt  # File chooser, permissions, progress
│           │   └── StudioWebViewClient.kt    # AssetLoader, offline fallback, JS injection
│           └── res/
│               ├── layout/activity_main.xml  # Layout with WebView, ProgressBar, Fallback UI
│               ├── values/                   # Strings, colors (#0F0F0F, #E85D5D), themes
│               └── xml/file_paths.xml        # FileProvider paths for sharing
├── build.gradle.kts                  # Root Gradle build script
├── settings.gradle.kts               # Gradle settings
├── gradle.properties                 # JVM arguments and AndroidX flags
└── gradlew                           # Gradle wrapper runner
```

---

## 🛠️ Building & Running

### Option 1: In Android Studio
1. Open Android Studio.
2. Select **Open** and choose the `StudioKotlin` folder.
3. Allow Gradle to sync dependencies.
4. Click **Run** or press `Shift + F10` on a connected Android phone or emulator.

### Option 2: Command Line (Gradle)
```bash
./gradlew assembleDebug
```
The resulting APK will be located at:
`app/build/outputs/apk/debug/app-debug.apk`

---

## 📱 Server Connection Quick Switch
In the app, you can switch between Bundled Offline mode and Local Bot Server anytime:
- Tap the **Android App Settings** icon in the sidebar or from the menu.
- Select **Bundled Offline Studio** or **Local Bot Server (127.0.0.1:5000)**.
