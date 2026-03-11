package com.example.webscraper

import android.annotation.SuppressLint
import android.content.ContentValues
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
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
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStreamWriter
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

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

        // Configure WebView to behave like Chrome
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

        // Add JavaScript bridge so the page can send text back to Kotlin
        webView.addJavascriptInterface(TextExtractorBridge(), "Android")

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                progressBar.progress = newProgress
            }
        }

        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                // Once the page is fully loaded, inject JS to extract all visible text
                view?.evaluateJavascript("""
                    (function() {
                        // Remove script and style elements so we don't grab code
                        var clones = document.documentElement.cloneNode(true);
                        var scripts = clones.querySelectorAll('script, style, noscript, head');
                        scripts.forEach(function(el) { el.remove(); });
                        var rawText = clones.innerText || clones.textContent || '';
                        // Clean up excessive whitespace
                        var cleaned = rawText.replace(/\r\n/g, '\n')
                                            .replace(/\r/g, '\n')
                                            .replace(/\n{3,}/g, '\n\n')
                                            .replace(/[ \t]{2,}/g, ' ')
                                            .trim();
                        Android.receiveText(cleaned, document.title || '');
                    })();
                """.trimIndent(), null)
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                if (request?.isForMainFrame == true) {
                    runOnUiThread {
                        setIdle()
                        val msg = error?.description ?: "Unknown error"
                        statusText.text = "Failed to load page: $msg"
                    }
                }
            }
        }

        scrapeButton.setOnClickListener { startScrape() }

        urlInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_GO) {
                startScrape()
                true
            } else false
        }
    }

    private fun startScrape() {
        var url = urlInput.text.toString().trim()
        if (url.isEmpty()) {
            Toast.makeText(this, "Please enter a URL", Toast.LENGTH_SHORT).show()
            return
        }
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "https://$url"
        }
        setBusy("Loading page...")
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

    /** JavaScript bridge — methods annotated with @JavascriptInterface are callable from JS */
    inner class TextExtractorBridge {
        @JavascriptInterface
        fun receiveText(text: String, pageTitle: String) {
            runOnUiThread {
                setIdle()
                if (text.isBlank()) {
                    statusText.text = "Page loaded but no text was found."
                    return@runOnUiThread
                }
                saveTextFile(text, pageTitle)
            }
        }
    }

    private fun saveTextFile(text: String, pageTitle: String) {
        val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val safeTitle = pageTitle
            .replace(Regex("[^a-zA-Z0-9_\\- ]"), "")
            .trim()
            .take(40)
            .ifEmpty { "webpage" }
        val fileName = "${safeTitle}_$timestamp.txt"

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                // Android 10+: use MediaStore to save into Downloads
                val values = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, fileName)
                    put(MediaStore.Downloads.MIME_TYPE, "text/plain")
                    put(MediaStore.Downloads.IS_PENDING, 1)
                }
                val resolver = contentResolver
                val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                    ?: throw Exception("Could not create file in Downloads")

                resolver.openOutputStream(uri)?.use { stream ->
                    OutputStreamWriter(stream, Charsets.UTF_8).use { it.write(text) }
                }

                values.clear()
                values.put(MediaStore.Downloads.IS_PENDING, 0)
                resolver.update(uri, values, null, null)
            } else {
                // Android 9 and below: write directly to Downloads folder
                val downloadsDir = Environment.getExternalStoragePublicDirectory(
                    Environment.DIRECTORY_DOWNLOADS
                )
                downloadsDir.mkdirs()
                val file = File(downloadsDir, fileName)
                FileOutputStream(file).use { fos ->
                    OutputStreamWriter(fos, Charsets.UTF_8).use { it.write(text) }
                }
            }

            statusText.text = "Saved to Downloads/$fileName\n(${text.length} characters)"
            Toast.makeText(this, "Saved: $fileName", Toast.LENGTH_LONG).show()
        } catch (e: Exception) {
            statusText.text = "Error saving file: ${e.message}"
            Toast.makeText(this, "Save failed: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }
}
