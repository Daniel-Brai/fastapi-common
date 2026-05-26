from fastapi import Request

PROXY_HEADERS: list[str] = [
    "CF-Connecting-IP",  # Cloudflare single IP, most trustworthy
    "True-Client-IP",  # Akamai / Cloudflare Enterprise
    "Fastly-Client-IP",  # Fastly CDN
    "X-Azure-ClientIP",  # Azure Front Door
    "X-Real-IP",  # nginx
    "X-Client-IP",  # Apache mod_remoteip
    "X-Forwarded-For",  # Standard list; parsed specially below
]

PROXY_COUNT: int = 1


def check_if_path_excluded(paths: set[str], endpoint: str) -> bool:
    """
    Check if the request path matches any of the excluded paths.

    Parameters
    ----------
    paths
        A set of paths or path prefixes to exclude.  Exact matches or prefix matches will return
        True.
    endpoint
        The request path to check against the excluded paths.

    Returns
    -------
    bool
        True if the endpoint matches any of the excluded paths or prefixes, False otherwise.
    """

    return endpoint in paths or any(endpoint.startswith(prefix) for prefix in paths)


def get_client_ip(
    request: Request,
    *,
    proxy_headers: list[str] | None = None,
    trusted_proxies: list[str] | None = None,
    proxy_count: int | None = None,
) -> str | None:
    """
    Extract the real client IP address from a FastAPI / Starlette request.

    Parameters
    ----------
    request
        The incoming FastAPI/Starlette Request object.
    proxy_headers
        Ordered list of headers to check.  Defaults to PROXY_HEADERS.
        CDN-specific single-value headers (CF-Connecting-IP, X-Real-IP, …)
        are returned directly.  X-Forwarded-For is parsed as a comma-separated
        list.
    trusted_proxies
        Optional list of trusted proxy IP strings.  When provided and the
        last entry in X-Forwarded-For matches a trusted proxy, the IP at
        position ``-(proxy_count + 1)`` is used instead of the first entry.
    proxy_count
        Number of trusted proxy hops to skip in the X-Forwarded-For list.
        Defaults to PROXY_COUNT (1).

    Returns
    -------
    str | None
        The client IP string, or None if it cannot be determined.

    Examples
    --------
        # Direct connection
        get_client_ip(request)                           # → "203.0.113.1"

        # Behind one nginx proxy (X-Real-IP set by nginx)
        get_client_ip(request)                           # → "203.0.113.1"

        # Behind Cloudflare
        get_client_ip(request)                           # → CF-Connecting-IP value

        # X-Forwarded-For: "client, proxy1, proxy2" with trusted proxy2
        get_client_ip(request, trusted_proxies=["proxy2"], proxy_count=1)
    """

    headers = proxy_headers or PROXY_HEADERS
    hop_count = proxy_count if proxy_count is not None else PROXY_COUNT

    for header_name in headers:
        value = request.headers.get(header_name)
        if not value:
            continue

        if header_name == "X-Forwarded-For" and "," in value:
            ips = [ip.strip() for ip in value.split(",") if ip.strip()]
            if not ips:
                continue
            if trusted_proxies and ips[-1] in trusted_proxies:
                idx = -(1 + hop_count)
                if abs(idx) <= len(ips):
                    return ips[idx]

            return ips[0]

        return value.strip()

    if request.client and request.client.host:
        return request.client.host

    return None


def get_user_agent(request: Request) -> str:
    """
    Return the User-Agent header value, or 'Unknown' if absent.

        agent = get_user_agent(request)
    """
    return request.headers.get("User-Agent", "Unknown")


def get_request_id(request: Request) -> str | None:
    """
    Return a request ID from headers or None if not found.

    Checks common headers like X-Request-ID, X-Correlation-ID, etc.

        req_id = get_request_id(request)
    """
    for header in ["X-Request-ID", "X-Correlation-ID", "X-Trace-ID"]:
        value = request.headers.get(header)
        if value:
            return value.strip()

    return None
