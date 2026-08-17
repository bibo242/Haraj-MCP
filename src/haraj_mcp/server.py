"""MCP server for haraj.com.sa.

Exposes 21 tools to any MCP-aware agent (Claude Desktop, Cursor, opencode,
Zed, etc.). Every tool mirrors a real haraj.com.sa operation captured
from a live browser session — no hallucinated filters.

Transport: stdio (JSON-RPC over stdin/stdout).

Run via `python -m haraj_mcp` or the `haraj-mcp` console script.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from haraj_mcp import tools


log = logging.getLogger("haraj_mcp.server")


SERVER_INSTRUCTIONS = """\
haraj.com.sa Saudi marketplace MCP server.

Tools mirror the actual operations the live site exposes (captured
2026-08-17). Every argument matches what the live front end sends in
its GraphQL calls — no hallucinated filters.

Core discovery:
  - trending_keywords(range_in_days)   top searched terms
  - search_suggest(prefix)            live autocomplete for the search box
  - related_tags(tag)                  cities with post counts for a tag
  - live_streams()                     currently-open live shopping streams

Feed / search:
  - fetch_feed(tag, city?, page?, before_update_date?, limit?)
        tag-based feed (homepage + category pages). Paginate with the
        last item's updateDate as before_update_date.
  - search(keyword, cities?, city?, tag?, tags?, during_date?, near?, ...)
        during_date accepts '1days' | '3days' | '1week' | '1months'.
        near is a geohash '@lat,lon' (e.g. '@26.4336,50.1116').
  - promoted_posts(tag)                fixed-length promoted carousel
  - sellers_list(tags)                 sellers per tag (real estate etc.)

Post detail:
  - get_post_details(post_id)          via similarPosts (canonical "fetch by id")
  - post_like_info(post_id)            {is_like, total, is_following}
  - comments(post_id)                  comment list
  - post_contact(post_id)              {contactText, contactMobile, whatsapp}
  - locker_shipment_offer(post_id)     {offerId, isEligible, price}

User:
  - user(username? | user_id?)         full profile
  - is_following_user(username)        bool
  - follow_user(username)              mutation: toggles follow
  - user_mention_suggestions()         for @-mentions

Account:
  - notes(set_read?)                   notifications (the bell)
  - outgoing_buy_requests(page?)       escrow history
  - is_following_tag(tag)              bool
  - check_auth()                       verify .env credentials
"""


def build_server() -> FastMCP:
    mcp = FastMCP(
        name="haraj",
        instructions=SERVER_INSTRUCTIONS,
    )
    env_path_str = os.environ.get("HARAJ_MCP_ENV")
    env_path = Path(env_path_str) if env_path_str else None

    # ----- 1. fetch_feed -----
    @mcp.tool(name="fetch_feed", description=(
        "Fetch the post feed for a tag (the homepage + category pages). "
        "Required: tag (Arabic category name like 'حراج السيارات' or 'حراج الأجهزة'). "
        "Optional: city (Arabic region like 'الشرقيه'), cities (list of regions), "
        "page (default 0), limit (default 21), before_update_date (Unix seconds cursor — "
        "pass the last item's updateDate to get the next page), only_with_image "
        "(default true), only_with_video (default false), order_main_by_post_id "
        "(default false), full (return full Post objects, default false = compact). "
        "Returns {count, has_next_page, view_options, posts}."
    ))
    async def _fetch_feed(
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
    ) -> dict:
        return await tools.fetch_feed(
            tag=tag, city=city, cities=cities, page=page, limit=limit,
            before_update_date=before_update_date,
            only_with_image=only_with_image,
            only_with_video=only_with_video,
            order_main_by_post_id=order_main_by_post_id,
            full=full, auth_path=env_path,
        )

    # ----- 2. promoted_posts -----
    @mcp.tool(name="promoted_posts", description=(
        "Fetch the promoted-post carousel for a tag. Required: tag. "
        "Optional: city. Returns {count, posts}."
    ))
    async def _promoted_posts(
        tag: str,
        city: str | None = None,
        full: bool = False,
    ) -> dict:
        return await tools.promoted_posts(tag, city=city, full=full, auth_path=env_path)

    # ----- 3. related_tags -----
    @mcp.tool(name="related_tags", description=(
        "Cities-with-counts for a given tag — powers the city-filter chips on "
        "tag pages. Required: tag. Optional: city. Returns [{tag, count, city}]."
    ))
    async def _related_tags(
        tag: str,
        city: str | None = None,
    ) -> dict:
        return await tools.related_tags(tag, city=city, auth_path=env_path)

    # ----- 4. is_following_tag -----
    @mcp.tool(name="is_following_tag", description=(
        "True/false whether the authenticated user follows `tag`."
    ))
    async def _is_following_tag(
        tag: str,
        city: str | None = None,
    ) -> dict:
        return await tools.is_following_tag(tag, city=city, auth_path=env_path)

    # ----- 5. search -----
    @mcp.tool(name="search", description=(
        "Search haraj by keyword. Required: keyword. Optional: cities (list), city, "
        "tag, tags (list), page, limit, only_with_image (default true), "
        "only_with_video (default false), hide_show_rooms (default false), "
        "order_by_post_id (default false), during_date ('1days'|'3days'|'1week'|'1months'), "
        "near ('@lat,lon' e.g. '@26.4336,50.1116'), full (default false = compact). "
        "Returns {keyword, count, has_next_page, view_options, posts}."
    ))
    async def _search(
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
    ) -> dict:
        return await tools.search(
            keyword=keyword, cities=cities, city=city, tag=tag, tags=tags,
            page=page, limit=limit, only_with_image=only_with_image,
            only_with_video=only_with_video, hide_show_rooms=hide_show_rooms,
            order_by_post_id=order_by_post_id, during_date=during_date, near=near,
            full=full, auth_path=env_path,
        )

    # ----- 6. get_post_details -----
    @mcp.tool(name="get_post_details", description=(
        "Fetch a post + 3 related groups (similar posts in the same tag/city, "
        "similar images, related offers). This is the canonical 'fetch by id' "
        "— there is no direct getById operation in the GraphQL API. "
        "Required: post_id. full (default true = full similarPosts response)."
    ))
    async def _get_post_details(
        post_id: int,
        full: bool = True,
    ) -> dict:
        return await tools.get_post_details(post_id, full=full, auth_path=env_path)

    # ----- 7. post_like_info -----
    @mcp.tool(name="post_like_info", description=(
        "{is_like, total, is_following} for a post. Required: post_id."
    ))
    async def _post_like_info(post_id: int) -> dict:
        return await tools.post_like_info(post_id, auth_path=env_path)

    # ----- 8. comments -----
    @mcp.tool(name="comments", description=(
        "Comment list for a post. Required: post_id. Optional: page, "
        "oldest_first (default true)."
    ))
    async def _comments(
        post_id: int,
        page: int = 0,
        oldest_first: bool = True,
    ) -> dict:
        return await tools.comments(
            post_id, page=page, oldest_first=oldest_first, auth_path=env_path
        )

    # ----- 9. user -----
    @mcp.tool(name="user", description=(
        "Full user profile (rating, followers, location history, badges). "
        "Pass either username (URL-encoded Arabic works) or user_id. "
        "rating_summary_only (default false) returns just the rating block."
    ))
    async def _user(
        username: str | None = None,
        user_id: int | None = None,
        rating_summary_only: bool = False,
    ) -> dict:
        return await tools.user(
            username=username, user_id=user_id,
            rating_summary_only=rating_summary_only, auth_path=env_path,
        )

    # ----- 10. is_following_user -----
    @mcp.tool(name="is_following_user", description=(
        "True/false whether the authenticated user follows `username`."
    ))
    async def _is_following_user(username: str) -> dict:
        return await tools.is_following_user(username, auth_path=env_path)

    # ----- 11. notes -----
    @mcp.tool(name="notes", description=(
        "User notifications (the bell icon). set_read (default false) marks "
        "them as read on the server."
    ))
    async def _notes(set_read: bool = False) -> dict:
        return await tools.notes(set_read=set_read, auth_path=env_path)

    # ----- 12. sellers_list -----
    @mcp.tool(name="sellers_list", description=(
        "Sellers for a tag (used by real-estate / business / investment pages). "
        "Required: tags (list of Arabic tag names)."
    ))
    async def _sellers_list(
        tags: list[str],
        page: int = 0,
    ) -> dict:
        return await tools.sellers_list(tags, page=page, auth_path=env_path)

    # ----- 13. locker_shipment_offer -----
    @mcp.tool(name="locker_shipment_offer", description=(
        "{offerId, isEligible, price} for a post's Locker shipping option. "
        "Required: post_id."
    ))
    async def _locker_shipment_offer(post_id: int) -> dict:
        return await tools.locker_shipment_offer(post_id, auth_path=env_path)

    # ----- 14. post_contact -----
    @mcp.tool(name="post_contact", description=(
        "{contactText, contactMobile, shouldEnableWhatsApp} for a post. "
        "Required: post_id."
    ))
    async def _post_contact(post_id: int) -> dict:
        return await tools.post_contact(post_id, auth_path=env_path)

    # ----- 15. follow_user -----
    @mcp.tool(name="follow_user", description=(
        "Follow (or unfollow) a user. Required: username. Returns the new "
        "is_following state."
    ))
    async def _follow_user(username: str) -> dict:
        return await tools.follow_user(username, auth_path=env_path)

    # ----- 16. search_suggest -----
    @mcp.tool(name="search_suggest", description=(
        "Live search-box autocomplete. Returns the top 10 suggestions for a "
        "typed prefix. Required: prefix (e.g. 'شاشة'). Optional: tag."
    ))
    async def _search_suggest(
        prefix: str,
        tag: str | None = None,
    ) -> dict:
        return await tools.search_suggest(prefix, tag=tag, auth_path=env_path)

    # ----- 17. trending_keywords -----
    @mcp.tool(name="trending_keywords", description=(
        "Top trending search terms over the last N days. "
        "range_in_days (default 7). Returns [{keyword, score}]."
    ))
    async def _trending_keywords(range_in_days: int = 7) -> dict:
        return await tools.trending_keywords(range_in_days=range_in_days, auth_path=env_path)

    # ----- 18. outgoing_buy_requests -----
    @mcp.tool(name="outgoing_buy_requests", description=(
        "'Buy with confidence' (وساطة) escrow requests the user has placed. "
        "Optional: page (default 0)."
    ))
    async def _outgoing_buy_requests(page: int = 0) -> dict:
        return await tools.outgoing_buy_requests(page=page, auth_path=env_path)

    # ----- 19. user_mention_suggestions -----
    @mcp.tool(name="user_mention_suggestions", description=(
        "Recent @-mention candidates for the comment / DM composer. "
        "Returns [{userId, username, handler}]."
    ))
    async def _user_mention_suggestions() -> dict:
        return await tools.user_mention_suggestions(auth_path=env_path)

    # ----- 20. live_streams -----
    @mcp.tool(name="live_streams", description=(
        "Currently-open haraj live shopping streams. Non-GraphQL REST endpoint. "
        "Returns [{id, title, cover_url, streamer, num_messages, num_viewers, started_at}]. "
        "limit (default 40; the server caps it)."
    ))
    async def _live_streams(limit: int = 40) -> dict:
        return await tools.live_streams(limit=limit, auth_path=env_path)

    # ----- 21. check_auth -----
    @mcp.tool(name="check_auth", description=(
        "Verify the JWT and lastRequestId in .env are still valid. "
        "Returns {ok, expires_at, seconds_remaining, user_id} or "
        "{ok: false, error} if the JWT is missing or expired."
    ))
    async def _check_auth() -> dict:
        return await tools.check_auth(auth_path=env_path)

    return mcp


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("HARAJ_MCP_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp = build_server()
    log.info("haraj-mcp starting (stdio transport, 21 tools)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()