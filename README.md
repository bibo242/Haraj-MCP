# haraj-mcp

A **Model Context Protocol (MCP) server** for [haraj.com.sa](https://haraj.com.sa) — the largest classified-ads marketplace in Saudi Arabia.

This server exposes **21 tools** to any MCP-aware agent (Claude Desktop, Cursor, opencode, Zed, etc.) so it can search and fetch marketplace listings in real time, no copy-paste of curl commands required.

**All tools mirror the real haraj.com.sa operations** captured from a live browser session (2026-08-17). No hallucinated filters — every argument matches what the live front end actually sends in its GraphQL calls.

```
Claude Desktop / Cursor / opencode
        │
        │  MCP (JSON-RPC over stdio)
        ▼
   ┌──────────────┐
   │  haraj-mcp   │ ── HTTPS ──▶  graphql.haraj.com.sa
   │  (Python)    │                + livestream.haraj.com.sa
   └──────────────┘
```

## Tools exposed (21)

### Discovery
| Tool | Purpose |
|------|---------|
| `trending_keywords(range_in_days)` | Top trending search terms (default 7 days) |
| `search_suggest(prefix)` | Live search-box autocomplete (top 10) |
| `related_tags(tag)` | Cities-with-counts for a given tag |
| `live_streams(limit)` | Currently-open haraj live shopping streams |

### Feed / search
| Tool | Purpose |
|------|---------|
| `fetch_feed(tag, city?, cities?, page?, before_update_date?, limit?)` | Tag-based feed (homepage + category pages). `before_update_date` is the cursor — pass the last item's `updateDate` to get the next page. |
| `search(keyword, cities?, city?, tag?, tags?, during_date?, near?, ...)` | Keyword search. `during_date` accepts `1days`/`3days`/`1week`/`1months`. `near` is a geohash `@lat,lon`. |
| `promoted_posts(tag)` | Promoted-post carousel for a tag |
| `sellers_list(tags, page?)` | Sellers per tag (real estate etc.) |

### Post detail
| Tool | Purpose |
|------|---------|
| `get_post_details(post_id)` | Post + 3 related groups (via the real `similarPosts` endpoint — canonical "fetch by id") |
| `post_like_info(post_id)` | `{is_like, total, is_following}` |
| `comments(post_id)` | Comment list |
| `post_contact(post_id)` | `{contactText, contactMobile, shouldEnableWhatsApp}` |
| `locker_shipment_offer(post_id)` | `{offerId, isEligible, price}` (Locker shipping) |

### User
| Tool | Purpose |
|------|---------|
| `user(username?, user_id?, rating_summary_only?)` | Full profile (rating, followers, location history, badges) |
| `is_following_user(username)` | bool |
| `follow_user(username)` | Mutation: toggles follow |
| `user_mention_suggestions()` | For @-mentions |

### Account
| Tool | Purpose |
|------|---------|
| `notes(set_read?)` | Notifications (the bell icon) |
| `outgoing_buy_requests(page?)` | "Buy with confidence" escrow history |
| `is_following_tag(tag)` | bool |
| `check_auth()` | Verify `.env` credentials are still valid |

For `fetch_feed`, `promoted_posts`, and `search`, pass `full=True` to get the entire `Post` object instead of a compact summary. The compact summary has these keys:
```json
{
  "id": 185926519,
  "title": "...",
  "price_sar": 650.0,
  "price_display": "650 SAR",
  "url": "https://haraj.com.sa/...",
  "city": "الشرقيه",
  "geo_city": "الدمام",
  "post_date": 1785729404,
  "has_image": true,
  "image_count": 3,
  "thumb_urls": [
    "https://mimg6cdn.haraj.com.sa/.../a.jpg",
    "https://mimg6cdn.haraj.com.sa/.../b.jpg",
    "https://mimg6cdn.haraj.com.sa/.../c.jpg"
  ],
  "tags": ["شاشات", "..."],
  "has_price": true
}
```

The compact result includes up to **3 image URLs** (`thumb_urls`). Pass any of those URLs to your vision tool to view the post's photos. For posts with more than 3 images, the rest are in the full Post object (`full=True`) or in `get_post_details(post_id)` — `image_count` tells you the total.

## Install

```bash
cd /mnt/W/Desktop/Software/haraj-mcp
pip install -e .
```

This installs the `haraj-mcp` console script on your PATH.

## Configure auth

```bash
cp .env.example .env
# Edit .env and paste your HARAJ_JWT and LAST_REQUEST_ID.
```

How to get fresh values (they expire every ~10 days):

1. Open <https://haraj.com.sa> in Chrome and log in.
2. **F12** → **Network** tab → click any `graphql.haraj.com.sa` request.
3. In **Headers**, copy `authorization` (starts with `Bearer eyJ…`) and `lastRequestId`.
4. Paste into `.env` and restart the MCP server.

You can verify with `check_auth` — it returns the JWT's `exp` claim and `seconds_remaining`.

## Wire into your MCP client

### opencode / Claude Desktop / Cursor

Add this to your client's MCP config (usually `~/.config/opencode/opencode.json`, `~/Library/Application Support/Claude/claude_desktop_config.json`, or `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "haraj": {
      "command": "haraj-mcp",
      "cwd": "/mnt/W/Desktop/Software/haraj-mcp"
    }
  }
}
```

The server reads `.env` from `cwd`, so secrets stay in the project directory and don't leak into your MCP client config.

### Custom `.env` location

Set `HARAJ_MCP_ENV=/path/to/.env` in the `env` block of the MCP config.

## Example agent prompts

Once wired in, your agent can answer:

> "What's trending on haraj today?"

> "Fetch the latest 20 posts in `حراج السيارات` (the cars category)."

> "Search haraj for `RTX 4090` in the last week (`during_date=1week`)."

> "Get the seller's profile and all their current listings for post_id=185354313."

> "What shipping fee do I pay if I buy this post via Locker?"

> "What are people typing in the search box after `شاشة`?"

> "List all open live shopping streams right now."

## Run without an MCP client (debug)

Pipe JSON-RPC messages directly into the server:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0"}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_regions","arguments":{}}}' | python -m haraj_mcp
```

## Tests

```bash
python tests/test_smoke.py
```

10 tests cover: tool registration (21 tools), live `version` URL, `sec-ch-ua-platform-version` header, `initalChars` typo preservation, real search variables, compact serializer shape, JWT validation (valid/expired/malformed), `check_auth` error handling, and a full stdio end-to-end test.

## Agent guide

For a per-tool "what is this used for" reference (and example agent workflows), see **[`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md)**. It explains:

- The 21 tools organized by use case (discovery, feed/search, post detail, user, account)
- Common multi-step workflows (e.g. "find me a deal on an RTX 4090" → 5 chained tool calls)
- Pagination cheatsheet (which tools use which cursor)
- Privacy / safety notes (which tools return sensitive data like IBANs and mobile numbers)
- Conversation snippets showing the agent calling tools

Share `docs/AGENT_GUIDE.md` with the LLM client (or use it as a reference when writing system prompts).

## Project structure

```
haraj-mcp/
├── pyproject.toml
├── README.md
├── .env.example
├── src/haraj_mcp/
│   ├── __init__.py
│   ├── __main__.py        # entry point: `python -m haraj_mcp`
│   ├── server.py         # FastMCP setup, 21 tool registrations
│   ├── tools.py          # the 21 tool implementations
│   └── auth.py           # .env reader + JWT validation
├── haraj/                # GraphQL client (captured from live haraj.com.sa)
│   ├── client.py
│   ├── models.py
│   ├── queries.py        # 20 exact-captured query strings
│   ├── constants.py
│   ├── auth.py
│   └── images.py
└── tests/test_smoke.py
```

## What changed in v0.2.0

v0.1.0 had 4 tools (`search_haraj`, `get_post`, `list_regions`, `check_auth`) that I had hallucinated from the live GraphQL schema — many of the supported filters were never used by the real site.

v0.2.0 replaces them with **21 tools** that mirror the actual operations haraj.com.sa uses. Captured from a real browser session on 2026-08-17 (219 requests, 173 GraphQL POSTs). The key fixes:

- `search` no longer has hallucinated filters (`carExtraInfo`, `priceRange`, `userLocation`, `notTag`, `authorUsername`); only the variables the live site actually sends (`search`, `cities`, `city`, `tag`, `tags`, `page`, `limit`, `onlyWithImage`, `onlyWithVideo`, `hideShowRooms`, `orderByPostId`, `duringDate`, `near`)
- `searchSuggest` preserves the live wire's typo `initalChars` (the server requires it)
- The `version` URL param bumped to `2026-08-11 22` (was `2026-08-03 15`)
- Added `sec-ch-ua-platform-version` header (sent on every live call)
- `ViewOptions` has `mustLoginToView` (only present on `posts` op)
- New `live_streams` tool for the non-GraphQL `livestream.haraj.com.sa` endpoint
- `get_post_details` now uses the proper `similarPosts(id:)` endpoint (not the ID-as-keyword hack)

## What changed in v0.3.0

Compact post results now include up to **3 image URLs** (`thumb_urls`) plus an `image_count` field. The agent can pass any of those URLs to its vision tool to view the post's photos. For posts with more than 3 images, the rest are available via `full=True` (entire Post object) or `get_post_details(post_id)`. The cap of 3 keeps the listing response small (a typical photo is 200-500 KB; 3 URLs ≈ 1-2 KB of metadata).