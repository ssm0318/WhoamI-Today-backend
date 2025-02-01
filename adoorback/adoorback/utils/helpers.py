import csv
import os
import textwrap

from django.conf import settings


PARTICIPANT_CSV_PATH = os.path.join(settings.BASE_DIR, 'assets', 'participant_info.csv')


def wrap_content(content):
    content_as_string = str(content)
    wrap_result = textwrap.shorten(content_as_string, width=18, placeholder='...')
    if wrap_result != '...':
        return wrap_result
    return f'{content_as_string[:15].rstrip()}...'


def load_participant_info():
    participants = {}
    with open(PARTICIPANT_CSV_PATH, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            email = row['email'].strip().lower()
            user_group = row.get('user_group')
            if user_group == '1':
                current_ver = 'default'
                user_group_str = 'group_1'
            elif user_group == '2':
                current_ver = 'experiment'
                user_group_str = 'group_2'
            participants[email] = {
                'user_group': user_group_str,
                'current_ver': current_ver
            }
    return participants
