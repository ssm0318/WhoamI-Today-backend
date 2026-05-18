import random
from account.models import User

# Words that do NOT overlap with load_users_from_csv.ADJECTIVES/NOUNS,
# all lowercase, no digits.
FRESH_ADJECTIVES = [
    'amber', 'azure', 'blushing', 'breezy', 'cinder', 'cosmic', 'crisp',
    'dappled', 'dewy', 'dusk', 'earthy', 'ebony', 'fleece', 'frosted',
    'glacier', 'glowing', 'golden', 'hazy', 'hollow', 'indigo', 'ivory',
    'jade', 'juniper', 'keen', 'lavender', 'lunar', 'misty', 'mossy',
    'neon', 'nimble', 'opal', 'onyx', 'pastel', 'pewter', 'petal',
    'quaint', 'radiant', 'raven', 'russet', 'sable', 'sandy', 'silky',
    'tawny', 'teal', 'topaz', 'umber', 'velvet', 'verdant', 'wistful',
    'woven',
]

FRESH_NOUNS = [
    'acorn', 'agate', 'aspen', 'beacon', 'birch', 'bison', 'canyon',
    'clover', 'cress', 'daisy', 'delta', 'dune', 'elder', 'ember',
    'fjord', 'flax', 'geyser', 'glen', 'grove', 'harbor', 'heath',
    'heron', 'ibis', 'inlet', 'jasper', 'junco', 'kestrel', 'lagoon',
    'lark', 'marsh', 'mesa', 'nebula', 'newt', 'orbit', 'osprey',
    'pebble', 'pike', 'quail', 'quartz', 'ravine', 'robin', 'summit',
    'thrush', 'tundra', 'valley', 'vole', 'willow', 'wren', 'yarrow',
    'zenith',
]


def generate_unique_fake_username(used_usernames: set) -> str:
    """Return a lowercase adjective+noun username not in used_usernames or the DB."""
    for _ in range(1000):
        username = random.choice(FRESH_ADJECTIVES) + random.choice(FRESH_NOUNS)
        if username not in used_usernames and not User.objects.filter(username=username).exists():
            return username
    raise RuntimeError('Failed to generate a unique fake username after 1000 attempts')
