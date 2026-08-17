"""GraphQL query strings captured from the live haraj.com.sa front end.

All strings below were copied verbatim from a 2026-08-17 browser capture
of the real site (219 requests, 173 GraphQL POSTs). The structure is
frozen: do NOT rewrite them by hand. If a query stops working, capture
the site again and replace.

Notable quirks captured from the live wire:
  - `searchSuggest` uses the typo `$initalChars` (missing second 'i').
  - The `posts` op has `generalInfo` declared twice inside `PostFields`
    (frontend bug, server tolerates).
  - The `carExtraInfo` arg in the Search op is declared as `$carExtraInfo`
    (lower-case variable) but used as `CarExtraInfo: $carExtraInfo` in
    the body (upper-case). Preserved.
  - `posts` paginates with a `beforeUpdateDate` cursor; `search` paginates
    with a plain `page` int.
"""

# The `PostFields` fragment is the same shape across nearly every query.
# Captured verbatim from the live `search` operation.
POST_FIELDS = """
    fragment PostFields on Post {
      id
      title
      postDate
      updateDate
      authorUsername
      authorId
      URL
      bodyTEXT
      bodyHTML
      thumbURL
      hasImage
      hasVideo
      city
      geoCity
      geoNeighborhood
      geoHash
      tags
      imagesList
      commentEnabled
      commentStatus
      isPromoted
      commentCount
      upRank
      downRank
      status
      postType
      generalInfo {
        key
        value
      }
      price {
        formattedPrice
        inputPrice
      }
      realEstateInfo {
        re_REGA_Advertiser_registration_number
        re_REGA_Authorization_number
      }
      carInfo {
        sellOrWaiver
        is4DW
        model
        mileage
        fuel
        gear
        condition
        carOrRelated
        Bank
      }
      jobsInfo {
        jobs_OfferType
        jobs_ExperienceLevel
        jobs_ContractType
        jobs_Qualification
        jobs_CommercialeRgisterNumber
      }
      postNotesList {
        iconName
        iconUrl
        note
        link
      }
      BuyButton {
        Link
        StoreName
        Name
        canRequestWasataService
        isMakeOfferEnabled
      }
    }
"""

# Mirror of the `realEstateOptions` fragment used by some posts.
REAL_ESTATE_OPTIONS = """
    fragment realEstateOptions on reInfo {
      re_REGA_Advertiser_registration_number
      re_REGA_Authorization_number
    }
"""


# -------------------------------------------------------------------------
# 1. search — the keyword search operation.
# Variables actually used in the capture: search, page, cities, duringDate,
# near, orderByPostId, tag, onlyWithImage. (Schema also declares the rest
# but the live site never sends them.)
# -------------------------------------------------------------------------
SEARCH_QUERY = """
    query Search(
      $id: [Int],
      $cities: [String],
      $search: String!,
      $city: String,
      $authorUsername: String,
      $page: Int,
      $limit: Int,
      $afterPostDate: Int,
      $afterUpdateDate: Int,
      $tag: String,
      $tags: [String],
      $carExtraInfo: CarExtraInfo,
      $priceRange: PriceRange,
      $near: String,
      $onlyWithImage: Boolean,
      $onlyWithVideo: Boolean,
      $duringDate: String,
      $userLocation: GeoPoint,
      $notTag: String,
      $hideShowRooms: Boolean,
      $orderByPostId: Boolean
    ) {
      search(
        id: $id,
        search: $search,
        city: $city,
        cities: $cities,
        authorUsername: $authorUsername,
        page: $page,
        limit: $limit,
        afterPostDate: $afterPostDate,
        afterUpdateDate: $afterUpdateDate,
        tag: $tag,
        tags: $tags,
        CarExtraInfo: $carExtraInfo,
        priceRange: $priceRange,
        near: $near,
        onlyWithImage: $onlyWithImage,
        onlyWithVideo: $onlyWithVideo,
        userLocation: $userLocation,
        duringDate: $duringDate,
        notTag: $notTag,
        hideShowRooms: $hideShowRooms,
        orderByPostId: $orderByPostId
      ) {
        analyticsContext
        items { ...PostFields }
        pageInfo { hasNextPage }
        viewOptions { hasSellersList }
      }
    }
    """ + POST_FIELDS


# -------------------------------------------------------------------------
# 2. posts — the homepage/tag-feed operation. (FetchAds)
# Paginates with `beforeUpdateDate` (Unix seconds cursor). Page 1 is
# reserved for promoted content and is skipped.
# -------------------------------------------------------------------------
POSTS_QUERY = """
    query FetchAds(
      $id: [Int] = null,
      $city: String = null,
      $cities: [String],
      $authorUsername: String = null,
      $page: Int = null,
      $limit: Int = null,
      $afterPostDate: Int = null,
      $afterUpdateDate: Int = null,
      $beforeUpdateDate: Int = null,
      $beforePostDate: Int = null,
      $tag: String = null,
      $near: String = null,
      $onlyWithImage: Boolean = null,
      $onlyWithVideo: Boolean = null,
      $orderMainByPostId: Boolean = null,
      $notTag: String = null
    ) {
      posts(
        id: $id
        city: $city
        cities: $cities
        authorUsername: $authorUsername
        page: $page
        limit: $limit
        afterPostDate: $afterPostDate
        afterUpdateDate: $afterUpdateDate
        beforeUpdateDate: $beforeUpdateDate
        beforePostDate: $beforePostDate
        tag: $tag
        near: $near
        onlyWithImage: $onlyWithImage
        onlyWithVideo: $onlyWithVideo
        orderMainByPostId: $orderMainByPostId
        notTag: $notTag
      ) {
        analyticsContext
        items { ...PostFields }
        pageInfo { hasNextPage }
        viewOptions { hasSellersList mustLoginToView }
      }
    }
    """ + POST_FIELDS


# -------------------------------------------------------------------------
# 3. promotedPosts — fixed-length promoted carousel for a tag.
# -------------------------------------------------------------------------
PROMOTED_POSTS_QUERY = """
    query PromotedPosts($tag: String!, $city: String = null) {
      promotedPosts(tag: $tag, city: $city) {
        analyticsContext
        items { ...PostFields }
        pageInfo { hasNextPage }
      }
    }
    """ + POST_FIELDS


# -------------------------------------------------------------------------
# 4. relatedTags — cities-with-counts for a given tag.
# Returns [{tag, count, city}].
# -------------------------------------------------------------------------
RELATED_TAGS_QUERY = """
    query GetRelatedTags($tag: String!, $city: String) {
      relatedTags(tag: $tag, city: $city) { tag, count, city }
    }
"""


# -------------------------------------------------------------------------
# 5. isFollowingTag — boolean, for the "follow star" UI.
# -------------------------------------------------------------------------
IS_FOLLOWING_TAG_QUERY = """
    query isFollowingTag($token: String!, $tag: String!, $city: String, $model: Int) {
      isFollowingTag(token: $token, tag: $tag, city: $city, model: $model)
    }
"""


# -------------------------------------------------------------------------
# 6. similarPosts — the "real" get-by-id. Returns the post + 3 related
# groups (each with its own pageInfo).
# -------------------------------------------------------------------------
SIMILAR_POSTS_QUERY = """
    query SimilarPosts($id: Int!, $lat: Float, $lon: Float) {
      similarPosts(id: $id, lat: $lat, lon: $lon) {
        id
        groupTags {
          tag
          city
          posts {
            analyticsContext
            items { ...PostFields }
            pageInfo { hasNextPage }
          }
        }
      }
    }
    """ + POST_FIELDS


# -------------------------------------------------------------------------
# 7. postLikeInfo — {isLike, total, isFollowing}.
# -------------------------------------------------------------------------
POST_LIKE_INFO_QUERY = """
    query postLikeInfo($id: Int!, $token: String) {
      postLikeInfo(id: $id, token: $token) { isLike, total, isFollowing }
    }
"""


# -------------------------------------------------------------------------
# 8. comments.
# -------------------------------------------------------------------------
COMMENTS_QUERY = """
    query Comments($postId: Int!, $commentsId: [Int!], $page: Int, $token: String,
                   $newestFirst: Boolean, $oldestFirst: Boolean) {
      comments(
        postId: $postId
        id: $commentsId
        page: $page
        token: $token
        newestFirst: $newestFirst
        oldestFirst: $oldestFirst
      ) {
        items {
          id, authorUsername, authorId, authorLevel, body, isNewUser, status,
          deleteReason, seqId, date, isReply, replyToCommentId,
          mention { textContainsMention, username, handler, userId }
        }
        pageInfo { hasNextPage, hasPreviousPage }
      }
    }
"""


# -------------------------------------------------------------------------
# 9. user — full profile. The light variant `UserRatingSummary` only
# fetches ratingSummery.
# -------------------------------------------------------------------------
USER_QUERY = """
    query User($token: String, $id: Int, $username: String, $handler: Handler) {
      user(
        token: $token
        id: $id
        username: $username
        handler: $handler
      ) {
        id
        username
        registrationDate
        countFollowers
        mobile
        handler
        discount
        isMember
        isAdmin
        isBlocked
        email
        didPay
        lastSeen
        messageToUser
        subscription {
          type, joinDate, expirationDate, mustJoinType, isActive
        }
        ratingSummery {
          upRank, downRank, upPaidRank, downPaidRank, rateAverage
        }
        badges { badge }
        geoLocation { lat, lon, date }
        isRealtor
        linkedViaNafath
        VATNumber
      }
    }
"""

USER_RATING_SUMMARY_QUERY = """
    query UserRatingSummary($token: String, $id: Int, $username: String) {
      user(token: $token, id: $id, username: $username) {
        ratingSummery { upRank, downRank, rateAverage }
      }
    }
"""


# -------------------------------------------------------------------------
# 10. isFollowingUser.
# -------------------------------------------------------------------------
IS_FOLLOWING_USER_QUERY = """
    query IsFollowingUser($token: String!, $username: String!) {
      isFollowingUser(token: $token, username: $username)
    }
"""


# -------------------------------------------------------------------------
# 11. notes — user notifications (the bell icon).
# -------------------------------------------------------------------------
NOTES_QUERY = """
    query NotesQuery($token: String!, $setRead: Boolean) {
      notes(token: $token, setRead: $setRead) {
        status
        items {
          type, icon, related_title, related_user, related_ads_num, pm_list_id,
          pay_value, status, date, viewType, viewTypeValue, city, searchKeyword,
          tag, thumbURL, displayTitle, displayBody, url, isActive
        }
      }
    }
"""


# -------------------------------------------------------------------------
# 12. sellersList — sellers for a tag (real estate, business).
# -------------------------------------------------------------------------
SELLERS_LIST_QUERY = """
    query SellersList($tags: [String]!, $page: Int) {
      sellersList(tags: $tags, page: $page) {
        items { userId, username, handler, aboutMe, contactRequestId }
        pageInfo { hasNextPage, hasPreviousPage }
      }
    }
"""


# -------------------------------------------------------------------------
# 13. getLockerShipmentOffer — Locker shipping fee quote.
# -------------------------------------------------------------------------
GET_LOCKER_SHIPMENT_OFFER_QUERY = """
    query GetLockerShipmentOffer($postId: Int!) {
      getLockerShipmentOffer(postId: $postId) { offerId, isEligible, price }
    }
"""


# -------------------------------------------------------------------------
# 14. postContact — contact info for a post.
# -------------------------------------------------------------------------
POST_CONTACT_QUERY = """
    query PostContactQuery($postId: Int!, $isManualRequest: Boolean) {
      postContact(postId: $postId, isManualRequest: $isManualRequest) {
        contactText, contactMobile, shouldEnableWhatsApp
      }
    }
"""


# -------------------------------------------------------------------------
# 15. followUser — mutation.
# -------------------------------------------------------------------------
FOLLOW_USER_MUTATION = """
    mutation FollowUser($token: String!, $username: String!) {
      followUser(token: $token, username: $username)
    }
"""


# -------------------------------------------------------------------------
# 16. submitGeoLocation — mutation (the "near me" consent).
# -------------------------------------------------------------------------
SUBMIT_GEO_LOCATION_MUTATION = """
    mutation SubmitGeoLocation($token: String!, $lat: Float!, $lon: Float!) {
      submitGeoLocation(token: $token, lat: $lat, lon: $lon)
    }
"""


# -------------------------------------------------------------------------
# 17. searchSuggest — live autocomplete. NOTE the typo `initalChars`.
# -------------------------------------------------------------------------
SEARCH_SUGGEST_QUERY = """
    query searchSuggest($initalChars: String!, $tag: String) {
      searchSuggest(initalChars: $initalChars, tag: $tag) { keywords }
    }
"""


# -------------------------------------------------------------------------
# 18. getTrendingKeywords.
# -------------------------------------------------------------------------
GET_TRENDING_KEYWORDS_QUERY = """
    query GetTrendingKeywords($rangeInDays: Int!) {
      getTrendingKeywords(rangeInDays: $rangeInDays) { keyword, score }
    }
"""


# -------------------------------------------------------------------------
# 19. getOutgoingBuyRequestsList — escrow history.
# -------------------------------------------------------------------------
GET_OUTGOING_BUY_REQUESTS_LIST_QUERY = """
    query GetOutgoingBuyRequestsList($page: Int) {
      getOutgoingBuyRequestsList(page: $page) {
        items {
          id, postId, postTitle, buyerUserId, buyerUsername, sellerUserId, sellerUsername,
          requestedAt, rejectedAt, acceptedAt, canceledAt, cancelationReason, rejectionReason,
          price, postPrice, shippingCost, commissionPercentage, requestWasataService,
          lockerShipmentOfferId, lockerShipmentSelected, totalPrice,
          paidAt, pickedAt, deliveredAt, disputeOpenedAt, returnRequestedAt, returnShippedAt,
          returnReceivedAt, refundIssuedAt, sellerCompensatedAt, payoutToSellerAt,
          arrivedAt, receivedAt, disputeClosedAt,
          shippingAddress, sellerIBAN, sellerIBANName, sellerIBANSwiftCode,
          buyerIBAN, buyerIBANName, status, statusLabel,
          statusHistory { status, changedAt, historyLabel },
          relatedActions, type
        }
        pageInfo { hasNextPage, hasPreviousPage }
      }
    }
"""


# -------------------------------------------------------------------------
# 20. getUserMentionSuggestions — for @-mention autocomplete.
# -------------------------------------------------------------------------
GET_USER_MENTION_SUGGESTIONS_QUERY = """
    query GetUserMentionSuggestions {
      getUserMentionSuggestions { userId, username, handler }
    }
"""