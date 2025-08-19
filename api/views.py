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

import os
from typing import Dict, Any

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
def _yt_base_opts() -> Dict[str, Any]:
    """
    Build yt-dlp options that work on servers with cookies.
    """
    opts: Dict[str, Any] = {
        "quiet": True,
        "noplaylist": True,
        "format": "bv*+ba/b[ext=mp4]/b",   # prefer single-file MP4
        "user_agent": os.getenv("YTDLP_UA", DEFAULT_UA),
    }

    cookie_header = os.getenv("IG_COOKIE_HEADER", "").strip()

    # 🔐 fallback: hardcoded cookie string
    if not cookie_header:
        cookie_header = (
            'csrftoken=LmbmoQevmYNc6mcma_7Czh; '
            'datr=mXifaEzs4ZkHjp6Jnbgfo29f; '
            'ig_did=C1361653-6529-4B2B-8095-3EFF5882998D; '
            'wd=1867x625; '
            'mid=aJ94mgAEAAE-YtbkisGtqQwhZw2f; '
            'ig_nrcb=1; '
            'sessionid=54174011413%3A94NAzjEixQVCCw%3A1%3AAYc0qFV6aShr7jbE41M7Q5eMehILfLuqlflg4FevzA; '
            'ds_user_id=54174011413; '
            'ps_l=1; '
            'ps_n=1; '
            'rur="RVA\\05454174011413\\0541786997274:01fead3c94a99887a9734fd004faef27643e1caa563ead1d29996591457100c8a0d03ea6"'
        )

    if cookie_header:
        opts["http_headers"] = {
            "User-Agent": opts["user_agent"],
            "Cookie": cookie_header,
            "Referer": "https://www.instagram.com/",
            "Origin": "https://www.instagram.com",
        }

    return opts



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

    ydl_opts = _yt_base_opts()


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

    ydl_opts = _yt_base_opts()


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

