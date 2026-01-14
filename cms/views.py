from django.shortcuts import redirect
from wagtail.views import serve as wagtail_serve


def root_or_app(request):
    response = wagtail_serve(request, path="")
    if response.status_code == 404:
        return redirect("/app/")
    return response
