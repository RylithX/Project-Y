# Preserve JavascriptInterface methods for WebKit bridge
-keepattributes JavascriptInterface
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

-keep class com.discord.studio.StudioBridge {
    public *;
}
