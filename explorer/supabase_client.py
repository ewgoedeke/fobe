"""Shared Supabase client for the explorer server."""

import os
from functools import lru_cache

from supabase import create_client, Client


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Return a cached Supabase client instance."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SECRET_KEY"]
    return create_client(url, key)


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
