import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .chatbot import chat


def chat_page(request):
    return render(request, "agents/chat.html")


@require_POST
def chat_api(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON i pavlefshem"}, status=400)

    question = data.get("question", "").strip()
    if not question:
        return JsonResponse({"error": "Pyetja eshte boshe"}, status=400)
    if len(question) > 500:
        return JsonResponse({"error": "Pyetja shume e gjate (max 500 karaktere)"}, status=400)

    history = data.get("history", [])
    history = history[-6:] if len(history) > 6 else history

    result = chat(question, history)
    return JsonResponse(result)
