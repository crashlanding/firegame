#!/usr/bin/env python3
"""
Run this once from your Mac terminal:
    python3 ~/Desktop/setup_webscraper.py

It creates (or updates) the WebScraper Android project in
~/AndroidStudioProjects/WebScraper with all the latest files.
"""

import os, sys

BASE = os.path.expanduser("~/AndroidStudioProjects/WebScraper")

files = {}

# ── AndroidManifest.xml ──────────────────────────────────────────────────────
files["app/src/main/AndroidManifest.xml"] = """\
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission
        android:name="android.permission.WRITE_EXTERNAL_STORAGE"
        android:maxSdkVersion="28" />

    <!-- Required on API 30+ to detect whether ChatGPT is installed -->
    <queries>
        <package android:name="com.openai.chatgpt" />
    </queries>

    <application
        android:allowBackup="true"
        android:label="@string/app_name"
        android:icon="@mipmap/ic_launcher"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:supportsRtl="true"
        android:theme="@style/Theme.WebScraper"
        android:usesCleartextTraffic="true">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:windowSoftInputMode="adjustResize">

            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>

            <!-- Appears as "Web Scraper" in the share sheet -->
            <intent-filter>
                <action android:name="android.intent.action.SEND" />
                <category android:name="android.intent.category.DEFAULT" />
                <data android:mimeType="text/plain" />
            </intent-filter>

        </activity>

    </application>

</manifest>
"""

# ── MainActivity.kt ──────────────────────────────────────────────────────────
files["app/src/main/java/com/example/webscraper/MainActivity.kt"] = """\
package com.example.webscraper

import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

private const val CHATGPT_PACKAGE = "com.openai.chatgpt"

class MainActivity : AppCompatActivity() {

    private lateinit var urlInput: EditText
    private lateinit var scrapeButton: Button
    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var statusText: TextView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        urlInput = findViewById(R.id.urlInput)
        scrapeButton = findViewById(R.id.scrapeButton)
        webView = findViewById(R.id.webView)
        progressBar = findViewById(R.id.progressBar)
        statusText = findViewById(R.id.statusText)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            setSupportZoom(false)
            userAgentString = "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            cacheMode = WebSettings.LOAD_NO_CACHE
        }

        webView.addJavascriptInterface(TextExtractorBridge(), "Android")

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                progressBar.progress = newProgress
            }
        }

        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                view?.evaluateJavascript(\"\"\"
                    (function() {
                        var clones = document.documentElement.cloneNode(true);
                        var scripts = clones.querySelectorAll('script, style, noscript, head');
                        scripts.forEach(function(el) { el.remove(); });
                        var rawText = clones.innerText || clones.textContent || '';
                        var cleaned = rawText.replace(/\\r\\n/g, '\\n')
                                            .replace(/\\r/g, '\\n')
                                            .replace(/\\n{3,}/g, '\\n\\n')
                                            .replace(/[ \\t]{2,}/g, ' ')
                                            .trim();
                        Android.receiveText(cleaned, document.title || '');
                    })();
                \"\"\".trimIndent(), null)
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                if (request?.isForMainFrame == true) {
                    runOnUiThread {
                        setIdle()
                        statusText.text = "Failed to load page: \${error?.description ?: "Unknown error"}"
                    }
                }
            }
        }

        scrapeButton.setOnClickListener { startScrape() }

        urlInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_GO) { startScrape(); true } else false
        }

        handleShareIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleShareIntent(intent)
    }

    private fun handleShareIntent(intent: Intent) {
        if (intent.action != Intent.ACTION_SEND) return
        if (intent.type != "text/plain") return
        val url = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim() ?: return
        if (url.isNotEmpty()) { urlInput.setText(url); startScrape() }
    }

    private fun startScrape() {
        var url = urlInput.text.toString().trim()
        if (url.isEmpty()) { Toast.makeText(this, "Please enter a URL", Toast.LENGTH_SHORT).show(); return }
        if (!url.startsWith("http://") && !url.startsWith("https://")) url = "https://\$url"
        setBusy("Loading page\u2026")
        webView.loadUrl(url)
    }

    private fun setBusy(message: String) {
        scrapeButton.isEnabled = false
        progressBar.visibility = View.VISIBLE
        statusText.text = message
    }

    private fun setIdle() {
        scrapeButton.isEnabled = true
        progressBar.visibility = View.INVISIBLE
    }

    inner class TextExtractorBridge {
        @JavascriptInterface
        fun receiveText(text: String, pageTitle: String) {
            runOnUiThread {
                setIdle()
                if (text.isBlank()) { statusText.text = "Page loaded but no text was found."; return@runOnUiThread }
                sendToChatGpt(text, pageTitle)
            }
        }
    }

    private fun sendToChatGpt(text: String, pageTitle: String) {
        val label = pageTitle.ifBlank { urlInput.text.toString() }
        statusText.text = "Scraped \${text.length} characters from \\"\$label\\". Sending\u2026"

        val sendIntent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, text)
        }

        val chatGptInstalled = try { packageManager.getPackageInfo(CHATGPT_PACKAGE, 0); true }
                               catch (_: PackageManager.NameNotFoundException) { false }

        if (chatGptInstalled) {
            sendIntent.setPackage(CHATGPT_PACKAGE)
            startActivity(sendIntent)
        } else {
            startActivity(Intent.createChooser(sendIntent, "Send scraped text to\u2026"))
        }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else { @Suppress("DEPRECATION") super.onBackPressed() }
    }
}
"""

# ── activity_main.xml ────────────────────────────────────────────────────────
files["app/src/main/res/layout/activity_main.xml"] = """\
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:background="#F5F5F5">

    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="vertical"
        android:background="#1565C0"
        android:padding="12dp"
        android:elevation="4dp">

        <TextView
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:text="Scrape as Text"
            android:textColor="#FFFFFF"
            android:textSize="20sp"
            android:textStyle="bold"
            android:layout_marginBottom="10dp"/>

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="horizontal">

            <EditText
                android:id="@+id/urlInput"
                android:layout_width="0dp"
                android:layout_height="48dp"
                android:layout_weight="1"
                android:hint="https://example.com"
                android:inputType="textUri"
                android:imeOptions="actionGo"
                android:singleLine="true"
                android:background="#FFFFFF"
                android:paddingStart="12dp"
                android:paddingEnd="12dp"
                android:textSize="14sp"
                android:layout_marginEnd="8dp"/>

            <Button
                android:id="@+id/scrapeButton"
                android:layout_width="wrap_content"
                android:layout_height="48dp"
                android:text="Scrape &amp; Send"
                android:backgroundTint="#FFA726"
                android:textColor="#FFFFFF"
                android:textSize="13sp"
                android:textStyle="bold"/>
        </LinearLayout>

        <ProgressBar
            android:id="@+id/progressBar"
            style="?android:attr/progressBarStyleHorizontal"
            android:layout_width="match_parent"
            android:layout_height="4dp"
            android:max="100"
            android:progressTint="#FFA726"
            android:visibility="invisible"
            android:layout_marginTop="8dp"/>
    </LinearLayout>

    <TextView
        android:id="@+id/statusText"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:padding="12dp"
        android:text="Enter a URL and tap Scrape &amp; Send — or share any page from Chrome using the share sheet."
        android:textSize="13sp"
        android:textColor="#555555"
        android:background="#E3F2FD"
        android:minHeight="48dp"/>

    <WebView
        android:id="@+id/webView"
        android:layout_width="match_parent"
        android:layout_height="0dp"
        android:layout_weight="1"/>

</LinearLayout>
"""

# ── Launcher icons ───────────────────────────────────────────────────────────
files["app/src/main/res/drawable/ic_launcher_background.xml"] = """\
<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="#FF6200EE"/>
</shape>
"""

files["app/src/main/res/drawable/ic_launcher_foreground.xml"] = """\
<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path
        android:fillColor="#FFFFFF"
        android:pathData="M54,32 C42,32 32,42 32,54 C32,66 42,76 54,76 C66,76 76,66 76,54 C76,42 66,32 54,32 Z M54,70 C45,70 38,63 38,54 C38,45 45,38 54,38 C63,38 70,45 70,54 C70,63 63,70 54,70 Z"/>
</vector>
"""

adaptive = """\
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background"/>
    <foreground android:drawable="@drawable/ic_launcher_foreground"/>
</adaptive-icon>
"""
files["app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml"] = adaptive
files["app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml"] = adaptive

layer = """\
<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:drawable="@drawable/ic_launcher_background"/>
    <item android:drawable="@drawable/ic_launcher_foreground"/>
</layer-list>
"""
files["app/src/main/res/mipmap-anydpi/ic_launcher.xml"] = layer
files["app/src/main/res/mipmap-anydpi/ic_launcher_round.xml"] = layer

# ── Write everything ─────────────────────────────────────────────────────────
for rel, content in files.items():
    path = os.path.join(BASE, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  wrote {rel}")

print(f"\nDone! Open {BASE} in Android Studio, then Run > Run 'app'.")
