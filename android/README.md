# Friday UGC — Android agent

The on-device "hands + eyes". Reads the Instagram UI via the Accessibility API and executes
the actions the AWS brain returns.

## Open in Android Studio

1. Open the `android/` folder in Android Studio (Koala+ / AGP 8.5).
2. First time only, generate the Gradle wrapper binary:

```bash
cd android && gradle wrapper --gradle-version 8.9
```

3. Set the brain URL + token when building (or edit `app/build.gradle.kts` defaults):

```bash
./gradlew assembleDebug -Pfriday.brainUrl=http://YOUR_AWS_HOST:8080 -Pfriday.apiToken=YOUR_TOKEN
```

## Key files

| File | Role |
|------|------|
| `FridayAccessibilityService.kt` | Always-on service: reads tree, exposes executor |
| `ScreenReader.kt` | Accessibility tree → compact indexed element list |
| `ActionExecutor.kt` | Executes tap/scroll/swipe/type/press/open_app |
| `BrainClient.kt` | HTTPS calls to the Gemma 4 brain |
| `AgentController.kt` | observe → decide → act loop + human pacing + approval gate |
| `VoiceManager.kt` | Friday's female TTS (+ STT hook) |
| `MainActivity.kt` | Setup panel: enable a11y, check brain, run a goal |

## Emulator note

Instagram blocks many emulators and flags automated logins. Use the emulator to test the
**agent loop against simple apps** (Settings, Chrome), and do real Instagram testing on a
physical device with a throwaway account first. See `../docs/ANDROID_BUILD.md`.
