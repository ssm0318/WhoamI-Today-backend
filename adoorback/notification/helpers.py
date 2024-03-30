import re

from django.core.exceptions import ValidationError

from adoorback.utils.content_types import get_comment_type, get_like_type, get_response_type, get_reaction_type, \
    get_note_type



def find_like_noti(user, origin, noti_type):
    from notification.models import Notification
    from comment.models import Comment

    existing_notifications = Notification.objects.filter(user=user, origin_id=origin.id, target_type=get_like_type())

    reply_ids = Comment.objects.filter(content_type=get_comment_type()). \
        values_list('id', flat=True)

    if noti_type == "like_reply_noti":
        existing_notifications = existing_notifications.filter(origin_type=get_comment_type(), origin_id__in=reply_ids)
    elif noti_type == "like_comment_noti":
        existing_notifications = existing_notifications.filter(origin_type=get_comment_type()).exclude(
            origin_id__in=reply_ids)
    elif noti_type == "like_response_noti":
        existing_notifications = existing_notifications.filter(origin_type=get_response_type())
    elif noti_type == "like_note_noti":
        existing_notifications = existing_notifications.filter(origin_type=get_note_type())

    if existing_notifications.count() > 1:
        raise ValidationError("There are more than one notifications that satisfy this condition.")

    return existing_notifications.first()


def construct_message(noti_type, user_a_ko, user_b_ko, user_a_en, user_b_en, N, content_preview, emoji=None):
    if noti_type == "like_reply_noti" or noti_type == "like_comment_noti":
        if N == 1:
            return f'{user_a_ko}이 회원님의 댓글을 좋아합니다: {content_preview}', \
                f'{user_a_en} liked your comment: {content_preview}'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 댓글을 좋아합니다: {content_preview}', \
                f'{user_a_en} and {user_b_en} liked your comment: {content_preview}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구가 회원님의 댓글을 좋아합니다: {content_preview}', \
                f'{user_a_en}, {user_b_en}, and {N - 2} other friend(s) liked your comment: {content_preview}'
    elif noti_type == "like_response_noti":
        if N == 1:
            return f'{user_a_ko}이 회원님의 답변을 좋아합니다: {content_preview}', \
                f'{user_a_en} liked your response: {content_preview}'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 답변을 좋아합니다: {content_preview}', \
                f'{user_a_en} and {user_b_en} liked your response: {content_preview}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구가 회원님의 답변을 좋아합니다: {content_preview}', \
                f'{user_a_en}, {user_b_en}, and {N - 2} other friend(s) liked your response: {content_preview}'
    elif noti_type == "like_note_noti":
        if N == 1:
            return f'{user_a_ko}이 회원님의 노트를 좋아합니다: {content_preview}', \
                f'{user_a_en} liked your note: {content_preview}'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 노트를 좋아합니다: {content_preview}', \
                f'{user_a_en} and {user_b_en} liked your note: {content_preview}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 1}명의 친구가 회원님의 노트를 좋아합니다: {content_preview}', \
                f'{user_a_en}, {user_b_en}, and {N - 1} other friend(s) liked your note: {content_preview}'
    elif noti_type == "response_request_noti":
        if N == 1:
            return f'똑똑똑! {user_a_ko}으로부터 질문이 왔어요: {content_preview}', \
                f'Knock knock! {user_a_en} has sent you a question: {content_preview}'
        elif N == 2:
            return f'똑똑똑! {user_a_ko}과 {user_b_ko}으로부터 질문이 왔어요: {content_preview}', \
                f'Knock knock! {user_a_en} and {user_b_en} have sent you a question: {content_preview}'
        else:
            return f'똑똑똑! {user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구로부터 질문이 왔어요: {content_preview}', \
                f'Knock knock! {user_a_en}, {user_b_en}, and {N - 2} other friend(s) have sent you a question: {content_preview}'
    elif noti_type == "reaction_response_noti":
        if N == 1:
            return f'{user_a_ko}이 회원님의 답변에 {emoji} 반응을 남겼습니다: {content_preview}', \
                f'{user_a_en} reacted with {emoji} to your response: {content_preview}'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 답변에 {emoji} 반응을 남겼습니다: {content_preview}', \
                f'{user_a_en} and {user_b_en} reacted with {emoji} to your response: {content_preview}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구가 회원님의 답변에 {emoji} 반응을 남겼습니다: {content_preview}', \
                f'{user_a_en}, {user_b_en}, and {N - 2} other friend(s) reacted with {emoji} to your response: {content_preview}'
