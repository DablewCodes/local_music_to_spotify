import os
import secrets
import time

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

import auth as auth_utils
import spotify as sp
from database import get_db, init_db

app = FastAPI(title="Local Music to Spotify")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def startup():
    init_db()


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()


@app.get("/register", response_class=HTMLResponse)
def register_page():
    with open("static/register.html", encoding="utf-8") as f:
        return f.read()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    with open("static/dashboard.html", encoding="utf-8") as f:
        return f.read()


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@app.post("/auth/register")
def register(body: RegisterRequest):
    if len(body.username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (body.username, body.email, auth_utils.hash_password(body.password)),
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE username = ?", (body.username,)).fetchone()
        token = auth_utils.create_access_token(user["id"], user["username"])
        return {"token": token, "username": user["username"]}
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(400, "Username or email already taken")
        raise HTTPException(500, "Registration failed")
    finally:
        db.close()


@app.post("/auth/login")
def login(body: LoginRequest):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (body.email,)).fetchone()
    db.close()

    if not user or not auth_utils.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")

    token = auth_utils.create_access_token(user["id"], user["username"])
    return {"token": token, "username": user["username"]}


@app.get("/auth/me")
def me(current_user=Depends(auth_utils.get_current_user)):
    db = get_db()
    has_spotify = db.execute(
        "SELECT 1 FROM spotify_tokens WHERE user_id = ?", (current_user["id"],)
    ).fetchone() is not None
    db.close()
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "email": current_user["email"],
        "created_at": current_user["created_at"],
        "spotify_connected": has_spotify,
    }


# ── Spotify OAuth ─────────────────────────────────────────────────────────────

# Temporary state store: state_token -> user_id
_oauth_states: dict[str, int] = {}


@app.get("/spotify/connect")
def spotify_connect(current_user=Depends(auth_utils.get_current_user)):
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = current_user["id"]
    return {"url": sp.get_auth_url(state)}


@app.get("/spotify/callback")
def spotify_callback(code: str = None, state: str = None, error: str = None):
    if error or not code or not state:
        return RedirectResponse("/dashboard?spotify=error")

    user_id = _oauth_states.pop(state, None)
    if not user_id:
        return RedirectResponse("/dashboard?spotify=error")

    try:
        tokens = sp.exchange_code(code)
    except Exception:
        return RedirectResponse("/dashboard?spotify=error")

    db = get_db()
    db.execute(
        """INSERT INTO spotify_tokens (user_id, access_token, refresh_token, expires_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               access_token = excluded.access_token,
               refresh_token = excluded.refresh_token,
               expires_at = excluded.expires_at""",
        (user_id, tokens["access_token"], tokens["refresh_token"], tokens["expires_at"]),
    )
    db.commit()
    db.close()
    return RedirectResponse("/dashboard?spotify=connected")


@app.delete("/spotify/disconnect")
def spotify_disconnect(current_user=Depends(auth_utils.get_current_user)):
    db = get_db()
    db.execute("DELETE FROM spotify_tokens WHERE user_id = ?", (current_user["id"],))
    db.commit()
    db.close()
    return {"message": "Spotify disconnected"}


# ── Playlists ─────────────────────────────────────────────────────────────────

class CreatePlaylistRequest(BaseModel):
    name: str
    filenames: list[str]


@app.post("/playlists/create")
def create_playlist(body: CreatePlaylistRequest, current_user=Depends(auth_utils.get_current_user)):
    if not body.filenames:
        raise HTTPException(400, "No filenames provided")
    if not body.name.strip():
        raise HTTPException(400, "Playlist name required")

    db = get_db()
    token = sp.get_valid_token(db, current_user["id"])
    if not token:
        db.close()
        raise HTTPException(403, "Spotify account not connected")

    found_uris = []
    not_found = []

    for filename in body.filenames:
        query = sp.clean_filename(filename)
        if not query:
            not_found.append(filename)
            continue
        result = sp.search_track(token, query)
        if result:
            found_uris.append(result["uri"])
        else:
            not_found.append(filename)
        time.sleep(0.05)  # gentle rate limiting

    if not found_uris:
        db.close()
        raise HTTPException(404, "No matching tracks found on Spotify")

    try:
        spotify_user_id = sp.get_spotify_user_id(token)
        playlist = sp.create_playlist(token, spotify_user_id, body.name)
        sp.add_tracks_to_playlist(token, playlist["id"], found_uris)
    except Exception as e:
        db.close()
        raise HTTPException(500, f"Spotify API error: {str(e)}")

    db.execute(
        "INSERT INTO playlists (user_id, spotify_playlist_id, name, track_count, not_found_count) VALUES (?, ?, ?, ?, ?)",
        (current_user["id"], playlist["id"], body.name, len(found_uris), len(not_found)),
    )
    db.commit()
    db.close()

    return {
        "playlist_url": playlist["external_urls"]["spotify"],
        "playlist_id": playlist["id"],
        "found": len(found_uris),
        "not_found": len(not_found),
        "not_found_tracks": not_found,
    }


@app.get("/playlists")
def get_playlists(current_user=Depends(auth_utils.get_current_user)):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM playlists WHERE user_id = ? ORDER BY created_at DESC",
        (current_user["id"],),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]
