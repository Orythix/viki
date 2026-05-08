# Mobile automation — Appium 2 (pattern only)

## Stack

- **Appium 2** + **UiAutomator2** (Android) / **XCUITest** (iOS)
- **Java** or **Python** client; same Page Object ideas as web.

## Example capabilities (Android) — do not commit real device farms

```json
{
  "platformName": "Android",
  "appium:deviceName": "Pixel_6_API_34",
  "appium:app": "/path/to/your-debug.apk",
  "appium:automationName": "UiAutomator2"
}
```

## Homework

1. Start **Android Emulator** locally.
2. `appium driver install uiautomator2`
3. Minimal test: launch app → assert package name or home screen id.

## CI

Use **Sauce Labs**, **BrowserStack**, **Firebase Test Lab**, or self-hosted device farm. Never point lab scripts at **users’ personal devices** without consent.

## Selenium overlap

Appium reuses **WebDriver** protocol; concepts (waits, locators, page objects) transfer from Selenium Web **after** you learn one web stack deeply.
