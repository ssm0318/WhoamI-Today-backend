from note.models import ShareType
from note.serializers import NoteSerializer


def get_note_mission_id(note):
    return getattr(note, 'mission_id_id', None)


def get_mission_group_key(note):
    if note.share_type != ShareType.MISSION:
        return None

    mission_id = get_note_mission_id(note)
    if mission_id is not None:
        return ('mission_id', note.author_id, mission_id)

    if note.mission_prompt:
        return ('mission_prompt', note.author_id, note.mission_prompt)

    return None


def serialize_note_entries(notes, context, data_by_note_id=None, extra_by_note_id=None):
    entries = []
    data_by_note_id = data_by_note_id or {}
    extra_by_note_id = extra_by_note_id or {}

    for note in notes:
        data = data_by_note_id.get(note.id)
        if data is None:
            data = NoteSerializer(note, context=context).data
        data = dict(data)
        data.setdefault('mission_id', get_note_mission_id(note))
        entries.append({
            'note': note,
            'data': data,
            'extra': dict(extra_by_note_id.get(note.id, {})),
        })

    return entries


def serialize_mission_grouped_notes(notes, context, wrap_notes=False, data_by_note_id=None, extra_by_note_id=None):
    entries = serialize_note_entries(
        notes,
        context=context,
        data_by_note_id=data_by_note_id,
        extra_by_note_id=extra_by_note_id,
    )
    return group_note_entries(entries, wrap_notes=wrap_notes)


def group_note_entries(entries, wrap_notes=False):
    results = []
    pending_group = []
    pending_key = None

    def flush_group():
        nonlocal pending_group, pending_key
        if pending_group:
            results.append(build_mission_group(pending_group))
            pending_group = []
            pending_key = None

    for entry in entries:
        key = get_mission_group_key(entry['note'])
        if key is None:
            flush_group()
            results.append(wrap_note_entry(entry, wrap_notes=wrap_notes))
            continue

        if pending_key is not None and key != pending_key:
            flush_group()

        pending_key = key
        pending_group.append(entry)

    flush_group()
    return results


def wrap_note_entry(entry, wrap_notes=False):
    if wrap_notes:
        result = {
            'type': 'Note',
            'body': entry['data'],
        }
        result.update(entry['extra'])
        return result

    result = dict(entry['data'])
    result.update(entry['extra'])
    return result


def build_mission_group(entries):
    attempts = sorted(entries, key=attempt_sort_key)
    latest_entry = max(entries, key=latest_attempt_sort_key)
    latest_data = latest_entry['data']

    mission_id = next(
        (get_note_mission_id(entry['note']) for entry in attempts if get_note_mission_id(entry['note']) is not None),
        None,
    )
    mission_prompt = next(
        (entry['note'].mission_prompt for entry in attempts if entry['note'].mission_prompt),
        None,
    )

    group = {
        'type': 'MissionGroup',
        'mission_id': mission_id,
        'mission_prompt': mission_prompt,
        'author': latest_data.get('author'),
        'author_detail': latest_data.get('author_detail'),
        'created_at': latest_data.get('created_at'),
        'updated_at': latest_data.get('updated_at'),
        'attempts': [entry['data'] for entry in attempts],
    }
    group.update(latest_entry['extra'])
    return group


def attempt_sort_key(entry):
    note = entry['note']
    attempt_number = note.mission_attempt_number
    return (
        attempt_number is None,
        attempt_number or 0,
        note.created_at,
        note.id,
    )


def latest_attempt_sort_key(entry):
    note = entry['note']
    return note.created_at, note.id
