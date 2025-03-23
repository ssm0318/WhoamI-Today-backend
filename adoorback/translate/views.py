from google.cloud import translate_v2 as translate
from translate.serializers import TranslateSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from adoorback.utils.validators import adoor_exception_handler


class TranslateV2(APIView):
  serializer_class = TranslateSerializer

  def get_exception_handler(self):
    return adoor_exception_handler

  def post(self, request):
    text = request.data.get("text")
    target_language = request.data.get("target_language")

    if not text or not target_language:
      return Response({"error": "Text and target language are required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
      # Create Translation API Client
      translate_client = translate.Client()

      # Translate Text
      result = translate_client.translate(text, target_language=target_language)
      return Response({"translatedText": result["translatedText"], "detectedSourceLanguage": result["detectedSourceLanguage"]})
    
    except Exception as e:
      return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
