# API Authentication & Setup Guide

This guide provides simple, step-by-step instructions for obtaining the necessary API keys and credentials for **WordPress**, **Blogger**, and **Tumblr**.

---

## 1. WordPress API (Application Passwords)
WordPress uses "Application Passwords" for automated posting. This is different from your regular login password.

### Steps to Generate:
1. **Log in** to your WordPress Dashboard.
2. Navigate to **Users** > **Profile** in the left sidebar.
3. Scroll down to the **Application Passwords** section.
4. **Enter a name** for the new password (e.g., "AI Blog Generator").
5. Click **Add New Application Password**.
6. **COPY THE PASSWORD**: WordPress will show you a 24-character code (e.g., `abcd efgh ijkl mnop qrst uvwx`). 
   > [!IMPORTANT]
   > Copy this immediately! It will only be shown once.

### Required for .env:
* `WORDPRESS_USERNAME`: Your regular WordPress username.
* `WORDPRESS_TOKEN`: The 24-character application password you just generated.

---

## 2. Blogger API (Google Cloud)
Blogger requires a "Client Secret" file from Google and a generated "Token" file (`.pkl`).

### Part A: Get the Credentials File
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. **Create a Project**: Click the project dropdown (top left) > **New Project**. Name it "Blogger Automation".
3. **Enable API**: Go to **APIs & Services** > **Library**. Search for **"Blogger API v3"** and click **Enable**.
4. **Consent Screen**: Go to **APIs & Services** > **OAuth consent screen**.
   - Select **External**.
   - Fill in "App Name" and your "Email".
   - Save and Continue through the steps.
5. **Create Credentials**: Go to **APIs & Services** > **Credentials**.
   - Click **Create Credentials** > **OAuth client ID**.
   - Select **Desktop App**.
   - Click **Create**.
6. **Download JSON**: Click the **Download** icon (down arrow) next to your new Client ID. Rename this file to `credentials.json` and place it in the `src/` folder.

### Part B: Generate the .pkl Token
The `.pkl` file is a "Permission Key" that lets the script act on your behalf.
1. Ensure your `credentials.json` is in the `src/` folder.
2. Run the token generator script:
   ```bash
   python src/generate_token.py
   ```
3. A browser window will open. **Log in** with your Blogger Google account and click **Allow**.
4. The script will save a file named `blogger_token.pkl` in the `tokens/` folder.

---

## 3. Tumblr API (OAuth)
Tumblr requires four pieces of information: a Consumer Key/Secret pair and a Token/Token Secret pair.

### Part A: Register Your App
1. Log in to [Tumblr](https://www.tumblr.com/).
2. Go to the [Tumblr OAuth Apps page](https://www.tumblr.com/oauth/apps).
3. Click **+ Register application**.
4. Fill in:
   - **Application Name**: "AI Content Bot"
   - **Application Website**: (Your website or any URL)
   - **Default Callback URL**: `http://localhost/`
5. Save the app. You will see your **OAuth Consumer Key**. Click **Show secret key** to see the **OAuth Consumer Secret**.

### Part B: Get the Token & Token Secret
The easiest way is to use the [Tumblr API Console](https://api.tumblr.com/console).
1. While logged into Tumblr, visit the console.
2. It will show your active tokens for the session.
3. Alternatively, create a `tumblr_token.json` file in the project root with this format:
   ```json
   {
     "access_token": "YOUR_ACCESS_TOKEN",
     "access_token_secret": "YOUR_ACCESS_TOKEN_SECRET"
   }
   ```

---

## 4. Understanding the .pkl and .json Files
- **.pkl files (Pickle)**: These are used by Google (Blogger). They securely store your "Login Session" so the script doesn't have to ask you to log in every time it runs.
- **.json files**: These are used by Tumblr to store your permanent access tokens.

### Summary Checklist for Deployment:
- [ ] **WordPress**: Username + Application Password.
- [ ] **Blogger**: `credentials.json` (Google Cloud) + `blogger_token.pkl` (Generated).
- [ ] **Tumblr**: Consumer Key + Consumer Secret + `tumblr_token.json`.

> [!TIP]
> Keep these files safe! They provide full access to your blogs. Never share them or upload them to public websites.
