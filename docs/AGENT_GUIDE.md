# Agent Guide for haraj-mcp

This document explains each of the 21 MCP tools in plain language, with practical guidance on **when** an LLM agent should call them, what they return, and how they chain into multi-step workflows.

If you're wiring this server into Claude Desktop, Cursor, opencode, or any other MCP-aware client, share this file with the agent (or with yourself, while building prompts). It maps directly to the 21 tools the server registers.

---

## The 21 Tools — Quick Reference

| # | Tool | What it returns | When the agent calls it |
|---|---|---|---|
| 1 | `check_auth` | JWT validity + expiry | First thing — confirm the token still works |
| 2 | `trending_keywords` | Top searched terms (last N days) | "What's hot right now?" |
| 3 | `search_suggest` | Autocomplete for a typed prefix | "What are people searching for after X?" |
| 4 | `related_tags` | Cities with post counts for a tag | "Where is most of the supply?" |
| 5 | `fetch_feed` | Post feed for a category tag | "Show me cars / electronics / jobs" |
| 6 | `promoted_posts` | Promoted carousel for a tag | "What's being pushed right now?" |
| 7 | `sellers_list` | Sellers in a tag (real estate etc.) | "Who are the top sellers in this category?" |
| 8 | `search` | Keyword search with real filters | "Find RTX 4090 under 2500 SAR" |
| 9 | `get_post_details` | Post + 3 related groups | "Tell me more about this listing" |
| 10 | `post_like_info` | {is_like, total, is_following} | "Is this popular / am I following?" |
| 11 | `comments` | Comment list | "What are people saying about this?" |
| 12 | `post_contact` | {contactText, contactMobile, whatsapp} | "How do I reach the seller?" |
| 13 | `locker_shipment_offer` | Locker shipping fee | "What would shipping cost?" |
| 14 | `user` | Full profile | "Who's this seller? Are they legit?" |
| 15 | `is_following_user` | bool | "Am I following them?" |
| 16 | `follow_user` | bool (toggle) | "Follow / unfollow this user" |
| 17 | `user_mention_suggestions` | Mention candidates | "@-mention autocomplete" |
| 18 | `notes` | Notifications | "What are my alerts?" |
| 19 | `outgoing_buy_requests` | Escrow history | "What escrow deals have I started?" |
| 20 | `is_following_tag` | bool | "Am I following this category?" |
| 21 | `live_streams` | Open live shopping streams | "Anything live to bid on right now?" |

---

## Practical "what's it used for" per tool

### Bootstrapping (the agent runs these first)

**1. `check_auth()`** — sanity check. "Is my token still good, or do I need to tell the user to refresh it?" If `seconds_remaining < 86400` (1 day), warn the user. If the token has expired, the server's auth-gated tools will return errors and the user needs to update `.env` and restart the server.

**2. `trending_keywords(range_in_days=7)`** — "What's the market buzzing about?" Returns 20 terms. The agent might say *"RTX 4090 is trending, want me to find current listings?"* Use `range_in_days=1` for today's pulse, `30` for monthly trends.

**3. `search_suggest(prefix="شاشة", tag="حراج الأجهزة")`** — autocomplete. Two ways the agent uses this:
- **For the user**: *"you typed 'شاشة', did you mean شاشة قيمنق or شاشة سامسونج?"*
- **For itself**: discover related keywords before searching

### Browse / discover

**4. `related_tags(tag="حراج السيارات")`** — cities with counts. Answers "where is most of the supply?" Returns sorted list like `[(الرياض, 435607), (جده, 173302), (الشرقيه, 123480), ...]`. The agent picks a city to filter on next.

**5. `fetch_feed(tag="حراج الأجهزة", city="الشرقيه", page=0, before_update_date=None, limit=21)`** — the workhorse. Powers the homepage. Pagination uses `before_update_date` cursor (Unix seconds). Use this for "show me what's listed in category X right now".

**6. `promoted_posts(tag="حراج الأجهزة")`** — the carousel of paid/featured posts. Useful for "what's being pushed right now" — agents can use this to gauge if a category is being monetized (a sign of high demand).

**7. `sellers_list(tags=["حراج العقار"])`** — sellers in a tag. Used when the user wants to find *reputable* sellers. Agent combines with `user(username=...)` to see their rating + history.

### Search (most important tool)

**8. `search(keyword="RTX 4090", cities=["الشرقيه"], during_date="1week", only_with_image=True, near=None, ...)`** — **the primary tool**. Variables the live site actually sends:
- `keyword` (required)
- `cities` or `city` (location filter)
- `tag` (single sub-category like `أجهزة كمبيوتر`)
- `tags` (array, valid but never used in practice)
- `during_date` (`"1days"`, `"3days"`, `"1week"`, `"1months"`) — recency filter
- `near` (geohash `"@lat,lon"`) — geographic radius
- `only_with_image` (default true)
- `only_with_video` (default false)
- `hide_show_rooms` (default false; if true, hides dealer posts)
- `order_by_post_id` (newest-first when true)
- `page`, `limit`

The agent uses this for: *"find me RTX 4090 in الشرقية from the last week with photos"*.

### Per-post operations

**9. `get_post_details(post_id=185354313)`** — fetch a post + up to 3 related groups (`{tag, city, posts: {items, pageInfo}}` for each). The agent uses this to drill into a specific listing or to surface similar posts in the same subcategory/city. Pass `full=False` for a compact summary.

**10. `post_like_info(post_id=185354313)`** — `{is_like, total, is_following}`. Agent uses to assess "is this a popular listing or a quiet one?" or to update UI state if the user clicks like via the agent.

**11. `comments(post_id=185354313, oldest_first=True)`** — comments. Agent uses to read seller replies, gauge negotiation history, or warn the user about scam reports.

**12. `post_contact(post_id=185354313)`** — `{contactText, contactMobile, shouldEnableWhatsApp}`. **Privacy-sensitive** — note that the mobile number is only returned if the seller has chosen to expose it. The agent shows this to the user with a warning if the contact is exposed.

**13. `locker_shipment_offer(post_id=185354313)`** — `{offerId, isEligible, price}`. The "Locker" service is haraj's escrow shipping. Agent uses this when the user is interested in a post and wants to know "can I use the safe-payment option, and what does it cost?"

### User / social

**14. `user(username="...", user_id=None, rating_summary_only=False)`** — full profile. Returns registration date, follower count, rating (upRank/downRank/upPaidRank/downPaidRank/rateAverage), badges, geoLocation history, isMember/isAdmin, VATNumber, etc. The agent uses this for trust scoring: *"this seller has been on haraj for 3 years, 0 negative reviews, GCC-spec only"*.

**15. `is_following_user(username="...")`** — bool. Used to check follow state before deciding whether to call `follow_user`.

**16. `follow_user(username="...")`** — mutation, toggles. Returns the new is_following state.

**17. `user_mention_suggestions()`** — `[{userId, username, handler}]`. Used when the agent is composing a comment or DM and the user typed `@`.

### Account

**18. `notes(set_read=False)`** — user notifications (the bell icon). Returns the same shape the website shows. Agent can summarize: *"you have 3 unread notes: a comment reply, a price drop on something you liked, and a new ad from a followed seller"*.

**19. `outgoing_buy_requests(page=0)`** — "Buy with confidence" escrow history. Returns full deal state including shipping address, status (paid/picked/delivered/disputed), prices, IBANs (for the buyer!). **Privacy-sensitive** — IBAN info is real money routing. The agent should only call this when the user explicitly asks about their escrow deals.

**20. `is_following_tag(tag="...")`** — bool.

**21. `live_streams(limit=40)`** — currently-open haraj live shopping streams. Returns `{id, title, cover_url, streamer, num_messages, num_viewers, started_at}`. The agent can recommend "there's a live stream on مجسمات سيارات with 34 viewers right now".

---

## Common agent workflows (so you can see how the tools chain)

### "Find me a good deal on an RTX 4090"

1. `trending_keywords(7)` — confirm RTX 4090 is in the top 20
2. `search(keyword="RTX 4090", cities=["الشرقيه"], during_date="1week")` — get recent listings
3. `get_post_details(post_id=...)` for the top 3 by price
4. `user(username=...)` for the sellers to check reputation
5. `locker_shipment_offer(post_id=...)` to show shipping cost

### "What's popular today in cars?"

1. `fetch_feed(tag="حراج السيارات")` — page 0
2. `promoted_posts(tag="حراج السيارات")` — see what's pushed
3. `trending_keywords(1)` — what car-related terms are trending
4. (Optional) `live_streams()` — any car livestreams running

### "Help me sell my iPhone — what's a fair price?"

1. `search(keyword="ايفون 17 برو ماكس", cities=["الشرقيه"], during_date="1months")` — recent comps
2. `trending_keywords(7)` — is "iPhone 17" still hot?
3. `search_suggest(prefix="ايفون 17")` — what other variants are people looking for
4. (Agent computes price suggestion from the comps, then maybe) `fetch_feed(tag="حراج الأجهزة")` to see how my listing would be displayed

### "Clean up my account"

1. `notes(set_read=True)` — mark all read
2. `is_following_tag(...)` for each tag you want to unfollow
3. `sellers_list(tags=["حراج العقار"])` — review who's selling in tags I follow

### "Show me cars near me under 50,000 SAR"

1. `submit_geo_location(lat, lon)` *(the agent would need this enabled — currently not exposed; use the website to grant location)*
2. `search(keyword="", tag="حراج السيارات", cities=["الشرقيه"], near="@26.4336,50.1116", price_max=50000)` *(note: as of the 2026-08-17 capture, the live site doesn't pass `priceRange` to GraphQL — filtering by price is done client-side after the search returns; the agent would need to filter results in code)*

### "Find me a deal and check if the seller is legit"

1. `search(keyword="...", cities=["الشرقيه"])` — get candidates
2. For the top 3 by price:
   - `get_post_details(post_id=...)` — see the full post + similar items
   - `user(username=...)` — check seller reputation (rating, history)
   - `comments(post_id=...)` — see what buyers said
3. `locker_shipment_offer(post_id=...)` — show safe-payment option

---

## Pagination cheatsheet

Different operations paginate differently. The agent needs to know which is which:

| Tool | Pagination | Cursor field |
|------|-----------|--------------|
| `fetch_feed` | `page` (int) + `before_update_date` (Unix sec) | `beforeUpdateDate` = last item's `updateDate` |
| `search` | `page` (int) only | `hasNextPage` bool |
| `comments` | `page` (int) | `hasNextPage`, `hasPreviousPage` |
| `sellers_list` | `page` (int) | `hasNextPage`, `hasPreviousPage` |
| `outgoing_buy_requests` | `page` (int) | `hasNextPage`, `hasPreviousPage` |
| `promoted_posts` | none (fixed slice) | – |
| `related_tags`, `search_suggest`, `trending_keywords`, `notes`, `is_following_*` | none | – |
| `live_streams` | `data.page_info.next_last_key` (opaque) | pass back as `last_key` query param |

For `fetch_feed`, when `has_next_page` is true in the response, take the last item's `updateDate`, call again with `before_update_date=<that value>` and `page=0`. The live site actually uses `page=2,3,4...` (skipping page=1) but the cursor approach is more reliable.

---

## Privacy / safety notes for the agent

When the agent uses these tools, it should be careful about:

- **`outgoing_buy_requests`** returns real IBANs, shipping addresses, and payment status. Show only when the user explicitly asks.
- **`post_contact`** may include a mobile number. Don't share with anyone.
- **`user`** exposes `mobile`, `email`, `geoLocation` history, `VATNumber`. Don't share.
- **`follow_user`** is a mutation. Ask before calling (don't follow random users).
- **Pagination loops**: when iterating with `fetch_feed` or `search`, cap at 5-10 pages to avoid hammering the server.
- **Rate limits**: the live haraj server has its own rate limits. If the agent gets 429 errors, back off (the `HarajClient` already does exponential backoff automatically).

---

## Tips for the agent

1. **Start every conversation with `check_auth`** — if the token expired mid-conversation, all the auth-gated tools will fail.
2. **Use `search_suggest` before `search`** — autocomplete often surfaces better keywords than what the user typed.
3. **Use `related_tags` before picking a city** — don't guess where the supply is.
4. **Use `during_date` aggressively** — the live server is fast but the user doesn't want to see 3-week-old listings.
5. **Verify seller reputation with `user` + `comments`** before recommending a purchase.
6. **Show `locker_shipment_offer` for any non-trivial purchase** — escrow is the only safe way to pay.

---

## Where these tool definitions live in code

The tool definitions (name, description, argument types) are in `src/haraj_mcp/server.py` — the `@mcp.tool()` decorators. The implementations are in `src/haraj_mcp/tools.py`. The single source of truth for the tool list is `tools.TOOL_NAMES` in `src/haraj_mcp/tools.py`.

To regenerate the launcher's tool list after adding a new tool:
1. Add the implementation to `tools.py` and append the name to `TOOL_NAMES`
2. Add the `@mcp.tool()` decorator in `server.py`
3. Run `python tests/test_smoke.py` to confirm the new tool registers over stdio

---

## Examples (as conversation snippets)

**User:** "what's a good deal on a 4090 in dammam?"

Agent: calls `check_auth`, then `search(keyword="RTX 4090", cities=["الشرقيه"], during_date="1week", only_with_image=True)`, then for each result calls `get_post_details` and `user` to verify the seller.

**User:** "how's the iPhone market looking?"

Agent: calls `trending_keywords(7)` to see if "ايفون" is hot, then `search_suggest(prefix="ايفون 17")` to find variants, then `search(keyword="ايفون 17", during_date="1months")` for recent comps, computes average price and gives the user a market summary.

**User:** "follow that seller from the RTX listing"

Agent: calls `get_post_details` if it only has a post_id, then `user` to confirm the username, then `is_following_user` to check current state, then asks the user "you want to follow <username>?" before calling `follow_user`.

**User:** "anything live right now?"

Agent: calls `live_streams()` and lists the open streams with their viewer counts.

---

If you want me to add an examples directory with full worked conversations in JSON form (so you can use them as few-shot examples for the agent), say so.