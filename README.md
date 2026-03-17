# local_music_to_spotify

Python web app that creates a Spotify playlist from locally stored music files.

## Features

* Scan a local folder containing music files
* Match tracks with Spotify catalog
* Automatically create a Spotify playlist
* Connect through Spotify Web API authentication

## Requirements

- Python 3.10+
- Spotify Developer Account
- Spotify Premium/Active Spotify Account

## Setup

### 1. Create a Spotify Developer App

Go to Spotify Developer Dashboard:

https://developer.spotify.com/

* Create a new app using the **Web API**
* Add the following redirect URIs:

```text
http://127.0.0.1:3000
http://127.0.0.1:3000/spotify/callback
```

### 2. Configure User Access

In **User Management**:

* Add the email address of the Spotify account where the playlist will be created

### 3. Configure Environment Variables

Copy:

* Client ID
* Client Secret

Create a `.env` file and add:

```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:3000/spotify/callback
SECRET_KEY=A-random-string-including-letters-numbers-symbols
```

### 4. Install Dependencies

Create and activate a virtual environment, then install requirements:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Run the Application

Start the server:

```bash
uvicorn main:app --reload --port 3000
```

### 6. Use the App

1. Register an account
2. Log in
3. Connect your Spotify account
4. Select the local folder containing music files
5. Run playlist creation

## Result

A Spotify playlist will be created automatically from the detected local music files.
