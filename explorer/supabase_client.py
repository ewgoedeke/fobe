"""Shared Supabase client for the explorer server."""

import os
import threading
from functools import lru_cache

from supabase import create_client, Client

_client: Client | None = None
_lock = threading.Lock()


def get_supabase() -> Client:
    """Return a cached Supabase client instance."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                url = os.environ["SUPABASE_URL"]
                key = os.environ["SUPABASE_SECRET_KEY"]
                _client = create_client(url, key)
    return _client


def reset_supabase() -> Client:
    """Force-create a new Supabase client (e.g. after connection errors)."""
    global _client
    with _lock:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SECRET_KEY"]
        _client = create_client(url, key)
    return _client


@lru_cache(maxsize=512)
def resolve_doc_uuid(slug: str) -> str | None:
    """Look up the Supabase UUID for a document slug. Cached."""
    resp = get_supabase().table("documents").select("id").eq("slug", slug).single().execute()
    return resp.data["id"] if resp.data else None


@lru_cache(maxsize=512)
def resolve_doc_slug(uuid: str) -> str | None:
    """Look up the slug for a document UUID. Cached."""
    resp = get_supabase().table("documents").select("slug").eq("id", uuid).single().execute()
    return resp.data["slug"] if resp.data else None
