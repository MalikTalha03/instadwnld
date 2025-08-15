# api/views.py
import json
import re
from django.http import (
    JsonResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
    HttpResponseRedirect,
)
from yt_dlp import YoutubeDL

import os
import uuid
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

# Accept any Instagram URL (post/reel/story highlight URLs vary)
INSTAGRAM_REGEX = re.compile(r"^https?://(www\.)?instagram\.com/.*", re.IGNORECASE)


def _pick_best_progressive_mp4(info: dict) -> str | None:
    """
    Prefer a progressive MP4 (video+audio in one file).
    Fallbacks: any AV single file; lastly, info['url'] (may be HLS/DASH).
    """
    formats = info.get("formats") or []

    # Progressive mp4s: both audio and video present
    progressive = [
        f for f in formats
        if (f.get("ext") == "mp4"
            and f.get("vcodec") != "none"
            and f.get("acodec") != "none"
            and f.get("url"))
    ]
    progressive.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0), reverse=True)
    if progressive:
        return progressive[0]["url"]

    # Any AV single-file
    av = [
        f for f in formats
        if (f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("url"))
    ]
    av.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0), reverse=True)
    if av:
        return av[0]["url"]

    # Last resort: top-level url (may be playlist)
    return info.get("url")


# ---------- OPTION A: Return direct URL in JSON ----------
@csrf_exempt
def resolve_instagram(request):
    """
    POST JSON: {"url": "<instagram url>"}
    Returns: {"status":"ok","direct_url": "...", ...}
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"], "Use POST with JSON: {\"url\": \"...\"}")

    try:
        data = json.loads(request.body.decode("utf-8"))
        ig_url = (data.get("url") or "").strip()
    except Exception:
        return HttpResponseBadRequest("Invalid JSON payload")

    if not ig_url or not INSTAGRAM_REGEX.match(ig_url):
        return HttpResponseBadRequest("Provide a valid Instagram URL")

    ydl_opts = {
        "quiet": True,
        "noplaylist": True,
        # Prefer a single-file mp4; otherwise, yt-dlp may give HLS/DASH
        "format": "bv*+ba/b[ext=mp4]/b",
        # --- If you need cookies for private/age-gated posts, uncomment one:
        # "cookiesfrombrowser": ("chrome",),  # or ("firefox",)
        # "cookiefile": "/path/to/cookies.txt",
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(ig_url, download=False)

        direct_url = _pick_best_progressive_mp4(info)
        if not direct_url:
            return JsonResponse({"status": "error", "message": "Could not resolve a direct URL"}, status=400)

        return JsonResponse({
            "status": "ok",
            "direct_url": direct_url,
            "title": info.get("title"),
            "duration": info.get("duration"),
            "note": "This link may expire soon; download immediately."
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


# ---------- OPTION B: 302 Redirect to direct URL ----------
@csrf_exempt
def redirect_instagram(request):
    """
    POST JSON: {"url": "<instagram url>"}
    Responds with HTTP 302 redirect to the direct media URL (no JSON).
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        data = json.loads(request.body.decode("utf-8"))
        ig_url = (data.get("url") or "").strip()
    except Exception:
        return HttpResponseBadRequest("Invalid JSON payload")

    if not ig_url or not INSTAGRAM_REGEX.match(ig_url):
        return HttpResponseBadRequest("Provide a valid Instagram URL")

    ydl_opts = {
        "quiet": True,
        "noplaylist": True,
        "format": "bv*+ba/b[ext=mp4]/b",
        # "cookiesfrombrowser": ("chrome",),  # if needed
        # "cookiefile": "/path/to/cookies.txt",
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(ig_url, download=False)

        direct_url = _pick_best_progressive_mp4(info)
        if not direct_url:
            return HttpResponseBadRequest("Could not resolve a direct media URL")

        # Client will download directly from Instagram's CDN
        return HttpResponseRedirect(direct_url)  # 302
    except Exception as e:
        return HttpResponseBadRequest(str(e))




@csrf_exempt  # for a simple API; in prod, use proper CSRF/auth
def download_instagram(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"], "Use POST with JSON: {\"url\": \"...\"}")

    # Parse JSON
    try:
        data = json.loads(request.body.decode("utf-8"))
        url = (data.get("url") or "").strip()
    except Exception:
        return HttpResponseBadRequest("Invalid JSON payload")

    # Validate URL
    if not url or not INSTAGRAM_REGEX.match(url):
        return HttpResponseBadRequest("Provide a valid Instagram URL")

    # Prepare output folder
    out_dir = os.path.join(settings.MEDIA_ROOT, "videos")
    os.makedirs(out_dir, exist_ok=True)

    # Unique filename template for yt-dlp
    unique = str(uuid.uuid4())
    outtmpl = os.path.join(out_dir, f"{unique}.%(ext)s")

    # yt-dlp options
    ydl_opts = {
        "outtmpl": outtmpl,
        "format": "mp4/best",         # try mp4 first
        "noplaylist": True,
        "quiet": True,
        "merge_output_format": "mp4", # ensure mp4 container when needed
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Get the actual downloaded file path
            downloaded = ydl.prepare_filename(info)  # includes extension decided by yt-dlp

        # Build a public URL (dev: Django serves media; prod: serve via CDN/object storage)
        rel_path = os.path.relpath(downloaded, settings.MEDIA_ROOT).replace("\\", "/")
        file_url = settings.MEDIA_URL + rel_path
        absolute_url = request.build_absolute_uri(file_url)

        return JsonResponse({
            "status": "ok",
            "download_url": absolute_url,
            "filename": os.path.basename(downloaded),
        })

    except Exception as e:
        # Hide internals but keep message helpful
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
