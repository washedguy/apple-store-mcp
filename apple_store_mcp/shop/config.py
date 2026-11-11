"""Supported Apple Store storefronts."""
# country -> (host, currency, languages)
STOREFRONTS = {
    "us": ("www.apple.com", "USD", ("en",)),
    "de": ("www.apple.com", "EUR", ("de",)),
    "fr": ("www.apple.com", "EUR", ("fr",)),
    "it": ("www.apple.com", "EUR", ("it",)),
    "es": ("www.apple.com", "EUR", ("es",)),
    "nl": ("www.apple.com", "EUR", ("nl",)),
    "at": ("www.apple.com", "EUR", ("de",)),
    "uk": ("www.apple.com", "GBP", ("en",)),
    "jp": ("www.apple.com", "JPY", ("ja",)),
    "cn": ("www.apple.com.cn", "CNY", ("zh",)),
    "kr": ("www.apple.com", "KRW", ("ko",)),
    "au": ("www.apple.com", "AUD", ("en",)),
    "ca": ("www.apple.com", "CAD", ("en", "fr")),
    "mx": ("www.apple.com", "MXN", ("es",)),
    "br": ("www.apple.com", "BRL", ("pt",)),
    "sg": ("www.apple.com", "SGD", ("en",)),
    "my": ("www.apple.com", "MYR", ("en",)),
    "th": ("www.apple.com", "THB", ("th",)),
    "in": ("www.apple.com", "INR", ("en",)),
    "ae": ("www.apple.com", "AED", ("en",)),
    "sa": ("www.apple.com", "SAR", ("en",)),
    "tr": ("www.apple.com", "TRY", ("tr",)),
    "za": ("www.apple.com", "ZAR", ("en",)),
    "se": ("www.apple.com", "SEK", ("sv",)),
    "no": ("www.apple.com", "NOK", ("no",)),
    "dk": ("www.apple.com", "DKK", ("da",)),
    "fi": ("www.apple.com", "EUR", ("fi",)),
    "pl": ("www.apple.com", "PLN", ("pl",)),
    "cz": ("www.apple.com", "CZK", ("cs",)),
    "hu": ("www.apple.com", "HUF", ("hu",)),
    "pt": ("www.apple.com", "EUR", ("pt",)),
    "ie": ("www.apple.com", "EUR", ("en",)),
    "nz": ("www.apple.com", "NZD", ("en",)),
    "be": ("www.apple.com", "EUR", ("fr", "nl")),
    "ch": ("www.apple.com", "CHF", ("de", "fr")),
}


def path_prefix(country: str, language: str) -> str:
    """Return the URL path segment for search/shop pages, e.g. 'us', 'ch-de', 'be-fr'."""
    if country == "ca" and language == "fr":
        return "xf"
    if country in ("be", "ch"):
        return f"{country}-{language}"
    return country

def site_prefix(country: str, language: str) -> str:
    """Return the URL path segment for marketing and store-list pages, e.g. 'us', 'chde', 'befr'."""
    if country == "ca" and language == "fr":
        return "ca/fr"
    if country in ("be", "ch"):
        return f"{country}{language}"
    return country


def base_url(country: str, language: str) -> str:
    host, _, _ = STOREFRONTS[country]
    return f"https://{host}"


def cofr_config(base):
    return {}
