from modeltranslation.translator import TranslationOptions, translator

from surveys.models import Survey, SurveyOption, SurveyQuestion


class SurveyTranslationOptions(TranslationOptions):
    fields = ('title', 'description', 'interpretation')
    required_languages = ('ko', 'en')


class SurveyQuestionTranslationOptions(TranslationOptions):
    fields = (
        'prompt',
        'low_label',
        'high_label',
        # New translatable fields for the long-form study extensions.
        'description',
        'placeholder',
        'min_length_warning',
        'na_option',
        'content',
    )
    # Only the original three fields require both languages. The long-form
    # study YAML is authored en-first; ko is backfilled later, and most
    # display_only blocks / placeholders / N/A labels never need ko.
    required_languages = {
        'en': ('prompt', 'low_label', 'high_label'),
        'ko': ('prompt', 'low_label', 'high_label'),
    }


class SurveyOptionTranslationOptions(TranslationOptions):
    fields = ('label',)
    required_languages = ('ko', 'en')


translator.register(Survey, SurveyTranslationOptions)
translator.register(SurveyQuestion, SurveyQuestionTranslationOptions)
translator.register(SurveyOption, SurveyOptionTranslationOptions)
