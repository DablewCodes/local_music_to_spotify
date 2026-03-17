import os
import re
import time
from typing import Optional

import httpx

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8000/spotify/callback")

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SPOTIFY_SCOPES = "playlist-modify-public playlist-modify-private"


def get_auth_url(state: str) -> str:
    params = (
        f"?client_id={SPOTIFY_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={SPOTIFY_REDIRECT_URI}"
        f"&scope={SPOTIFY_SCOPES.replace(' ', '%20')}"
        f"&state={state}"
    )
    return SPOTIFY_AUTH_URL + params


def exchange_code(code: str) -> dict:
    with httpx.Client() as client:
        resp = client.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": SPOTIFY_REDIRECT_URI,
            },
            auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        )
        resp.raise_for_status()
        data = resp.json()
        data["expires_at"] = time.time() + data["expires_in"]
        return data


def refresh_access_token(refresh_token: str) -> dict:
    with httpx.Client() as client:
        resp = client.post(
            SPOTIFY_TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        )
        resp.raise_for_status()
        data = resp.json()
        data["expires_at"] = time.time() + data["expires_in"]
        return data


def get_valid_token(db, user_id: int) -> Optional[str]:
    row = db.execute(
        "SELECT access_token, refresh_token, expires_at FROM spotify_tokens WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if not row:
        return None

    if time.time() >= row["expires_at"] - 60:
        refreshed = refresh_access_token(row["refresh_token"])
        db.execute(
            "UPDATE spotify_tokens SET access_token = ?, expires_at = ? WHERE user_id = ?",
            (refreshed["access_token"], refreshed["expires_at"], user_id),
        )
        db.commit()
        return refreshed["access_token"]

    return row["access_token"]


def clean_filename(filename: str) -> str:
    name = re.sub(r'\.[^.]+$', '', filename)       # remove extension
    name = re.sub(r'^\d+[\s.\-]+', '', name)        # remove leading track numbers
    name = re.sub(r'[\(\[\{][^\)\]\}]*[\)\]\}]', '', name)  # remove parenthetical tags
    return name.strip()


def search_track(token: str, query: str) -> Optional[dict]:
    with httpx.Client() as client:
        resp = client.get(
            f"{SPOTIFY_API_BASE}/search",
            params={"q": query, "type": "track", "limit": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 2))
            time.sleep(retry_after)
            return search_track(token, query)
        resp.raise_for_status()
        items = resp.json().get("tracks", {}).get("items", [])
        if items:
            t = items[0]
            return {
                "uri": t["uri"],
                "name": t["name"],
                "artist": t["artists"][0]["name"] if t["artists"] else "",
                "album": t["album"]["name"],
            }
    return None


def get_spotify_user_id(token: str) -> str:
    with httpx.Client() as client:
        resp = client.get(
            f"{SPOTIFY_API_BASE}/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()["id"]


def create_playlist(token: str, user_id: str, name: str) -> dict:
    with httpx.Client() as client:
        resp = client.post(
            f"{SPOTIFY_API_BASE}/users/{user_id}/playlists",
            json={"name": name, "public": False, "description": "Created by Local Music to Spotify"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


def add_tracks_to_playlist(token: str, playlist_id: str, uris: list[str]):
    with httpx.Client() as client:
        for i in range(0, len(uris), 100):
            chunk = uris[i : i + 100]
            resp = client.post(
                f"{SPOTIFY_API_BASE}/playlists/{playlist_id}/tracks",
                json={"uris": chunk},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
