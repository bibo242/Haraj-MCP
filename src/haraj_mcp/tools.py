"""MCP tool implementations for the haraj server.

All tools wrap `haraj.client.HarajClient` methods, which in turn call
the *actual* haraj.com.sa operations captured from a real browser
session. No hallucinated filters — every variable matches what the
live site sends.

For each tool, the `full=True` opt-in flag returns the entire pydantic
`Post` object. Default is a compact summary.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from haraj.client import HarajClient, HarajError
from haraj.images import image_urls
from haraj.models import Post

from haraj_mcp.auth import AuthError, HarajAuth, jwt_status, load_auth_from_env

log = logging.getLogger("haraj_mcp.tools")


# -------------------------------------------------------------------------
# Compact serializer
# -------------------------------------------------------------------------

def _compact(post: Post) -> dict:
    images = image_urls(post, max_n=1)
    return {
        "id": post.id,
        "title": post.title,
        "price_sar": post.price_sar,
        "price_display": post.price_display,
        "url": post.web_url,
        "city": post.city,
        "geo_city": post.geoCity,
        "post_date": post.postDate,
        "has_image": post.hasImage,
        "thumb_url": images[0] if images else None,
        "tags": list(post.tags or [])[:6],
        "has_price": post.price_sar is not None,
    }


def _full(post: Post) -> dict:
    return post.model_dump(mode="json", exclude_none=False)


# -------------------------------------------------------------------------
# Auth bootstrap
# -------------------------------------------------------------------------

def _auth_or_error(auth_path) -> tuple[HarajAuth | None, dict | None]:
    try:
        return load_auth_from_env(auth_path), None
    except AuthError as exc:
        return None, {"ok": False, "error": str(exc)}


def _client(auth: HarajAuth) -> HarajClient:
    return HarajClient(auth, max_pages=5, limit=21)


# -------------------------------------------------------------------------
# Tool implementations
# -------------------------------------------------------------------------

async def fetch_feed(
    tag: str,
    city: str | None = None,
    cities: list[str] | None = None,
    page: int = 0,
    limit: int = 21,
    before_update_date: int | None = None,
    only_with_image: bool = True,
    only_with_video: bool = False,
    order_main_by_post_id: bool = False,
    full: bool = False,
    auth_path: str | None = None,
) -> dict:
    """Fetch the post feed for a tag (e.g. 'حراج السيارات', 'أجهزة كمبيوتر').

    `before_update_date` is the cursor for pagination — pass the last
    item's `updateDate` to get the next batch.
    """
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        data = await client.fetch_feed(
            tag, city=city, cities=cities, page=page, limit=min(max(limit, 1), 100),
            before_update_date=before_update_date,
            only_with_image=only_with_image,
            only_with_video=only_with_video,
            order_main_by_post_id=order_main_by_post_id,
        )
    except HarajError as exc:
        return {"ok": False, "error": str(exc), "posts": []}
    posts_raw = (data.get("posts") or {}).get("items") or []
    view_options = (data.get("posts") or {}).get("viewOptions") or {}
    posts = [_full(Post.model_validate(p)) if full else _compact(Post.model_validate(p)) for p in posts_raw]
    return {
        "tag": tag,
        "count": len(posts),
        "page": page,
        "has_next_page": (data.get("posts") or {}).get("pageInfo", {}).get("hasNextPage", False),
        "view_options": view_options,
        "posts": posts,
    }


async def promoted_posts(
    tag: str,
    city: str | None = None,
    full: bool = False,
    auth_path: str | None = None,
) -> dict:
    """Fetch the promoted-post carousel for a tag (e.g. 'حراج الأجهزة')."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        posts = await client.promoted_posts(tag, city=city)
    except HarajError as exc:
        return {"ok": False, "error": str(exc), "posts": []}
    return {
        "tag": tag,
        "count": len(posts),
        "posts": [_full(p) if full else _compact(p) for p in posts],
    }


async def related_tags(
    tag: str,
    city: str | None = None,
    auth_path: str | None = None,
) -> dict:
    """Cities-with-counts for a given tag. Example: tag='حراج السيارات' returns
    [{tag, count, city}] sorted by count — powers the city-filter chips."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        cities = await client.related_tags(tag, city=city)
    except HarajError as exc:
        return {"ok": False, "error": str(exc), "cities": []}
    return {"tag": tag, "count": len(cities), "cities": cities}


async def is_following_tag(
    tag: str,
    city: str | None = None,
    auth_path: str | None = None,
) -> dict:
    """True/false whether the authenticated user follows `tag`."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        result = await client.is_following_tag(tag, city=city)
    except HarajError as exc:
        return {"ok": False, "error": str(exc)}
    return {"tag": tag, "is_following": result}


async def search(
    keyword: str,
    cities: list[str] | None = None,
    city: str | None = None,
    tag: str | None = None,
    tags: list[str] | None = None,
    page: int = 0,
    limit: int = 21,
    only_with_image: bool = True,
    only_with_video: bool = False,
    hide_show_rooms: bool = False,
    order_by_post_id: bool = False,
    during_date: str | None = None,
    near: str | None = None,
    full: bool = False,
    auth_path: str | None = None,
) -> dict:
    """Search haraj by keyword — the real `search` operation, no hallucinated
    filters. `during_date` accepts '1days' | '3days' | '1week' | '1months'.
    `near` is a geohash string like '@26.4336,50.1116'."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        result = await client.search(
            keyword,
            cities=cities, city=city, tag=tag, tags=tags,
            page=page, limit=min(max(limit, 1), 100),
            only_with_image=only_with_image,
            only_with_video=only_with_video,
            hide_show_rooms=hide_show_rooms,
            order_by_post_id=order_by_post_id,
            during_date=during_date, near=near,
        )
    except HarajError as exc:
        return {"ok": False, "error": str(exc), "posts": []}
    posts = [_full(p) if full else _compact(p) for p in result.items]
    return {
        "keyword": keyword,
        "count": len(posts),
        "page": page,
        "has_next_page": result.pageInfo.hasNextPage,
        "view_options": result.viewOptions.model_dump(),
        "posts": posts,
    }


async def get_post_details(
    post_id: int,
    full: bool = True,
    auth_path: str | None = None,
) -> dict:
    """Fetch a post + 3 related groups via the real similarPosts endpoint.

    This is the canonical "fetch post by id" — there is no direct getById
    operation in the GraphQL API.
    """
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        data = await client.get_post_details(post_id)
    except HarajError as exc:
        return {"ok": False, "error": str(exc)}
    if not data:
        return {"ok": False, "error": f"post {post_id} not found", "id": post_id}
    return {"ok": True, "post": data}


async def post_like_info(
    post_id: int,
    auth_path: str | None = None,
) -> dict:
    """{is_like, total, is_following} for a post."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        return await client.post_like_info(post_id)
    except HarajError as exc:
        return {"ok": False, "error": str(exc)}


async def comments(
    post_id: int,
    page: int = 0,
    oldest_first: bool = True,
    auth_path: str | None = None,
) -> dict:
    """Comment list for a post."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        return await client.comments(post_id, page=page, oldest_first=oldest_first)
    except HarajError as exc:
        return {"ok": False, "error": str(exc)}


async def user(
    username: str | None = None,
    user_id: int | None = None,
    rating_summary_only: bool = False,
    auth_path: str | None = None,
) -> dict:
    """Full user profile: rating, followers, location history, badges.

    Pass either `username` (URL-encoded Arabic works) or `user_id`.
    """
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        return await client.user(
            username=username, id=user_id, rating_summary_only=rating_summary_only
        )
    except HarajError as exc:
        return {"ok": False, "error": str(exc)}


async def is_following_user(
    username: str,
    auth_path: str | None = None,
) -> dict:
    """True/false whether the authenticated user follows `username`."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        result = await client.is_following_user(username)
    except HarajError as exc:
        return {"ok": False, "error": str(exc)}
    return {"username": username, "is_following": result}


async def notes(
    set_read: bool = False,
    auth_path: str | None = None,
) -> dict:
    """User notifications (the bell icon)."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        return await client.notes(set_read=set_read)
    except HarajError as exc:
        return {"ok": False, "error": str(exc)}


async def sellers_list(
    tags: list[str],
    page: int = 0,
    auth_path: str | None = None,
) -> dict:
    """Sellers for a tag (used by real-estate, business, investment pages)."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        return await client.sellers_list(tags, page=page)
    except HarajError as exc:
        return {"ok": False, "error": str(exc)}


async def locker_shipment_offer(
    post_id: int,
    auth_path: str | None = None,
) -> dict:
    """{offerId, isEligible, price} for a post's Locker shipping option."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        return await client.locker_shipment_offer(post_id)
    except HarajError as exc:
        return {"ok": False, "error": str(exc)}


async def post_contact(
    post_id: int,
    auth_path: str | None = None,
) -> dict:
    """Contact info (text, mobile, WhatsApp-enabled) for a post."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        return await client.post_contact(post_id)
    except HarajError as exc:
        return {"ok": False, "error": str(exc)}


async def follow_user(
    username: str,
    auth_path: str | None = None,
) -> dict:
    """Follow (or unfollow) a user. Returns the new is_following state."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        result = await client.follow_user(username)
    except HarajError as exc:
        return {"ok": False, "error": str(exc)}
    return {"username": username, "is_following": result}


async def search_suggest(
    prefix: str,
    tag: str | None = None,
    auth_path: str | None = None,
) -> dict:
    """Live search-box autocomplete. Returns the top 10 suggestions for a
    typed prefix (e.g. prefix='شاشة' → ['شاشة', 'شاشة قيمنق', 'شاشة سامسونج', ...])."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        keywords = await client.search_suggest(prefix, tag=tag)
    except HarajError as exc:
        return {"ok": False, "error": str(exc), "keywords": []}
    return {"prefix": prefix, "count": len(keywords), "keywords": keywords}


async def trending_keywords(
    range_in_days: int = 7,
    auth_path: str | None = None,
) -> dict:
    """Top trending search terms over the last N days. Returns [{keyword, score}]."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        items = await client.trending_keywords(range_in_days=range_in_days)
    except HarajError as exc:
        return {"ok": False, "error": str(exc), "trending": []}
    return {"range_in_days": range_in_days, "count": len(items), "trending": items}


async def outgoing_buy_requests(
    page: int = 0,
    auth_path: str | None = None,
) -> dict:
    """'Buy with confidence' escrow requests the user has placed."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        return await client.outgoing_buy_requests(page=page)
    except HarajError as exc:
        return {"ok": False, "error": str(exc)}


async def user_mention_suggestions(
    auth_path: str | None = None,
) -> dict:
    """Recent @-mention candidates for the comment / DM composer."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        items = await client.user_mention_suggestions()
    except HarajError as exc:
        return {"ok": False, "error": str(exc), "suggestions": []}
    return {"count": len(items), "suggestions": items}


async def live_streams(
    limit: int = 40,
    auth_path: str | None = None,
) -> dict:
    """Currently-open haraj live shopping streams. Non-GraphQL REST endpoint
    (livestream.haraj.com.sa/streams)."""
    auth, err = _auth_or_error(auth_path)
    if err:
        return err
    client = _client(auth)
    try:
        resp = await client.live_streams(limit=limit)
    except HarajError as exc:
        return {"ok": False, "error": str(exc), "streams": []}
    streams = resp.data.streams if resp.data else []
    return {
        "ok": resp.ok,
        "count": len(streams),
        "streams": [s.model_dump(mode="json") for s in streams],
        "page_info": resp.data.page_info.model_dump() if resp.data else {},
    }


async def check_auth(auth_path: str | None = None) -> dict:
    """Verify the JWT and lastRequestId in .env are still valid (not expired)."""
    try:
        auth = load_auth_from_env(auth_path)
    except AuthError as exc:
        return {"ok": False, "error": str(exc)}
    status = jwt_status(auth.jwt)
    if not status.get("ok"):
        return status
    status["last_request_id_preview"] = auth.last_request_id[:20]
    return status


# Tool list — single source of truth for the server.
TOOL_NAMES = [
    "fetch_feed",
    "promoted_posts",
    "related_tags",
    "is_following_tag",
    "search",
    "get_post_details",
    "post_like_info",
    "comments",
    "user",
    "is_following_user",
    "notes",
    "sellers_list",
    "locker_shipment_offer",
    "post_contact",
    "follow_user",
    "search_suggest",
    "trending_keywords",
    "outgoing_buy_requests",
    "user_mention_suggestions",
    "live_streams",
    "check_auth",
]