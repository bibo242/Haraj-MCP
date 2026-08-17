"""Async client for the real haraj.com.sa GraphQL + REST endpoints.

All methods below are wrappers around the actual operations the live
haraj.com.sa front end uses (captured 2026-08-17). No hallucinated filters.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, AsyncIterator, Optional

import httpx

from haraj.auth import HarajAuth
from haraj.constants import (
    GRAPHQL_ENDPOINT,
    GRAPHQL_ORIGIN,
    GRAPHQL_REFERER,
    LIVESTREAM_ENDPOINT,
    SEC_CH_UA,
    SEC_CH_UA_FULL_VERSION_LIST,
    SEC_CH_UA_PLATFORM,
    SEC_CH_UA_PLATFORM_VERSION,
    USER_AGENT,
)
from haraj.models import (
    LivestreamResponse,
    Post,
    SearchResult,
)
from haraj.queries import (
    COMMENTS_QUERY,
    FOLLOW_USER_MUTATION,
    GET_LOCKER_SHIPMENT_OFFER_QUERY,
    GET_OUTGOING_BUY_REQUESTS_LIST_QUERY,
    GET_TRENDING_KEYWORDS_QUERY,
    GET_USER_MENTION_SUGGESTIONS_QUERY,
    IS_FOLLOWING_TAG_QUERY,
    IS_FOLLOWING_USER_QUERY,
    NOTES_QUERY,
    POST_CONTACT_QUERY,
    POST_LIKE_INFO_QUERY,
    POSTS_QUERY,
    PROMOTED_POSTS_QUERY,
    RELATED_TAGS_QUERY,
    SEARCH_QUERY,
    SELLERS_LIST_QUERY,
    SEARCH_SUGGEST_QUERY,
    SIMILAR_POSTS_QUERY,
    SUBMIT_GEO_LOCATION_MUTATION,
    USER_QUERY,
    USER_RATING_SUMMARY_QUERY,
)

log = logging.getLogger("haraj.client")


class HarajError(RuntimeError):
    """Raised on transport or schema errors."""


class HarajClient:
    def __init__(
        self,
        auth: HarajAuth,
        *,
        max_pages: int = 5,
        limit: int = 21,
        min_interval: float = 1.5,
        max_interval: float = 2.5,
        max_retries: int = 4,
        timeout: float = 30.0,
    ) -> None:
        self._auth = auth
        self._max_pages = max_pages
        self._limit = limit
        self._min_interval = min_interval
        self._max_interval = max_interval
        self._max_retries = max_retries
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "HarajClient":
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            headers=self._base_headers(),
            http2=False,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _base_headers(self) -> dict[str, str]:
        return {
            "authorization": self._auth.authorization_header(),
            "lastRequestId": self._auth.last_request_id,
            "trackId": "",
            "Content-Type": "application/json",
            "Origin": GRAPHQL_ORIGIN,
            "Referer": GRAPHQL_REFERER,
            "User-Agent": USER_AGENT,
            "sec-ch-ua": SEC_CH_UA,
            "sec-ch-ua-platform": SEC_CH_UA_PLATFORM,
            "sec-ch-ua-platform-version": SEC_CH_UA_PLATFORM_VERSION,
            "sec-ch-ua-full-version-list": SEC_CH_UA_FULL_VERSION_LIST,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-arch": '"x86"',
            "sec-ch-ua-model": '""',
            "Accept": "*/*",
            "Sec-GPC": "1",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

    # ---- low-level dispatcher ----

    async def _query(self, query_name: str, query: str, variables: dict) -> Any:
        """POST a GraphQL operation. Returns the raw `data` field."""
        if self._client is None:
            raise HarajError("HarajClient must be used as an async context manager.")
        url = GRAPHQL_ENDPOINT.format(queryName=query_name)
        body = {"query": query, "variables": variables}

        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await self._client.post(url, json=body)
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise HarajError(f"HTTP error after {attempt} attempts: {exc}") from exc
                await self._sleep_backoff(attempt)
                continue

            if resp.status_code != 200:
                if resp.status_code in (401, 403):
                    raise HarajError(
                        f"Auth rejected ({resp.status_code}). JWT may be expired — "
                        f"re-login to haraj.com.sa and refresh HARAJ_JWT."
                    )
                if resp.status_code == 429 and attempt < self._max_retries:
                    await self._sleep_backoff(attempt, base=5.0)
                    continue
                if attempt < self._max_retries and resp.status_code >= 500:
                    await self._sleep_backoff(attempt)
                    continue
                raise HarajError(f"GraphQL HTTP {resp.status_code}: {resp.text[:300]}")

            data = resp.json()
            if "errors" in data and data["errors"]:
                raise HarajError(f"GraphQL errors: {data['errors']}")
            return data.get("data") or {}

    async def _jitter(self) -> None:
        delay = random.uniform(self._min_interval, self._max_interval)
        await asyncio.sleep(delay)

    async def _sleep_backoff(self, attempt: int, base: float = 2.0) -> None:
        delay = base * (2 ** (attempt - 1)) + random.uniform(0, 1.0)
        log.warning("Retrying after %.1fs (attempt %d)", delay, attempt)
        await asyncio.sleep(delay)

    # =========================================================================
    # Tool methods — one per real haraj operation. Argument lists mirror
    # what the live site actually sends in the captured requests.
    # =========================================================================

    # 1. posts (FetchAds) — homepage/tag feed.
    async def fetch_feed(
        self,
        tag: str,
        *,
        city: Optional[str] = None,
        cities: Optional[list[str]] = None,
        page: int = 0,
        limit: Optional[int] = None,
        before_update_date: Optional[int] = None,
        only_with_image: bool = True,
        only_with_video: bool = False,
        order_main_by_post_id: bool = False,
    ) -> dict:
        """Fetch the post feed for a tag (or all tags if tag is None).

        `before_update_date` is the cursor: pass the last item's `updateDate`
        from the previous page to get the next batch.
        """
        variables: dict[str, Any] = {
            "tag": tag,
            "page": page,
            "limit": limit if limit is not None else self._limit,
        }
        if city:
            variables["city"] = city
        if cities:
            variables["cities"] = [c for c in cities if c]
        if before_update_date is not None:
            variables["beforeUpdateDate"] = before_update_date
        if only_with_image:
            variables["onlyWithImage"] = True
        if only_with_video:
            variables["onlyWithVideo"] = True
        if order_main_by_post_id:
            variables["orderMainByPostId"] = True
        return await self._query("posts", POSTS_QUERY, variables)

    async def stream_feed(
        self,
        tag: str,
        **kwargs,
    ) -> AsyncIterator[Post]:
        for page in range(self._max_pages):
            if page > 0:
                await self._jitter()
            payload = await self.fetch_feed(tag, page=page, **kwargs)
            items = (payload.get("posts") or {}).get("items") or []
            for raw in items:
                yield Post.model_validate(raw)
            if not (payload.get("posts") or {}).get("pageInfo", {}).get("hasNextPage"):
                break

    # 2. promotedPosts.
    async def promoted_posts(
        self,
        tag: str,
        *,
        city: Optional[str] = None,
    ) -> list[Post]:
        payload = await self._query("promotedPosts", PROMOTED_POSTS_QUERY, {"tag": tag, "city": city})
        items = (payload.get("promotedPosts") or {}).get("items") or []
        return [Post.model_validate(p) for p in items]

    # 3. relatedTags — cities with post counts for a tag.
    async def related_tags(
        self,
        tag: str,
        *,
        city: Optional[str] = None,
    ) -> list[dict]:
        payload = await self._query(
            "relatedTags", RELATED_TAGS_QUERY, {"tag": tag, "city": city}
        )
        return payload.get("relatedTags") or []

    # 4. isFollowingTag.
    async def is_following_tag(
        self,
        tag: str,
        *,
        city: Optional[str] = None,
        model: Optional[int] = None,
    ) -> bool:
        payload = await self._query(
            "isFollowingTag",
            IS_FOLLOWING_TAG_QUERY,
            {"token": self._auth.jwt, "tag": tag, "city": city, "model": model},
        )
        return bool(payload.get("isFollowingTag"))

    # 5. search — keyword search (the one the live site uses most).
    async def search(
        self,
        keyword: str,
        *,
        cities: Optional[list[str]] = None,
        city: Optional[str] = None,
        tag: Optional[str] = None,
        tags: Optional[list[str]] = None,
        page: int = 0,
        limit: Optional[int] = None,
        only_with_image: bool = True,
        only_with_video: bool = False,
        hide_show_rooms: bool = False,
        order_by_post_id: bool = False,
        during_date: Optional[str] = None,        # "1days" | "3days" | "1week" | "1months"
        near: Optional[str] = None,                # "@lat,lon" e.g. "@26.4336,50.1116"
    ) -> SearchResult:
        """The full search op with the real variable set the live site sends.

        Note: the live site never passes `id`, `authorUsername`, `carExtraInfo`,
        `priceRange`, `userLocation`, or `notTag`. They're in the schema but
        unused. Don't add them — they'd be hallucinated filters.
        """
        variables: dict[str, Any] = {
            "search": keyword,
            "page": page,
            "limit": limit if limit is not None else self._limit,
        }
        if cities:
            cleaned = [c for c in cities if c]
            if cleaned:
                variables["cities"] = cleaned
        elif city:
            variables["city"] = city
        if tag:
            variables["tag"] = tag
        if tags:
            variables["tags"] = tags
        if only_with_image:
            variables["onlyWithImage"] = True
        if only_with_video:
            variables["onlyWithVideo"] = True
        if hide_show_rooms:
            variables["hideShowRooms"] = True
        if order_by_post_id:
            variables["orderByPostId"] = True
        if during_date:
            variables["duringDate"] = during_date
        if near:
            variables["near"] = near

        payload = await self._query("search", SEARCH_QUERY, variables)
        result_payload = payload.get("search") or {}
        return SearchResult.model_validate(result_payload)

    async def stream_search(
        self,
        keyword: str,
        **kwargs,
    ) -> AsyncIterator[Post]:
        for page in range(self._max_pages):
            if page > 0:
                await self._jitter()
            result = await self.search(keyword, page=page, **kwargs)
            for post in result.items:
                yield post
            if not result.pageInfo.hasNextPage:
                break

    async def search_all(
        self,
        keyword: str,
        **kwargs,
    ) -> list[Post]:
        return [p async for p in self.stream_search(keyword, **kwargs)]

    # 6. similarPosts — the "real" get-post-by-id (returns the post + 3
    # related groups of posts).
    async def get_post_details(self, post_id: int) -> dict:
        payload = await self._query(
            "similarPosts", SIMILAR_POSTS_QUERY,
            {"id": post_id, "lat": None, "lon": None},
        )
        return payload.get("similarPosts") or {}

    # 7. postLikeInfo.
    async def post_like_info(self, post_id: int) -> dict:
        payload = await self._query(
            "postLikeInfo", POST_LIKE_INFO_QUERY,
            {"id": post_id, "token": self._auth.jwt},
        )
        return payload.get("postLikeInfo") or {}

    # 8. comments.
    async def comments(
        self,
        post_id: int,
        *,
        page: int = 0,
        oldest_first: bool = True,
        newest_first: bool = False,
    ) -> dict:
        payload = await self._query(
            "comments", COMMENTS_QUERY,
            {
                "postId": post_id,
                "commentsId": None,
                "page": page,
                "token": self._auth.jwt,
                "newestFirst": newest_first,
                "oldestFirst": oldest_first,
            },
        )
        return payload.get("comments") or {}

    # 9. user (full profile).
    async def user(
        self,
        *,
        username: Optional[str] = None,
        id: Optional[int] = None,
        handler: Optional[str] = None,
        rating_summary_only: bool = False,
    ) -> dict:
        query = USER_RATING_SUMMARY_QUERY if rating_summary_only else USER_QUERY
        payload = await self._query(
            "user", query,
            {
                "token": self._auth.jwt,
                "id": id,
                "username": username,
                "handler": handler,
            },
        )
        return (payload.get("user") or {}) if not rating_summary_only \
            else ((payload.get("user") or {}).get("ratingSummery") or {})

    # 10. isFollowingUser.
    async def is_following_user(self, username: str) -> bool:
        payload = await self._query(
            "isFollowingUser", IS_FOLLOWING_USER_QUERY,
            {"token": self._auth.jwt, "username": username},
        )
        return bool(payload.get("isFollowingUser"))

    # 11. notes — user notifications.
    async def notes(self, *, set_read: bool = False) -> dict:
        payload = await self._query(
            "notes", NOTES_QUERY,
            {"token": self._auth.jwt, "setRead": set_read},
        )
        return payload.get("notes") or {}

    # 12. sellersList.
    async def sellers_list(
        self,
        tags: list[str],
        *,
        page: int = 0,
    ) -> dict:
        payload = await self._query(
            "sellersList", SELLERS_LIST_QUERY,
            {"tags": tags, "page": page},
        )
        return payload.get("sellersList") or {}

    # 13. getLockerShipmentOffer.
    async def locker_shipment_offer(self, post_id: int) -> dict:
        payload = await self._query(
            "getLockerShipmentOffer", GET_LOCKER_SHIPMENT_OFFER_QUERY,
            {"postId": post_id},
        )
        return payload.get("getLockerShipmentOffer") or {}

    # 14. postContact.
    async def post_contact(
        self,
        post_id: int,
        *,
        is_manual_request: bool = False,
    ) -> dict:
        payload = await self._query(
            "postContact", POST_CONTACT_QUERY,
            {"postId": post_id, "isManualRequest": is_manual_request},
        )
        return payload.get("postContact") or {}

    # 15. followUser — mutation.
    async def follow_user(self, username: str) -> bool:
        payload = await self._query(
            "followUser", FOLLOW_USER_MUTATION,
            {"token": self._auth.jwt, "username": username},
        )
        return bool(payload.get("followUser"))

    # 16. submitGeoLocation — mutation.
    async def submit_geo_location(self, lat: float, lon: float) -> bool:
        payload = await self._query(
            "submitGeoLocation", SUBMIT_GEO_LOCATION_MUTATION,
            {"token": self._auth.jwt, "lat": lat, "lon": lon},
        )
        return bool(payload.get("submitGeoLocation"))

    # 17. searchSuggest — autocomplete. NOTE the typo `initalChars`.
    async def search_suggest(
        self,
        prefix: str,
        *,
        tag: Optional[str] = None,
    ) -> list[str]:
        payload = await self._query(
            "searchSuggest", SEARCH_SUGGEST_QUERY,
            {"initalChars": prefix, "tag": tag},
        )
        return (payload.get("searchSuggest") or {}).get("keywords") or []

    # 18. getTrendingKeywords.
    async def trending_keywords(self, range_in_days: int = 7) -> list[dict]:
        payload = await self._query(
            "getTrendingKeywords", GET_TRENDING_KEYWORDS_QUERY,
            {"rangeInDays": range_in_days},
        )
        return payload.get("getTrendingKeywords") or []

    # 19. getOutgoingBuyRequestsList — escrow history.
    async def outgoing_buy_requests(self, page: int = 0) -> dict:
        payload = await self._query(
            "getOutgoingBuyRequestsList", GET_OUTGOING_BUY_REQUESTS_LIST_QUERY,
            {"page": page},
        )
        return payload.get("getOutgoingBuyRequestsList") or {}

    # 20. getUserMentionSuggestions.
    async def user_mention_suggestions(self) -> list[dict]:
        payload = await self._query(
            "getUserMentionSuggestions", GET_USER_MENTION_SUGGESTIONS_QUERY, {}
        )
        return payload.get("getUserMentionSuggestions") or []

    # =========================================================================
    # Non-GraphQL: livestream REST endpoint
    # =========================================================================

    async def live_streams(self, limit: int = 40) -> LivestreamResponse:
        """Fetch currently-open haraj live shopping streams.

        Non-GraphQL — uses `https://livestream.haraj.com.sa/streams?limit=N`.
        The server caps `limit` at 40 in practice.
        """
        if self._client is None:
            raise HarajError("HarajClient must be used as an async context manager.")
        resp = await self._client.get(
            LIVESTREAM_ENDPOINT, params={"limit": limit}
        )
        if resp.status_code != 200:
            raise HarajError(
                f"Livestream HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return LivestreamResponse.model_validate(resp.json())