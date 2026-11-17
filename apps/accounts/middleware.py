from django.shortcuts import redirect


class ForcePasswordChangeMiddleware:
    """Send accounts that still have a temporary password to the change-password page."""

    ALLOWED_URL_NAMES = {'change-password', 'logout-view'}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None
        if not getattr(user, 'must_change_password', False):
            return None
        match = getattr(request, 'resolver_match', None)
        if match and match.url_name in self.ALLOWED_URL_NAMES:
            return None
        return redirect('change-password')
