from itertools import chain
import re

from django.contrib.auth import get_user_model

from adoorback.utils.validators import USERNAME_REGEX

User = get_user_model()


def parse_user_tag_from_content(content):
    tagged_users = User.objects.none()
    word_indices = []
    if not '@' in content:
        return tagged_users, word_indices

    words = content.split(' ')
    for i, word in enumerate(words):
        if len(word) == 0 or word[0] != '@':
            continue

        # cut username by regex (exclude unallowed characters)
        tagged_username = re.compile(USERNAME_REGEX[1:-2]).match(word[1:]).group()
        try:
            tagged_users = list(chain(tagged_users, User.objects.filter(username=tagged_username)))
            word_indices.append(i)
        except User.DoesNotExist:
            continue

    return tagged_users, word_indices
