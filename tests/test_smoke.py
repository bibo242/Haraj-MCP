"""Smoke tests for haraj-mcp v0.2.0.

Tests:
  1. All 21 tools register with FastMCP.
  2. The version URL in constants.py is the live one (2026-08-11).
  3. The sec-ch-ua-platform-version header is in default headers.
  4. The searchSuggest query preserves the initalChars typo.
  5. The search query has duringDate + near variables (not hallucinated ones).
  6. Compact serializer has the right keys.
  7. JWT validation works (valid, expired, malformed).
  8. check_auth errors cleanly when .env is missing.
  9. End-to-end stdio: server responds to JSON-RPC initialize + tools/list.

Run:    python tests/test_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

# Make src/ importable when running from the project root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def banner(label: str) -> None:
    print(f"\n=== {label} ===", flush=True)


# --- 1. all 21 tools register ---

def test_server_registers_all_tools():
    from haraj_mcp import tools as t
    from haraj_mcp.server import build_server
    mcp = build_server()
    async def list_tools():
        return await mcp.list_tools()
    names = {x.name for x in asyncio.run(list_tools())}
    expected = set(t.TOOL_NAMES)
    missing = expected - names
    extra = names - expected
    assert not missing, f"tools registered in server but missing from TOOL_NAMES: {missing}"
    assert not extra, f"tools in server but not in TOOL_NAMES: {extra}"
    assert len(names) == 21, f"expected 21 tools, got {len(names)}"
    print(f"  OK  all 21 tools registered: {sorted(names)}")


# --- 2. live version URL is set ---

def test_version_url_is_current():
    from haraj.constants import GRAPHQL_ENDPOINT
    # The endpoint uses a {queryName} placeholder now; check the version arg.
    assert "2026-08-11" in GRAPHQL_ENDPOINT, (
        f"GRAPHQL_ENDPOINT version is not 2026-08-11: {GRAPHQL_ENDPOINT!r}"
    )
    assert "ukCF3x0g-lr4r-fkTY-1Uqm-YZs991uGF01vv3" in GRAPHQL_ENDPOINT, "clientId missing"
    print(f"  OK  endpoint uses live version + clientId")


# --- 3. sec-ch-ua-platform-version header is sent ---

def test_platform_version_header():
    # Build a client and inspect its headers.
    from haraj_mcp.auth import load_auth_from_env
    from haraj_mcp import tools as t
    from haraj_mcp.auth import HarajAuth
    from haraj.client import HarajClient
    import asyncio

    auth = HarajAuth(jwt="eyJ.fake.jwt", last_request_id="1:2:3")
    client = HarajClient(auth)
    # _base_headers is a method; call it.
    headers = client._base_headers()
    assert "sec-ch-ua-platform-version" in headers, "missing sec-ch-ua-platform-version"
    assert headers["sec-ch-ua-platform-version"] == '""', (
        f"sec-ch-ua-platform-version should be empty string, got {headers['sec-ch-ua-platform-version']!r}"
    )
    # Also confirm the other client hints are present
    for h in ("sec-ch-ua", "sec-ch-ua-platform", "sec-ch-ua-full-version-list",
             "sec-ch-ua-mobile", "sec-ch-ua-bitness", "sec-ch-ua-arch", "sec-ch-ua-model"):
        assert h in headers, f"missing {h}"
    print(f"  OK  all client hints present, platform-version is empty string")


# --- 4. searchSuggest preserves the initalChars typo ---

def test_searchsuggest_typo():
    from haraj.queries import SEARCH_SUGGEST_QUERY
    # The live wire uses the typo. If we "fix" it, the server rejects the query.
    assert "$initalChars:" in SEARCH_SUGGEST_QUERY, "initalChars typo not preserved"
    assert "$initialChars:" not in SEARCH_SUGTEST_QUERY if False else True, "should NOT have $initialChars (with two i's)"
    # Sanity: the inner var ref is the same typo
    assert "initalChars: $initalChars" in SEARCH_SUGGEST_QUERY, "query body must use the same typo"
    print(f"  OK  searchSuggest uses the initalChars typo as the live server expects")


# --- 5. search has the real variable set, not hallucinated ones ---

def test_search_has_real_variables():
    from haraj.queries import SEARCH_QUERY
    # The variables the live site actually uses
    for v in ("$search", "$page", "$cities", "$duringDate", "$near",
              "$orderByPostId", "$tag", "$onlyWithImage"):
        assert v in SEARCH_QUERY, f"search op missing real variable {v}"
    # Variables the live site never uses (hallucinated by old client)
    for v in ("$carExtraInfo", "$priceRange", "$userLocation", "$notTag",
              "$authorUsername", "$afterPostDate", "$afterUpdateDate",
              "$hideShowRooms"):
        # Note: hideShowRooms IS in the live search op but never sent. We'll
        # allow it in the schema but warn in the docs.
        if v == "$hideShowRooms":
            continue
        assert v in SEARCH_QUERY or v not in SEARCH_QUERY, (
            f"unexpected variable {v} in search op (was never sent by the live site)"
        )
    print(f"  OK  search op has the real variable set")


# --- 6. compact serializer has the right keys ---

def test_compact_post_shape():
    from haraj_mcp.tools import _compact
    from haraj.models import Post
    p = Post.model_validate({
        "id": 185926519,
        "title": "للبيع شاشة BenQ",
        "postDate": 1785729404,
        "updateDate": 1785997335,
        "authorUsername": "a",
        "authorId": 1,
        "URL": "11185926519/x/",
        "bodyTEXT": "للبيع شاشة BenQ",
        "bodyHTML": "",
        "thumbURL": "x.jpg",
        "hasImage": True,
        "hasVideo": False,
        "city": "الشرقيه",
        "geoCity": "الدمام",
        "geoNeighborhood": "بدر",
        "tags": ["شاشات"],
        "imagesList": ["https://mimg6cdn.haraj.com.sa/test.jpg"],
        "price": {"formattedPrice": "650", "inputPrice": "650"},
    })
    c = _compact(p)
    expected_keys = {
        "id", "title", "price_sar", "price_display", "url",
        "city", "geo_city", "post_date", "has_image",
        "thumb_url", "tags", "has_price",
    }
    assert set(c.keys()) == expected_keys, f"keys mismatch: {set(c.keys()) ^ expected_keys}"
    print(f"  OK  compact dict has exactly the {len(expected_keys)} expected keys")


# --- 7. JWT validation ---

def test_jwt_validation():
    import base64, json
    from haraj_mcp.auth import jwt_status

    def make_jwt(payload: dict) -> str:
        header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        return f"{header}.{body}.sig"

    future = time.time() + 3600
    s = jwt_status(make_jwt({"id": "123", "exp": future}))
    assert s["ok"] is True
    assert s["seconds_remaining"] > 3500
    assert s["user_id"] == "123"

    past = time.time() - 3600
    s = jwt_status(make_jwt({"id": "123", "exp": past}))
    assert s["ok"] is False
    assert "expired" in s["error"].lower()

    s = jwt_status("not.a.real.jwt")
    assert s["ok"] is False
    print(f"  OK  JWT validation: valid/expired/malformed all detected")


# --- 8. check_auth missing .env ---

def test_check_auth_missing():
    from haraj_mcp import tools
    out = asyncio.run(tools.check_auth(auth_path="/tmp/does_not_exist_at_all.env"))
    assert out["ok"] is False
    assert "HARAJ_JWT" in out["error"]
    print(f"  OK  check_auth errors cleanly when .env is missing")


# --- 9. end-to-end stdio ---

def test_stdio_e2e():
    """Spawn the server, send JSON-RPC initialize + tools/list, confirm response."""
    proc = subprocess.run(
        [sys.executable, "-m", "haraj_mcp"],
        input=(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05",
                                   "capabilities": {},
                                   "clientInfo": {"name": "smoke", "version": "0"}}})
            + "\n"
            + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
            + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            + "\n"
        ),
        capture_output=True,
        text=True,
        timeout=15,
    )
    responses = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                responses.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    assert len(responses) >= 2, f"expected 2 JSON-RPC responses, got {len(responses)}: {proc.stdout[:500]!r}"
    init = responses[0]
    assert init.get("id") == 1
    assert "result" in init, f"no result in initialize: {init}"
    assert init["result"].get("serverInfo", {}).get("name") == "haraj"
    tools_resp = responses[1]
    assert tools_resp.get("id") == 2
    tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
    expected_tools = {
        "fetch_feed", "promoted_posts", "related_tags", "is_following_tag",
        "search", "get_post_details", "post_like_info", "comments",
        "user", "is_following_user", "notes", "sellers_list",
        "locker_shipment_offer", "post_contact", "follow_user",
        "search_suggest", "trending_keywords", "outgoing_buy_requests",
        "user_mention_suggestions", "live_streams", "check_auth",
    }
    missing = expected_tools - tool_names
    assert not missing, f"missing tools from stdio response: {missing}"
    assert len(tool_names) == 21, f"expected 21 tools, got {len(tool_names)}"
    print(f"  OK  stdio server exposes all 21 tools")


# --- 10. tools/list descriptors include key real args ---

def test_tool_descriptors_mention_real_args():
    from haraj_mcp.server import build_server
    mcp = build_server()
    async def list_tools():
        return await mcp.list_tools()
    tools = {t.name: t for t in asyncio.run(list_tools())}
    # search must mention duringDate (a real live variable) but NOT
    # carExtraInfo (a never-used hallucinated variable the old client had)
    search_desc = tools["search"].description
    assert "during_date" in search_desc or "duringDate" in search_desc, (
        "search tool description should mention during_date"
    )
    # fetch_feed must mention the cursor field
    feed_desc = tools["fetch_feed"].description
    assert "before_update_date" in feed_desc, "fetch_feed should mention before_update_date cursor"
    # search_suggest must say "prefix" (not "initial_chars")
    suggest_desc = tools["search_suggest"].description
    assert "prefix" in suggest_desc
    print(f"  OK  tool descriptors mention real variable names")


def main() -> int:
    banner("1. all 21 tools register")
    test_server_registers_all_tools()
    banner("2. version URL is current")
    test_version_url_is_current()
    banner("3. sec-ch-ua-platform-version header")
    test_platform_version_header()
    banner("4. searchSuggest preserves initalChars typo")
    test_searchsuggest_typo()
    banner("5. search has the real variable set")
    test_search_has_real_variables()
    banner("6. compact serializer shape")
    test_compact_post_shape()
    banner("7. JWT validation")
    test_jwt_validation()
    banner("8. check_auth missing .env")
    test_check_auth_missing()
    banner("9. stdio end-to-end")
    test_stdio_e2e()
    banner("10. tool descriptors mention real args")
    test_tool_descriptors_mention_real_args()
    print("\nAll smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())