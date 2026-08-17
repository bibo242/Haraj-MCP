"""Pydantic models for haraj.com.sa Post objects.

Note: the original `BuyButton` class was renamed to `BuyButtonData` because
`BuyButton: Optional[BuyButton]` in `Post` shadows the class name in the
class namespace (the field lookup returns `None` from the field's own
default), causing pydantic to see the annotation as just `NoneType`.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class Price(BaseModel):
    formattedPrice: Optional[str] = None
    inputPrice: Optional[str] = None

    @property
    def numeric(self) -> Optional[float]:
        if self.inputPrice:
            try:
                return float(self.inputPrice.replace(",", ""))
            except ValueError:
                pass
        if self.formattedPrice:
            try:
                return float(self.formattedPrice.replace(",", ""))
            except ValueError:
                pass
        return None


class GeneralInfo(BaseModel):
    key: str
    value: str


class RealEstateInfo(BaseModel):
    re_REGA_Advertiser_registration_number: Optional[str] = None
    re_REGA_Authorization_number: Optional[str] = None


class CarInfo(BaseModel):
    sellOrWaiver: Optional[str] = None
    is4DW: Optional[Any] = None
    model: Optional[Any] = None
    mileage: Optional[Any] = None
    fuel: Optional[str] = None
    gear: Optional[str] = None
    condition: Optional[str] = None
    carOrRelated: Optional[str] = None
    Bank: Optional[str] = None


class JobsInfo(BaseModel):
    jobs_OfferType: Optional[str] = None
    jobs_ExperienceLevel: Optional[str] = None
    jobs_ContractType: Optional[str] = None
    jobs_Qualification: Optional[str] = None
    jobs_CommercialeRgisterNumber: Optional[str] = None


class PostNote(BaseModel):
    iconName: Optional[str] = None
    iconUrl: Optional[str] = None
    note: Optional[str] = None
    link: Optional[str] = None


class BuyButtonData(BaseModel):
    Link: Optional[str] = None
    StoreName: Optional[str] = None
    Name: Optional[str] = None
    canRequestWasataService: Optional[bool] = None
    isMakeOfferEnabled: Optional[bool] = None


class Post(BaseModel):
    id: int
    title: str
    postDate: int
    updateDate: int
    authorUsername: str
    authorId: int
    URL: str
    bodyTEXT: str = ""
    bodyHTML: str = ""
    thumbURL: Optional[str] = None
    hasImage: bool = False
    hasVideo: bool = False
    city: Optional[str] = None
    geoCity: Optional[str] = None
    geoNeighborhood: Optional[str] = None
    geoHash: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    imagesList: list[str] = Field(default_factory=list)
    commentEnabled: bool = True
    commentStatus: Optional[int] = None
    isPromoted: bool = False
    commentCount: int = 0
    upRank: int = 0
    downRank: int = 0
    status: bool = True
    postType: Optional[str] = None
    generalInfo: Optional[list[GeneralInfo]] = None
    price: Optional[Price] = None
    realEstateInfo: Optional[RealEstateInfo] = None
    carInfo: Optional[CarInfo] = None
    tagsFilters: list[str] = Field(default_factory=list)
    jobsInfo: Optional[JobsInfo] = None
    postNotesList: Optional[list[PostNote]] = None
    BuyButton: Optional[BuyButtonData] = None

    @field_validator("generalInfo", mode="before")
    @classmethod
    def _coerce_general_info(cls, v: Any) -> Any:
        if v is None:
            return None
        if not isinstance(v, list):
            return None
        seen: set[tuple[str, str]] = set()
        out = []
        for item in v:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            val = item.get("value")
            if key is None or val is None:
                continue
            pair = (key, val)
            if pair in seen:
                continue
            seen.add(pair)
            out.append({"key": key, "value": val})
        return out if out else None

    @field_validator("BuyButton", mode="before")
    @classmethod
    def _coerce_buy_button(cls, v: Any) -> Any:
        if isinstance(v, dict) and not v:
            return None
        return v

    @field_validator("postNotesList", mode="before")
    @classmethod
    def _coerce_post_notes(cls, v: Any) -> Any:
        if v is None:
            return None
        if not isinstance(v, list):
            return None
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, v: Any) -> Any:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return [str(t) for t in v if t is not None]

    @field_validator("imagesList", mode="before")
    @classmethod
    def _coerce_images(cls, v: Any) -> Any:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return [str(u) for u in v if u is not None]

    @property
    def web_url(self) -> str:
        return f"https://haraj.com.sa/{self.URL}"

    @property
    def price_sar(self) -> Optional[float]:
        return self.price.numeric if self.price else None

    @property
    def price_display(self) -> str:
        if not self.price or not self.price.formattedPrice:
            return "Contact for price"
        if self.price.formattedPrice.strip() in ("0", "0.0", ""):
            return "Contact for price"
        return f"{self.price.formattedPrice} SAR"

    @property
    def location_display(self) -> str:
        parts = [p for p in (self.geoNeighborhood, self.geoCity, self.city) if p]
        return "، ".join(parts) if parts else "Unknown"

    @property
    def general_specs(self) -> dict[str, str]:
        if not self.generalInfo:
            return {}
        return {g.key: g.value for g in self.generalInfo}

    def is_deal_candidate(self) -> bool:
        """Cheap pre-filter: must have price, image, and not be a promoted ad."""
        if not self.hasImage and not self.imagesList:
            return False
        if self.price_sar is None or self.price_sar <= 0:
            return False
        return True


class PageInfo(BaseModel):
    hasNextPage: bool = False


class ViewOptions(BaseModel):
    hasSellersList: bool = False
    # `mustLoginToView` is only present on the `posts` operation (homepage
    # tag feed). Absent from the `search` op. The live frontend uses it to
    # decide whether to render the "log in to see this post" gate.
    mustLoginToView: bool = False


class SearchResult(BaseModel):
    analyticsContext: Optional[str] = None
    items: list[Post] = Field(default_factory=list)
    pageInfo: PageInfo = Field(default_factory=PageInfo)
    viewOptions: ViewOptions = Field(default_factory=ViewOptions)


# ---------- Livestream (non-GraphQL REST) ----------

class LivestreamUser(BaseModel):
    id: int
    name: str = ""
    handler: str = ""


class LivestreamItem(BaseModel):
    id: int
    status: str = ""          # "OPEN" or "CLOSED"
    title: str = ""
    cover_url: str = ""
    streamer: Optional[LivestreamUser] = None
    num_messages: int = 0
    num_viewers: int = 0
    started_at: int = 0       # Unix seconds


class LivestreamPageInfo(BaseModel):
    has_next_page: bool = False
    next_last_key: str = ""


class LivestreamParams(BaseModel):
    last_key: str = ""
    limit: int = 0


class LivestreamData(BaseModel):
    streams: list[LivestreamItem] = Field(default_factory=list)
    params: LivestreamParams = Field(default_factory=LivestreamParams)
    page_info: LivestreamPageInfo = Field(default_factory=LivestreamPageInfo)


class LivestreamResponse(BaseModel):
    ok: bool
    data: Optional[LivestreamData] = None
    err: str = ""
    msg: str = ""
    ts: int = 0
