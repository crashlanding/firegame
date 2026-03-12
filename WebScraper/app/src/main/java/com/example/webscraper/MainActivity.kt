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
                        var clones = document.documentElement.cloneNode(true);
                        var scripts = clones.querySelectorAll('script, style, noscript, head');
                        scripts.forEach(function(el) { el.remove(); });
                        var rawText = clones.innerText || clones.textContent || '';
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

        // If launched from a browser's share sheet, grab the shared URL and
        // start scraping immediately — no extra taps needed.
        handleShareIntent(intent)
    }

    /**
     * Called when the activity is already running and the user shares another
     * URL to it (singleTop / singleTask reuse scenario).
     */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleShareIntent(intent)
    }

    /**
     * Extracts a URL from an ACTION_SEND intent (e.g. from Chrome's share sheet)
     * and begins scraping it automatically.
     */
    private fun handleShareIntent(intent: Intent) {
        if (intent.action != Intent.ACTION_SEND) return
        if (intent.type != "text/plain") return

        val sharedText = intent.getStringExtra(Intent.EXTRA_TEXT) ?: return
        // Browsers typically share the raw URL as EXTRA_TEXT
        val url = sharedText.trim()
        if (url.isNotEmpty()) {
            urlInput.setText(url)
            startScrape()
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
        setBusy("Loading page…")
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
                sendToChatGpt(text, pageTitle)
            }
        }
    }

    /**
     * Sends the scraped text to the ChatGPT app if installed, otherwise falls
     * back to the standard Android share sheet so the user can pick any app.
     */
    private fun sendToChatGpt(text: String, pageTitle: String) {
        val label = pageTitle.ifBlank { urlInput.text.toString() }
        statusText.text = "Scraped ${text.length} characters from \"$label\". Sending…"

        val sendIntent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, text)
        }

        val chatGptInstalled = try {
            packageManager.getPackageInfo(CHATGPT_PACKAGE, 0)
            true
        } catch (_: PackageManager.NameNotFoundException) {
            false
        }

        if (chatGptInstalled) {
            // Target ChatGPT directly — no chooser dialog shown
            sendIntent.setPackage(CHATGPT_PACKAGE)
            startActivity(sendIntent)
        } else {
            // ChatGPT not installed: let the user pick from all share targets
            startActivity(Intent.createChooser(sendIntent, "Send scraped text to…"))
        }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }
}
