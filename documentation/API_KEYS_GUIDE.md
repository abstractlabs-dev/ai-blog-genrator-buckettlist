# How to Get API Keys for Blogger & Tumblr

This step-by-step guide walks you through obtaining the necessary OAuth keys and tokens for publishing to Blogger and Tumblr automatically using your AI Blog Generator.

---

## 1. Google Blogger API Setup

To publish to Blogger, you need to create a project on the Google Cloud Console, enable the Blogger API v3, and generate OAuth 2.0 Credentials (client secrets). 

### Step 1.1: Create a Google Cloud Project & Enable Blogger
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click on the project dropdown at the top and select **New Project**. Name it something like "AI-Blog-Auto-Publisher" and click Create.
3. In the search bar at the top, type **Blogger API v3**.
4. Click on the API in the results and click **Enable**.

### Step 1.2: Configure the OAuth Consent Screen
1. On the left sidebar, navigate to **APIs & Services > OAuth consent screen**.
2. Choose **External** user type and click **Create**.
3. Fill in the required fields (App name, User support email, Developer contact email) and click **Save and Continue**.
4. Skip the Scopes screen by clicking **Save and Continue**.
5. On the **Test users** screen, click **+ Add Users** and add your own Google email address (the one you will use to log into Blogger). Click **Save and Continue**.

### Step 1.3: Generate OAuth Client ID (client_secrets.json)
1. On the left sidebar, navigate to **APIs & Services > Credentials**.
2. Click **+ Create Credentials** at the top and choose **OAuth client ID**.
3. Set Application type to **Desktop app**.
4. Give it a name (e.g., "Blogger Desktop Client") and click **Create**.
5. A popup will appear with your Client ID and Client Secret. Click **Download JSON**.
6. Move the downloaded JSON file into the codebase under the `src/` folder and rename it to `credentials1.json` (or `credentials2.json`, `credentials3.json` if configuring multiple blogs).

### Step 1.4: Generate the Authorization Token (.pkl)
Now that you have the `credentials1.json` file, you need to authorize it to generate the `blogger1.pkl` file used by the system.
1. Open a terminal in the project root.
2. Ensure you have the required Google auth library installed:
   ```bash
   pip install google-auth-oauthlib google-api-python-client
   ```
3. Run the built-in token generator script:
   ```bash
   python src/generate_token.py
   ```
4. A web browser will open asking you to log into Google. Select the account you added as a test user and click **Allow** to grant permissions.
5. You will see a success message in the console, and a `tokens/blogger1.pkl` file will be generated!
6. Open `.env` and set `BLOGGER_BLOG_ID1=your_blog_id_here`. You can find your blog ID by going to Blogger dashboard and looking at the URL: `https://www.blogger.com/blog/posts/YOUR_BLOG_ID_IS_HERE`.

---

## 2. Tumblr API Setup

To publish to Tumblr, you need to register an application on the Tumblr Developer portal to get a Consumer Key and Secret, and then use OAuth to generate an Access Token and Secret.

### Step 2.1: Register a Tumblr Application
1. Log into Tumblr in your web browser.
2. Go to the [Tumblr OAuth Apps Portal](https://www.tumblr.com/oauth/apps).
3. Click **+ Register application**.
4. Fill in the required details:
   - **Application Name**: AI Blog Generator
   - **Application Website**: `http://localhost`
   - **Application Description**: Auto publisher
   - **Administrative contact email**: Your email
   - **Default callback URL**: `http://localhost`
5. Click **Register**.
6. On the next screen, you will see your **OAuth Consumer Key**. Look for a link/button that says **Show secret key** and copy your **Consumer Secret**.
7. Open `.env` and add these to:
   - `TUMBLR_CONSUMER_KEY`
   - `TUMBLR_CONSUMER_SECRET`
   - `TUMBLR_BLOG_HOSTNAME` (e.g., `mycoolblog.tumblr.com`)

### Step 2.2: Generate the Authorization Token (.json)
Unlike Blogger, Tumblr uses OAuth 1.0a. We have provided a handy script to generate your token file!

1. Open a terminal in the project root.
2. Install the OAuth library if you haven't:
   ```bash
   pip install requests_oauthlib
   ```
3. Run the Tumblr token generator script we created:
   ```bash
   python scratch/generate_tumblr_token.py
   ```
4. The script will guide you through the process:
   - It will load your Consumer Key/Secret from `.env`.
   - It will print a URL. Click the URL to open it in your browser.
   - Click **Allow** on the Tumblr page.
   - Tumblr will redirect you to an empty `http://localhost...` page. 
   - Copy the ENTIRE URL you were redirected to and paste it back into the terminal.
5. The script will generate a `tumblr_token.json` file in your project root!
6. You are now fully configured to publish to Tumblr!
