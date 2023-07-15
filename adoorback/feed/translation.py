from modeltranslation.translator import translator, TranslationOptions
from .models import Question

class QuestionTranslationOptions(TranslationOptions):
    fields = ('content',)
    required_languages = ('ko', 'en',)

translator.register(Question, QuestionTranslationOptions)
