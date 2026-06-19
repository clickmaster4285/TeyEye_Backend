import requests
from user_agents import parse
from .models import UserActivityLog


# Paths we don't log (e.g. report endpoint to avoid duplicate entries, or health checks)
SKIP_LOG_PATHS = ("/api/activity-logs/report/", "/api/activity-logs/report", "/favicon.ico")


def get_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_device_info(request):
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    parsed = parse(user_agent)
    device = "Mobile" if parsed.is_mobile else "PC"
    os_str = parsed.os.family or ""
    browser = parsed.browser.family or ""
    return device, os_str, browser


def get_geo(ip):
    if not ip or ip in ("127.0.0.1", "127.0.1", "localhost"):
        return "Pakistan", "Local"
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}", timeout=2)
        if r.ok:
            j = r.json()
            return j.get("country"), j.get("city")
    except Exception:
        pass
    return None, None


def create_activity_log(user, request, action):
    ip = get_ip(request)
    device, os_str, browser = get_device_info(request)
    country, city = get_geo(ip)
    UserActivityLog.objects.create(
        user=user,
        ip_address=ip,
        country=country,
        city=city,
        device=device,
        os=os_str,
        browser=browser,
        action=action[:255],
    )


class ActivityLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated:
            path = request.path.rstrip("/") or "/"
            if any(path.startswith(p.rstrip("/")) for p in SKIP_LOG_PATHS):
                return response
            action = f"{request.method} {path}"
            create_activity_log(request.user, request, action)

        return response