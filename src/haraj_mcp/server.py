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
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from haraj_mcp import tools


log = logging.getLogger("haraj_mcp.server")


# Tool-annotation presets. Every tool must declare all four hints as
# explicit booleans (OpenAI's directory rejects tools with missing or
# non-boolean hints). Values match each handler's actual behaviour.
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
# check_auth only reads the local .env file — no network, no open world.
READ_ONLY_LOCAL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
# notes(set_read=True) flips the read flag: additive, idempotent.
NOTES_MUTATION = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
# follow_user toggles follow/unfollow: not idempotent (calling twice
# returns to the original state).
FOLLOW_MUTATION = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)


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
    @mcp.tool(name="fetch_feed", annotations=READ_ONLY, description=(
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
        tag: Annotated[str, Field(description=(
            "Arabic category/tag name, e.g. 'حراج السيارات' (cars) or "
            "'حراج الأجهزة' (devices)."
        ))],
        city: Annotated[str | None, Field(description=(
            "Single Arabic region name to filter by, e.g. 'الشرقيه'."
        ))] = None,
        cities: Annotated[list[str] | None, Field(description=(
            "List of Arabic region names to filter by (multi-city)."
        ))] = None,
        page: Annotated[int, Field(description="Zero-based page index.")] = 0,
        limit: Annotated[int, Field(description=(
            "Number of posts to return (clamped to 1-100)."
        ))] = 21,
        before_update_date: Annotated[int | None, Field(description=(
            "Pagination cursor in Unix seconds — pass the last item's "
            "updateDate to get the next page."
        ))] = None,
        only_with_image: Annotated[bool, Field(description=(
            "Only return posts that have at least one image."
        ))] = True,
        only_with_video: Annotated[bool, Field(description=(
            "Only return posts that have a video."
        ))] = False,
        order_main_by_post_id: Annotated[bool, Field(description=(
            "Order the main feed by post id instead of update date."
        ))] = False,
        full: Annotated[bool, Field(description=(
            "Return full Post objects instead of compact summaries."
        ))] = False,
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
    @mcp.tool(name="promoted_posts", annotations=READ_ONLY, description=(
        "Fetch the promoted-post carousel for a tag. Required: tag. "
        "Optional: city. Returns {count, posts}."
    ))
    async def _promoted_posts(
        tag: Annotated[str, Field(description=(
            "Arabic tag name for the promoted carousel, e.g. 'حراج الأجهزة'."
        ))],
        city: Annotated[str | None, Field(description=(
            "Arabic region name to filter by."
        ))] = None,
        full: Annotated[bool, Field(description=(
            "Return full Post objects instead of compact summaries."
        ))] = False,
    ) -> dict:
        return await tools.promoted_posts(tag, city=city, full=full, auth_path=env_path)

    # ----- 3. related_tags -----
    @mcp.tool(name="related_tags", annotations=READ_ONLY, description=(
        "Cities-with-counts for a given tag — powers the city-filter chips on "
        "tag pages. Required: tag. Optional: city. Returns [{tag, count, city}]."
    ))
    async def _related_tags(
        tag: Annotated[str, Field(description=(
            "Arabic tag name to get city post-counts for, e.g. 'حراج السيارات'."
        ))],
        city: Annotated[str | None, Field(description=(
            "Optional Arabic region name to scope the counts to."
        ))] = None,
    ) -> dict:
        return await tools.related_tags(tag, city=city, auth_path=env_path)

    # ----- 4. is_following_tag -----
    @mcp.tool(name="is_following_tag", annotations=READ_ONLY, description=(
        "True/false whether the authenticated user follows `tag`."
    ))
    async def _is_following_tag(
        tag: Annotated[str, Field(description=(
            "Arabic tag name to check the authenticated user's follow status for."
        ))],
        city: Annotated[str | None, Field(description=(
            "Optional Arabic region name to scope the check."
        ))] = None,
    ) -> dict:
        return await tools.is_following_tag(tag, city=city, auth_path=env_path)

    # ----- 5. search -----
    @mcp.tool(name="search", annotations=READ_ONLY, description=(
        "Search haraj by keyword. Required: keyword. Optional: cities (list), city, "
        "tag, tags (list), page, limit, only_with_image (default true), "
        "only_with_video (default false), hide_show_rooms (default false), "
        "order_by_post_id (default false), during_date ('1days'|'3days'|'1week'|'1months'), "
        "near ('@lat,lon' e.g. '@26.4336,50.1116'), full (default false = compact). "
        "Returns {keyword, count, has_next_page, view_options, posts}."
    ))
    async def _search(
        keyword: Annotated[str, Field(description=(
            "Search keyword (Arabic or English), e.g. 'RTX 4090' or 'شاشة'."
        ))],
        cities: Annotated[list[str] | None, Field(description=(
            "List of Arabic region names to filter by."
        ))] = None,
        city: Annotated[str | None, Field(description=(
            "Single Arabic region name to filter by."
        ))] = None,
        tag: Annotated[str | None, Field(description=(
            "Restrict the search to a single Arabic tag."
        ))] = None,
        tags: Annotated[list[str] | None, Field(description=(
            "Restrict the search to a list of Arabic tags."
        ))] = None,
        page: Annotated[int, Field(description="Zero-based page index.")] = 0,
        limit: Annotated[int, Field(description=(
            "Number of posts to return (clamped to 1-100)."
        ))] = 21,
        only_with_image: Annotated[bool, Field(description=(
            "Only return posts that have at least one image."
        ))] = True,
        only_with_video: Annotated[bool, Field(description=(
            "Only return posts that have a video."
        ))] = False,
        hide_show_rooms: Annotated[bool, Field(description=(
            "If true, hides dealer posts (real-estate filter)."
        ))] = False,
        order_by_post_id: Annotated[bool, Field(description=(
            "Order results by post id instead of relevance/date."
        ))] = False,
        during_date: Annotated[str | None, Field(description=(
            "Time window: '1days', '3days', '1week', or '1months'."
        ))] = None,
        near: Annotated[str | None, Field(description=(
            "Geohash location filter like '@26.4336,50.1116'."
        ))] = None,
        full: Annotated[bool, Field(description=(
            "Return full Post objects instead of compact summaries."
        ))] = False,
    ) -> dict:
        return await tools.search(
            keyword=keyword, cities=cities, city=city, tag=tag, tags=tags,
            page=page, limit=limit, only_with_image=only_with_image,
            only_with_video=only_with_video, hide_show_rooms=hide_show_rooms,
            order_by_post_id=order_by_post_id, during_date=during_date, near=near,
            full=full, auth_path=env_path,
        )

    # ----- 6. get_post_details -----
    @mcp.tool(name="get_post_details", annotations=READ_ONLY, description=(
        "Fetch a post + 3 related groups (similar posts in the same tag/city, "
        "similar images, related offers). This is the canonical 'fetch by id' "
        "— there is no direct getById operation in the GraphQL API. "
        "Required: post_id. full (default true = full similarPosts response)."
    ))
    async def _get_post_details(
        post_id: Annotated[int, Field(description=(
            "Haraj post id, e.g. 185926519."
        ))],
        full: Annotated[bool, Field(description=(
            "Return the full similarPosts response instead of a summary."
        ))] = True,
    ) -> dict:
        return await tools.get_post_details(post_id, full=full, auth_path=env_path)

    # ----- 7. post_like_info -----
    @mcp.tool(name="post_like_info", annotations=READ_ONLY, description=(
        "{is_like, total, is_following} for a post. Required: post_id."
    ))
    async def _post_like_info(
        post_id: Annotated[int, Field(description="Haraj post id.")],
    ) -> dict:
        return await tools.post_like_info(post_id, auth_path=env_path)

    # ----- 8. comments -----
    @mcp.tool(name="comments", annotations=READ_ONLY, description=(
        "Comment list for a post. Required: post_id. Optional: page, "
        "oldest_first (default true)."
    ))
    async def _comments(
        post_id: Annotated[int, Field(description="Haraj post id.")],
        page: Annotated[int, Field(description="Zero-based page index.")] = 0,
        oldest_first: Annotated[bool, Field(description=(
            "Return oldest comments first (false = newest first)."
        ))] = True,
    ) -> dict:
        return await tools.comments(
            post_id, page=page, oldest_first=oldest_first, auth_path=env_path
        )

    # ----- 9. user -----
    @mcp.tool(name="user", annotations=READ_ONLY, description=(
        "Full user profile (rating, followers, location history, badges). "
        "Pass either username (URL-encoded Arabic works) or user_id. "
        "rating_summary_only (default false) returns just the rating block."
    ))
    async def _user(
        username: Annotated[str | None, Field(description=(
            "Haraj username (URL-encoded Arabic is accepted)."
        ))] = None,
        user_id: Annotated[int | None, Field(description=(
            "Numeric Haraj user id (alternative to username)."
        ))] = None,
        rating_summary_only: Annotated[bool, Field(description=(
            "Return only the rating block instead of the full profile."
        ))] = False,
    ) -> dict:
        return await tools.user(
            username=username, user_id=user_id,
            rating_summary_only=rating_summary_only, auth_path=env_path,
        )

    # ----- 10. is_following_user -----
    @mcp.tool(name="is_following_user", annotations=READ_ONLY, description=(
        "True/false whether the authenticated user follows `username`."
    ))
    async def _is_following_user(
        username: Annotated[str, Field(description="Haraj username to check.")],
    ) -> dict:
        return await tools.is_following_user(username, auth_path=env_path)

    # ----- 11. notes -----
    @mcp.tool(name="notes", annotations=NOTES_MUTATION, description=(
        "User notifications (the bell icon). set_read (default false) marks "
        "them as read on the server."
    ))
    async def _notes(
        set_read: Annotated[bool, Field(description=(
            "Mark the notifications as read on the server."
        ))] = False,
    ) -> dict:
        return await tools.notes(set_read=set_read, auth_path=env_path)

    # ----- 12. sellers_list -----
    @mcp.tool(name="sellers_list", annotations=READ_ONLY, description=(
        "Sellers for a tag (used by real-estate / business / investment pages). "
        "Required: tags (list of Arabic tag names)."
    ))
    async def _sellers_list(
        tags: Annotated[list[str], Field(description=(
            "List of Arabic tag names (real-estate/business/investment pages)."
        ))],
        page: Annotated[int, Field(description="Zero-based page index.")] = 0,
    ) -> dict:
        return await tools.sellers_list(tags, page=page, auth_path=env_path)

    # ----- 13. locker_shipment_offer -----
    @mcp.tool(name="locker_shipment_offer", annotations=READ_ONLY, description=(
        "{offerId, isEligible, price} for a post's Locker shipping option. "
        "Required: post_id."
    ))
    async def _locker_shipment_offer(
        post_id: Annotated[int, Field(description="Haraj post id.")],
    ) -> dict:
        return await tools.locker_shipment_offer(post_id, auth_path=env_path)

    # ----- 14. post_contact -----
    @mcp.tool(name="post_contact", annotations=READ_ONLY, description=(
        "{contactText, contactMobile, shouldEnableWhatsApp} for a post. "
        "Required: post_id."
    ))
    async def _post_contact(
        post_id: Annotated[int, Field(description="Haraj post id.")],
    ) -> dict:
        return await tools.post_contact(post_id, auth_path=env_path)

    # ----- 15. follow_user -----
    @mcp.tool(name="follow_user", annotations=FOLLOW_MUTATION, description=(
        "Follow (or unfollow) a user. Required: username. Returns the new "
        "is_following state."
    ))
    async def _follow_user(
        username: Annotated[str, Field(description=(
            "Haraj username to follow/unfollow."
        ))],
    ) -> dict:
        return await tools.follow_user(username, auth_path=env_path)

    # ----- 16. search_suggest -----
    @mcp.tool(name="search_suggest", annotations=READ_ONLY, description=(
        "Live search-box autocomplete. Returns the top 10 suggestions for a "
        "typed prefix. Required: prefix (e.g. 'شاشة'). Optional: tag."
    ))
    async def _search_suggest(
        prefix: Annotated[str, Field(description=(
            "Text typed in the search box, e.g. 'شاشة'."
        ))],
        tag: Annotated[str | None, Field(description=(
            "Optional Arabic tag to scope the suggestions."
        ))] = None,
    ) -> dict:
        return await tools.search_suggest(prefix, tag=tag, auth_path=env_path)

    # ----- 17. trending_keywords -----
    @mcp.tool(name="trending_keywords", annotations=READ_ONLY, description=(
        "Top trending search terms over the last N days. "
        "range_in_days (default 7). Returns [{keyword, score}]."
    ))
    async def _trending_keywords(
        range_in_days: Annotated[int, Field(description=(
            "Look-back window in days (default 7)."
        ))] = 7,
    ) -> dict:
        return await tools.trending_keywords(range_in_days=range_in_days, auth_path=env_path)

    # ----- 18. outgoing_buy_requests -----
    @mcp.tool(name="outgoing_buy_requests", annotations=READ_ONLY, description=(
        "'Buy with confidence' (وساطة) escrow requests the user has placed. "
        "Optional: page (default 0)."
    ))
    async def _outgoing_buy_requests(
        page: Annotated[int, Field(description="Zero-based page index.")] = 0,
    ) -> dict:
        return await tools.outgoing_buy_requests(page=page, auth_path=env_path)

    # ----- 19. user_mention_suggestions -----
    @mcp.tool(name="user_mention_suggestions", annotations=READ_ONLY, description=(
        "Recent @-mention candidates for the comment / DM composer. "
        "Returns [{userId, username, handler}]."
    ))
    async def _user_mention_suggestions() -> dict:
        return await tools.user_mention_suggestions(auth_path=env_path)

    # ----- 20. live_streams -----
    @mcp.tool(name="live_streams", annotations=READ_ONLY, description=(
        "Currently-open haraj live shopping streams. Non-GraphQL REST endpoint. "
        "Returns [{id, title, cover_url, streamer, num_messages, num_viewers, started_at}]. "
        "limit (default 40; the server caps it)."
    ))
    async def _live_streams(
        limit: Annotated[int, Field(description=(
            "Maximum number of streams to return (the server caps it)."
        ))] = 40,
    ) -> dict:
        return await tools.live_streams(limit=limit, auth_path=env_path)

    # ----- 21. check_auth -----
    @mcp.tool(name="check_auth", annotations=READ_ONLY_LOCAL, description=(
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