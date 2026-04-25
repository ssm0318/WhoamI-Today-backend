from django.core.management.base import BaseCommand
from account.models import Interest, Persona, PERSONA_CHOICES, CHIPS_BY_CATEGORY
from django.db import IntegrityError

class Command(BaseCommand):
    help = 'Initialize Interest and Persona models with default choices'

    def handle(self, *args, **kwargs):
        # Initialize Persona
        persona_count = 0
        for _, value in PERSONA_CHOICES:
            # Format value: Remove spaces and special characters (like #) to make it PascalCase
            formatted_content = value.replace(' ', '').replace('#', '')
            try:
                persona, created = Persona.objects.get_or_create(content=formatted_content)
                if created:
                    persona_count += 1
            except IntegrityError:
                persona = Persona.objects.all_with_deleted().get(content=formatted_content)
                if persona.deleted:
                    persona.undelete()
                    persona_count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully initialized {persona_count} Persona instances.'))

        # Initialize Interest from CHIPS_BY_CATEGORY
        interest_count = 0
        for category, chips in CHIPS_BY_CATEGORY.items():
            for content in chips:
                try:
                    interest, created = Interest.objects.get_or_create(
                        content=content,
                        category=category,
                    )
                    if created:
                        interest_count += 1
                except IntegrityError:
                    interest = Interest.objects.all_with_deleted().get(content=content, category=category)
                    if interest.deleted:
                        interest.undelete()
                        interest_count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully initialized {interest_count} Interest instances.'))
