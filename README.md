# Jelly Request

**Jelly Request** is a handy little app that keeps your media library fresh by automatically adding trending movies from IMDb to your Jellyseerr requests. No more hunting down what’s popular—it does the work for you, so you can kick back and enjoy your movies.

---

## What It Does

- **Finds trending movies**: Pulls a list of popular movies straight from IMDb.
- **Adds them to Jellyseerr**: Requests movies you don’t already have in your library.
- **Runs on its own**: Once you set it up, it keeps going without any extra effort from you.

---

## How to Install

Here’s how to get Jelly Request up and running on Unraid:

1. Open the **Apps** tab in your Unraid dashboard.
2. Search for "Jelly Request" in the Community Apps store.
3. Click **Install** to add it to your Docker containers.
4. Fill in these two key settings:
   - **Jellyseerr URL**: The address where your Jellyseerr is running (e.g., `http://192.168.0.29:5054`). You can find this by visiting Jellyseerr in your browser and copying the URL (minus any extra paths like `/settings`).
   - **API Key**: Head to Jellyseerr > **Settings** > **General**, and copy the API key listed there. Paste it into the field.
5. Leave the other settings alone—they come pre-configured with sensible defaults (like checking IMDb every week).
6. Hit **Apply**, and you’re good to go!

> **Pro Tip**: If your Jellyseerr is on the same Unraid server, you might use something like `http://localhost:5054` or your server’s IP. Just make sure Jelly Request can reach it!

---

## How It Works

Here’s the step-by-step of what Jelly Request does behind the scenes:

1. **Checks IMDb**: Every week (or your chosen interval), it grabs a list of trending movies from IMDb.
2. **Compares to your library**: It talks to Jellyseerr to see which of those movies you’re missing.
3. **Requests the good stuff**: Any movies not in your collection get added to your Jellyseerr requests.
4. **Repeats on schedule**: It keeps this up quietly in the background, so your library stays fresh.

  ![image](https://github.com/user-attachments/assets/db42d0ad-ebd1-49c6-babc-dcfe2a19b2a1)

---

## If Something Goes Wrong

Running into trouble? Here are the most common fixes:

- **Movies aren’t showing up in Jellyseerr**:
  - Double-check your **Jellyseerr URL**. Make sure it’s exact (e.g., no trailing slashes like `/` at the end unless needed).
  - Verify your **API key**. Copy it fresh from Jellyseerr’s settings to rule out typos.
- **App won’t start**:
  - Ensure your Unraid server has internet access—Jelly Request needs to reach IMDb.
  - Check that Jellyseerr is running and accessible at the URL you provided.
- **Still stuck?** Peek at the logs:
  - Go to the **Docker** tab in Unraid.
  - Find "Jelly Request," click it, and select **Logs**.
  - Look for error messages (like “connection failed” or “invalid key”) to get a clue.
- **Need more help?** Head to the [GitHub page](https://github.com/tophat17/jelly-request) to ask a question.

---

**License**: This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
