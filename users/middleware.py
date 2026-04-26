from django.shortcuts import redirect


class SuperuserRedirectMiddleware:
    ALLOWED_PREFIXES = ('/admin/', '/accounts/', '/static/', '/media/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and request.user.is_superuser
            and not any(request.path.startswith(p) for p in self.ALLOWED_PREFIXES)
        ):
            return redirect('/admin/')
        return self.get_response(request)
