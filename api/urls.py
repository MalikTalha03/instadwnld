# api/urls.py
from django.urls import path
from .views import resolve_instagram, redirect_instagram
from django.http import JsonResponse

def health(_): return JsonResponse({"ok": True})

urlpatterns = [
    path("resolve/", resolve_instagram, name="resolve_instagram"),   # Option A
    path("redirect/", redirect_instagram, name="redirect_instagram"),# Option B
    path("health/", health),
]
