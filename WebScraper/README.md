# Web Page Scraper – Android App

A simple Android app that loads any URL using the built-in WebView (Chrome engine), extracts all visible text from the page, and saves it as a `.txt` file in your **Downloads** folder.

## Features

- Enter any URL (http or https)
- Page loads inside the app using the same engine as Chrome
- One tap to extract all visible text (scripts/styles are stripped out)
- Saved automatically to `Downloads/<PageTitle>_<timestamp>.txt`
- Works on Android 7.0 (API 24) and above

## How to Build

### Requirements
- Android Studio Hedgehog (2023.1) or newer
- Android SDK 34

### Steps
1. Open Android Studio → **File → Open** → select the `WebScraper/` folder
2. Let Gradle sync finish
3. Connect your Android phone via USB (enable Developer Options + USB Debugging)
4. Click **Run ▶** or press `Shift+F10`

### Install a pre-built APK
If you have the APK:
```bash
adb install WebScraper-debug.apk
```

## Usage

1. Launch **Web Scraper** on your phone
2. Type or paste a URL in the top bar (e.g. `https://en.wikipedia.org/wiki/Kotlin`)
3. Tap **Save Text** (or press Go on the keyboard)
4. Watch the page load in the WebView below
5. When the page finishes loading the text is extracted and saved automatically
6. A toast notification tells you the file name — find it in your Downloads folder

## Permissions

| Permission | Why |
|---|---|
| `INTERNET` | Load web pages |
| `WRITE_EXTERNAL_STORAGE` | Save files on Android 9 and below only |

On Android 10+ files are saved via MediaStore — no storage permission is required.

## Project Structure

```
WebScraper/
├── app/
│   ├── src/main/
│   │   ├── java/com/example/webscraper/
│   │   │   └── MainActivity.kt      ← all logic here
│   │   ├── res/
│   │   │   ├── layout/activity_main.xml
│   │   │   └── values/
│   │   └── AndroidManifest.xml
│   ├── build.gradle
│   └── proguard-rules.pro
├── build.gradle
├── settings.gradle
└── gradle/wrapper/gradle-wrapper.properties
```
