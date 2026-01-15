from django.http import Http404
from django.shortcuts import redirect
from wagtail.views import serve as wagtail_serve


def root_or_app(request):
    try:
        response = wagtail_serve(request, path="")
    except Http404:
        return redirect("/app/")
    if response.status_code == 404:
        return redirect("/app/")
    return response
