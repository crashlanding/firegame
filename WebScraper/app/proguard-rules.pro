# Keep JavaScript interface methods accessible from WebView
-keepclassmembers class com.example.webscraper.MainActivity$TextExtractorBridge {
    @android.webkit.JavascriptInterface <methods>;
}
