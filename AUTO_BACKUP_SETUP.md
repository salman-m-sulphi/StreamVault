# StreamVault automatic YouTube backups

StreamVault can check your own channel every five minutes while the app is open. When a livestream has ended and YouTube reports that its replay is processed, StreamVault downloads the best available video and audio into the selected output folder. It remembers completed downloads.

## One-time setup

1. In Google Cloud Console, create a project, enable **YouTube Data API v3**, and configure the OAuth consent screen.
2. Create an OAuth client with application type **Desktop app** and download its JSON file. If the consent screen is in testing mode, add your Google account as a test user.
3. In StreamVault, select that client JSON with **Choose Google client file**, then click **Connect YouTube**. Complete sign-in on Google's page in your browser. StreamVault does not ask for or save your Google password.
4. Choose a browser that is signed into the same YouTube account, set the output folder, and enable **Auto-download finished streams**.

The app checks streams from the prior 24 hours when the feature is first enabled, then remembers the broadcasts it has downloaded. The app must remain open. If a replay is still processing or a download fails, it is retried on later checks.

## Security

The Google authorization asks only for read-only YouTube access. Its refresh token is encrypted for the current Windows account using Windows Data Protection API. The client JSON contains a public desktop-app client ID and client secret, not your Google username or password. Keep the JSON file private nonetheless. The downloader reads authentication from the selected browser when it needs a private replay; StreamVault does not export browser cookies to a file. You can revoke StreamVault access in your Google account's third-party access settings.

For now, automatic checks operate while the desktop app is open. Available replay quality depends on what YouTube has finished processing. YouTube account sign-in and private-video downloading require a live account test; this build has only been tested locally without account credentials.
