from modeltranslation.translator import TranslationOptions, translator

from surveys.models import Survey, SurveyOption, SurveyQuestion


class SurveyTranslationOptions(TranslationOptions):
    fields = ('title', 'description', 'interpretation')
    required_languages = ('ko', 'en')


class SurveyQuestionTranslationOptions(TranslationOptions):
    fields = ('prompt', 'low_label', 'high_label')
    required_languages = ('ko', 'en')


class SurveyOptionTranslationOptions(TranslationOptions):
    fields = ('label',)
    required_languages = ('ko', 'en')


translator.register(Survey, SurveyTranslationOptions)
translator.register(SurveyQuestion, SurveyQuestionTranslationOptions)
translator.register(SurveyOption, SurveyOptionTranslationOptions)
