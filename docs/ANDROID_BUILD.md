# Android Build — get an installable APK

Two paths. CI is the "download one file" experience you wanted.

## Path A — GitHub Actions (recommended)

1. Push this repo to GitHub.
2. (Optional, for a *signed release* APK) add repo secrets:
   - `FRIDAY_API_TOKEN` — must match the brain's token.
   - `ANDROID_KEYSTORE_B64` — `base64 -w0 friday-keystore.jks`
   - `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`
3. Actions tab → **android-apk** → **Run workflow** → set `brain_url` to your AWS `BrainApiUrl`.
4. Download the APK from the run's **Artifacts** (`friday-ugc-apk`).
5. Transfer to the phone and install (see "Install" below).

Without signing secrets you still get a **debug APK**, which installs fine for personal testing.

### Create a keystore (one time, local)

```bash
keytool -genkey -v -keystore friday-keystore.jks -keyalg RSA -keysize 2048 \
  -validity 10000 -alias friday
base64 -w0 friday-keystore.jks   # paste into ANDROID_KEYSTORE_B64 secret
```

## Path B — Android Studio (local)

```bash
cd android
gradle wrapper --gradle-version 8.9      # first time only, creates ./gradlew
./gradlew assembleDebug \
  -Pfriday.brainUrl=http://YOUR_AWS_HOST:8080 \
  -Pfriday.apiToken=YOUR_TOKEN
# APK at: android/app/build/outputs/apk/debug/app-debug.apk
```

## Install on the phone

1. Copy the `.apk` to the phone (USB file transfer, or download from the Actions artifact link).
2. Open it with a file manager; allow "install from unknown sources" for that app.
3. Launch **Friday UGC**.

## Emulator testing (what it's good for)

- Use an emulator (Pixel API 34) to test the **loop mechanics** on Settings/Chrome:
  read tree → scroll → tap → back. This validates `ScreenReader`/`ActionExecutor` fast.
- **Do not** rely on the emulator for Instagram: IG frequently blocks emulators and triggers
  login checkpoints. Do real IG testing on a **physical device + throwaway account**.

```bash
# quick emulator smoke (with Android SDK installed):
emulator -avd Pixel_API_34 &
adb install android/app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.miguelbits.fridayugc/.MainActivity
```

## Common build issues

| Error | Fix |
|-------|-----|
| `SDK location not found` | create `android/local.properties` with `sdk.dir=/path/to/Android/Sdk` |
| Gradle wrapper missing | run `gradle wrapper --gradle-version 8.9` in `android/` |
| `INSTALL_FAILED_...` on install | uninstall old build; enable unknown-sources for the installer app |
