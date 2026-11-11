"""Typed MCP response schemas."""
from typing import Literal
from pydantic import BaseModel, Field


class CacheInfo(BaseModel):
    hit: bool
    age_seconds: float
    ttl_seconds: int

class Observation(BaseModel):
    observed_at: str | None = None
    cache: CacheInfo | None = None

class Delivery(BaseModel):
    status: Literal["available", "unavailable", "partial", "preorder", "unknown"]
    preorder: bool | None = None
    is_preorder: bool | None = None
    retailer_status: str | None
    retailer_code: str | None
    earliest: str | None

class Product(BaseModel):
    id: str | None
    title: str | None
    brand: str | None
    price: float | None
    currency: str | None
    url: str | None
    image: str | None = None
    type: str | None = None
    description: str | None = None
    delivery: Delivery
    preorder: bool | None = None
    is_preorder: bool | None = None
    variants: list["Variant"] | None = None
    marketplace_offers: list["Offer"] | None = None
    offers_coverage: str | None = None
    enrichment_error: str | None = None
    enrichment_error_code: str | None = None
    details_observed_at: str | None = None
    details_cache: CacheInfo | None = None

class Paging(BaseModel):
    current_page: int
    page_count: int | None
    max_page: int | None

class SearchResult(Observation):
    retailer: str
    country: str = "us"
    language: str = "en"
    query: str
    products: list[Product]
    count: int
    total_products: int | None
    page: int
    next_page: int | None
    paging: Paging
    source: str
    coverage: str
    redirected_url: str | None = None
    related_pages: list[str] | None = None
    local_filters: list[str] | None = None
    note: str | None = None
    tab: str | None = None

class Variant(BaseModel):
    product_id: str
    title: str | None
    variant_name: str | None
    variant_value: str | None
    url: str | None

class VariantPrice(BaseModel):
    part_number: str | None = None
    name: str | None = None
    label: str | None = None
    size: str | None = None
    color: str | None = None
    chip: str | None = None
    cpu_cores: int | None = None
    gpu_cores: int | None = None
    price: float | None
    currency: str | None = None
    url: str | None = None
    attributes: dict[str, str] = {}
    attribute_descriptions: dict[str, str] = {}

class Offer(BaseModel):
    offer_id: str
    product_id: str | None
    seller_id: str | None
    seller_name: str | None
    seller_rating: float | None
    price: float | None
    currency: str | None
    shipping_cost: float | None
    condition: str | None
    delivery: Delivery
    is_best_offer: bool | None

class Image(BaseModel):
    url: str
    alt: str | None

class Rating(BaseModel):
    average: float | None
    count: int | None
    scale: int | float | None

class Feature(BaseModel):
    name: str
    value: str | int | float | bool | None
    unit: str | None

class FeatureGroup(BaseModel):
    group: str | None
    items: list[Feature]

class ProductDetails(Product):
    ean: str | None
    resolved_url: str
    variants: list[Variant]
    marketplace_offers: list[Offer]
    offers_coverage: str
    description: str | None
    description_marketing: str | None
    images: list[Image]
    rating: Rating
    categories: list[str]
    features: list[FeatureGroup]
    variant_prices: list[VariantPrice] = []
    options: dict | None = None
    configuration_collections: list[str] = []

class ProductResult(Observation):
    retailer: str
    country: str = "us"
    language: str = "en"
    reference: str
    found: bool
    product: ProductDetails | None
    reason: str | None

class Address(BaseModel):
    street: str | None
    house_number: str | None
    postal_code: str | None
    city: str | None
    country: str | None

class Position(BaseModel):
    latitude: float | None
    longitude: float | None

class Store(BaseModel):
    id: str
    name: str | None
    url: str | None = None
    region: str | None = None
    address: Address
    position: Position
    phone: str | None

class StoreResult(Observation):
    retailer: str
    country: str = "us"
    language: str = "en"
    query: str
    stores: list[Store]
    count: int

class Storefront(BaseModel):
    country: str
    retailer: str
    languages: list[str]
    default_language: str
    currency: str
    url: str
    delivery_filter_languages: list[str]

class SitemapLink(BaseModel):
    title: str
    url: str

class SitemapResult(Observation):
    retailer: str
    country: str = "us"
    language: str = "en"
    query: str | None = None
    links: list[SitemapLink]
    count: int

class StorefrontList(BaseModel):
    storefronts: list[Storefront]

class ConfigurationChoice(BaseModel):
    value: str = Field(description="Apple's option identifier; pass it as a selection value.")
    category: Literal["compatible", "upgrade"] = Field(description="Compatible with the current selection, or an upgrade that may require other changes.")
    price_delta: float | None = Field(description="Change relative to the returned selected configuration, in its currency; null if Apple did not provide it.")
    display_price_delta: str | None
    selected: bool | None
    default: bool | None
    blocked: bool | None

class ConfigurationDimension(BaseModel):
    name: str
    description: str | None
    choices: list[ConfigurationChoice]

class ConfigurationResult(BaseModel):
    country: str
    language: str
    collection: str
    requested_selections: dict[str, str]
    selected_dimensions: dict[str, str | None]
    currency: str
    part_number: str | None
    container_part_number: str | None
    product_configuration: dict[str, str]
    selected_price: float | None = Field(description="Apple's price for the returned selection, if supplied. Check the display text for qualifiers such as 'from'.")
    selected_price_display: str | None = Field(description="Apple's price text including any starting-price qualifier.")
    reset: bool | None
    observed_at: str
    dimensions: list[ConfigurationDimension]


class PickupQuote(BaseModel):
    part_number: str | None = None
    eligible: bool | None = Field(description="Apple pickup eligibility; this alone does not mean the item is in stock.")
    status: Literal["available", "unavailable", "ships_to_store", "unknown"] = Field(description="Normalized Apple pickup status; ships_to_store can require a wait.")
    display: str | None = Field(description="Original Apple pickup status code.")
    quote: str | None

class PickupStore(BaseModel):
    id: str | None
    name: str | None
    city: str | None
    availability: list[PickupQuote]

class FulfillmentResult(BaseModel):
    country: str
    language: str
    observed_at: str
    selected_dimensions: dict[str, str | None]
    configuration: ConfigurationResult = Field(description="Price, options and selected configuration used for the availability check.")
    location_scope: str
    note: str
    stores: list[PickupStore]

class BrowseChoice(BaseModel):
    name: str
    url: str

class BrowseOptionChoice(BaseModel):
    name: str
    value: str
    compatible: bool
    blocked: bool | None = None
    requires_changes: bool
    price_change: float | None

class BrowseOption(BaseModel):
    name: str
    selected: str | None
    choices: list[BrowseOptionChoice]

class BrowseIssue(BaseModel):
    stage: str
    code: str
    message: str

class BrowseResult(BaseModel):
    kind: Literal['choices', 'configuration', 'variants']
    url: str
    choices: list[BrowseChoice] = []
    variants: list[VariantPrice] = []
    currency: str | None = None
    price: float | None = None
    price_display: str | None = None
    selection: dict[str, str] = {}
    options: list[BrowseOption] = []
    observed_at: str | None = None
    location: str | None = None
    stores: list[PickupStore] | None = None
    availability_observed_at: str | None = None
    delivery: 'ConfigurationDeliveryEstimates | DeliveryEstimates | None' = None
    issues: list[BrowseIssue] = []

class DeliveryOption(BaseModel):
    method: str | None
    date: str | None
    latest_date: str | None = None
    shipping_cost: str | None

class ProductDeliveryEstimate(BaseModel):
    part_number: str
    product: str | None
    options: list[DeliveryOption]
    available: bool | None
    note: str | None

class DeliveryEstimates(BaseModel):
    country: str
    language: str
    postal_code: str
    observed_at: str
    products: list[ProductDeliveryEstimate]

class ConfigurationDeliveryEstimates(DeliveryEstimates):
    configuration: ConfigurationResult


class VariantPickupResult(BaseModel):
    country: str
    language: str
    location: str
    observed_at: str
    stores: list[PickupStore]

class StoreListEntry(BaseModel):
    id: str | None = None
    name: str
    url: str
    region: str | None

class AllStoresResult(BaseModel):
    country: str
    count: int
    stores: list[StoreListEntry]
    observed_at: str

class ComparisonError(BaseModel):
    stage: str
    input: str
    code: str
    message: str

class ComparedStore(PickupStore):
    observed_at: str
    queried_near: str

class MissingStore(BaseModel):
    id: str | None
    name: str

class MissingPart(BaseModel):
    store_id: str
    part_number: str

class UnknownDelivery(BaseModel):
    postal_code: str
    part_number: str

class ComparisonResult(BaseModel):
    country: str
    language: str
    part_numbers: list[str]
    observed_at: str
    pickup: list[ComparedStore]
    delivery: list[DeliveryEstimates]
    errors: list[ComparisonError]
    directory_checked: bool
    directory_store_count: int | None
    missing_stores: list[MissingStore]
    missing_parts: list[MissingPart]
    unknown_parts: list[MissingPart]
    unknown_delivery: list[UnknownDelivery]
    complete: bool
    note: str

class InformationPrice(BaseModel):
    amount: float
    currency: str
    kind: Literal['starting_at', 'change_from_example']
    display: str | None = None

class OptionRequirement(BaseModel):
    status: Literal['compatible', 'requires_changes', 'unavailable_or_unknown', 'observed_with']
    when: str
    price_change: InformationPrice | None = None
    dimension: str | None = None
    values: list[str] = []
    description: str

class InformationOption(BaseModel):
    name: str
    description: str | None = None
    price: InformationPrice | None
    requirements: list[OptionRequirement]

class InformationVariant(BaseModel):
    attributes: dict[str, str]
    attribute_descriptions: dict[str, str] = {}
    price: float | None = None
    price_display: str | None = None
    currency: str | None = None
    part_number: str | None = None

class ProductInformation(BaseModel):
    kind: Literal['choices', 'products', 'configuration']
    product: str
    country: str
    url: str
    observed_at: str
    currency: str | None = None
    choices: list[BrowseChoice] = []
    variants: list[InformationVariant] = []
    options: dict[str, list[InformationOption]] = {}
    example_configuration: dict[str, str] | None = None
    example_configurations: dict[str, dict[str, str]] = {}
    availability_configuration: dict[str, str] | None = None
    availability_observed_at: str | None = None
    stores: list[PickupStore] | None = None
    delivery: ConfigurationDeliveryEstimates | DeliveryEstimates | None = None
    issues: list[BrowseIssue] = []
    note: str | None = None
