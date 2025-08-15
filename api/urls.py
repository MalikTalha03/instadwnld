# api/urls.py
from django.urls import path
from .views import resolve_instagram, redirect_instagram, download_instagram

urlpatterns = [
    path("resolve/", resolve_instagram, name="resolve_instagram"),   # Option A
    path("redirect/", redirect_instagram, name="redirect_instagram"),# Option B
    path("download/", download_instagram, name="download_instagram"),
]
