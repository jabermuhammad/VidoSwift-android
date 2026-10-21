# VidoSwift Download Studio — Android Client

An authentic, dark-themed Android application built with React Native and Expo for downloading media from authorized sources.

## Features
- **URL Analysis**: Enter or paste any supported video URL to extract video title, thumbnail, duration, uploader, and available formats.
- **Quality & Format Selection**: Choose from available resolutions (1080p, 720p, 480p, 360p, or Audio) with estimated file sizes.
- **Download & Export**: Downloads video to app storage with native Android file sharing to save directly to device gallery or send to other apps.
- **Download History**: Persisted locally via AsyncStorage with status badges (Completed/Failed), timestamps, and retry/open actions.
- **Settings & Preferences**:
  - Default Quality preference
  - Wi-Fi only download protection
  - Clipboard suggestion banner on launch
  - Notifications toggle
  - Backend health test (`/v1/health`)
- **VidoSwift Dark Theme**: Distinctive dark interface (`#111116` / `#19191f`) with electric cyan/blue accents (`#3478f6` / `#38bdf8`) faithfully preserving the original design system.

## Project Structure
```text
vidoswift-android-final/
├── App.tsx             # Complete application with Home, History, and Settings screens
├── app.json            # Expo configuration (package: com.vidoswift.downloadstudio)
├── eas.json            # EAS Build configuration for APK preview and production builds
├── package.json        # Expo SDK dependencies
├── tsconfig.json       # TypeScript configuration
├── src/
│   └── config.ts       # Backend API URL (default: https://vidoswift.onrender.com)
├── assets/             # App icons, adaptive icons, and splash screens
└── README_BN.md        # Bengali documentation
```

## Running the App

### Option 1: Expo Go (Development)
1. Install Node.js 20 or 22.
2. In this folder, install dependencies:
   ```bash
   npm install
   ```
3. Start the Expo development server:
   ```bash
   npx expo start
   ```
4. Scan the QR code using the **Expo Go** app on your Android device.

### Option 2: Build Standalone Android APK (EAS Build)
1. Install EAS CLI globally:
   ```bash
   npm install -g eas-cli
   ```
2. Log in to your Expo account:
   ```bash
   eas login
   ```
3. Run the Android preview build to generate an installable `.apk` file:
   ```bash
   eas build --platform android --profile preview
   ```
4. Once the build completes, download and install the APK on your device.

## Backend Connection
The Android app communicates with the VidoSwift FastAPI backend:
- `POST /v1/analyze`: Analyzes video metadata and returns format options.
- `GET /v1/download`: Downloads the merged video file.
- `GET /v1/health`: Checks backend health and availability.

To point the app to your own self-hosted or local backend, edit `src/config.ts` or set the `EXPO_PUBLIC_API_BASE_URL` environment variable.
