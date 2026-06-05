from django.shortcuts import render


def impressum(request):
    return render(request, "home/impressum.html")
