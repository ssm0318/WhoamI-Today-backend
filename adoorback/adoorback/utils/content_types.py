from django.contrib.contenttypes.models import ContentType


def get_user_type():
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return ContentType.objects.get_for_model(User)


def get_friend_request_type():
    from account.models import FriendRequest
    return ContentType.objects.get_for_model(FriendRequest)


def get_comment_type():
    from comment.models import Comment
    return ContentType.objects.get_for_model(Comment)


def get_like_type():
    from like.models import Like
    return ContentType.objects.get_for_model(Like)


def get_question_type():
    from qna.models import Question
    return ContentType.objects.get_for_model(Question)


def get_response_type():
    from qna.models import Response
    return ContentType.objects.get_for_model(Response)


def get_response_request_type():
    from qna.models import ResponseRequest
    return ContentType.objects.get_for_model(ResponseRequest)


def get_user_tag_type():
    from user_tag.models import UserTag
    return ContentType.objects.get_for_model(UserTag)


def get_reaction_type():
    from reaction.models import Reaction
    return ContentType.objects.get_for_model(Reaction)


def get_note_type():
    from note.models import Note
    return ContentType.objects.get_for_model(Note)


def get_reaction_type():
    from reaction.models import Reaction
    return ContentType.objects.get_for_model(Reaction)


def get_generic_relation_type(model):
    model = model.capitalize()
    if model == 'Comment':
        return get_comment_type()
    elif model == 'Response':
        return get_response_type()
    elif model == 'Question':
        return get_question_type()
    elif model == 'Note':
        return get_note_type()
    else:
        return None
