from itertools import chain
import re

from django.contrib.auth import get_user_model

from adoorback.utils.validators import USERNAME_REGEX
from chat.models import UserChatActivity

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


def update_last_read_message(user, chat_room):
    last_message = chat_room.messages.last()
    user_activity, _ = UserChatActivity.objects.get_or_create(user=user, chat_room=chat_room)
    user_activity.last_read_message = last_message
    user_activity.save()

    return
