"""Constants for the haraj.com.sa GraphQL endpoint.

Sourced from a real browser capture (2026-08-17) of the live haraj.com.sa
front end, not hallucinated.
"""

# The base URL is the same for every queryName; we override `queryName` per
# call. The live front end currently uses `version=N0.0.1, 2026-08-11 22/`
# (the build id the SPA was last built with).
GRAPHQL_ENDPOINT = (
    "https://graphql.haraj.com.sa/"
    "?queryName={queryName}"
    "&clientId=ukCF3x0g-lr4r-fkTY-1Uqm-YZs991uGF01vv3"
    "&version=N0.0.1%20,%202026-08-11%2022/"
)

GRAPHQL_ORIGIN = "https://haraj.com.sa"
GRAPHQL_REFERER = "https://haraj.com.sa/"

# The livestream endpoint is non-GraphQL (it's a custom REST API).
LIVESTREAM_ENDPOINT = "https://livestream.haraj.com.sa/streams"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)

SEC_CH_UA = '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"'
SEC_CH_UA_PLATFORM = '"Linux"'
SEC_CH_UA_PLATFORM_VERSION = '""'   # empty string — sent verbatim on every live call
SEC_CH_UA_FULL_VERSION_LIST = (
    '"Brave";v="149.0.0.0", "Chromium";v="149.0.0.0", "Not)A;Brand";v="24.0.0.0"'
)

# The 13 Saudi administrative regions + 6 city-level values the live API
# actually accepts in the `city` / `cities: [String]` filter. Spellings match
# the live capture exactly (note the missing ة on مكه, الشرقيه, الباحه,
# الحدود الشماليه — that's how the server expects them).
SAUDI_REGIONS: dict[str, str] = {
    # 13 administrative regions
    "الرياض": "Riyadh",
    "مكه": "Makkah",
    "المدينه": "Madinah",
    "الشرقيه": "Eastern Province",
    "القصيم": "Qassim",
    "عسير": "Asir",
    "تبوك": "Tabuk",
    "حائل": "Hail",
    "جازان": "Jazan",
    "نجران": "Najran",
    "الباحه": "Al Bahah",
    "الحدود الشماليه": "Northern Borders",
    "الجوف": "Al Jawf",
    # 6 city-level values the live site accepts as if they were regions
    "الطايف": "Taif",
    "جده": "Jeddah",
    "حفر الباطن": "Hafr Al-Batin",
    "الدرعية": "Diriyah",
    "قلوة": "Qalwah",
    "ينبع": "Yanbu",
    "عرعر": "Arar",
}

ALL_REGIONS_KEY = "all"  # sentinel: empty list in the GraphQL variables = no region filter