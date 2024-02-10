import re

from django.core.exceptions import ValidationError

from adoorback.utils.content_types import get_comment_type, get_like_type, get_response_type, get_reaction_type


def parse_message_ko(msg, actor_count):
    print(msg, actor_count)
    if actor_count > 2:
        pattern_c = re.compile(
            r"똑똑똑! (\w+)님, (\w+)님, 외 (\d+)명의 친구로부터 질문이 왔어요|"
            r"(\w+)님, (\w+)님, 외 (\d+)명의 친구가 회원님의 (댓글을|답변을) 좋아합니다|"
            r"(\w+)님, (\w+)님, 외 (\d+)명의 친구가 회원님의 답변에 .+ 반응을 남겼습니다"
        )
        match_c = pattern_c.search(msg)
        return {
            'user_a': match_c.group(1) or match_c.group(4) or match_c.group(7),
            'user_b': match_c.group(2) or match_c.group(5) or match_c.group(8)
        }

    if actor_count == 2:
        pattern_b = re.compile(
            r"똑똑똑! (\w+)님과 (\w+)님으로부터 질문이 왔어요|"
            r"(\w+)님과 (\w+)님이 회원님의 (댓글을|답변을) 좋아합니다|"
            r"(\w+)님과 (\w+)님이 회원님의 답변에 .+ 반응을 남겼습니다"
        )
        match_b = pattern_b.search(msg)
        return {
            'user_a': match_b.group(1) or match_b.group(3) or match_b.group(6),
            'user_b': match_b.group(2) or match_b.group(4) or match_b.group(7)
        }

    if actor_count == 1:
        pattern_a = re.compile(
            r"똑똑똑! (\w+)님으로부터 질문이 왔어요|"
            r"(\w+)님이 회원님의 (댓글을|답변을) 좋아합니다|"
            r"(\w+)님이 회원님의 답변에 .+ 반응을 남겼습니다"
        )
        match_a = pattern_a.search(msg)
        return {
            'user_a': match_a.group(1) or match_a.group(2) or match_a.group(4),
            'user_b': None
        }

    return {'user_a': None, 'user_b': None}


def parse_message_en(msg, actor_count):
    if actor_count > 2:
        pattern_c = re.compile(r"(Knock knock! |)(\w+), (\w+), and (\d+) other friend\(s\)")
        match_c = pattern_c.search(msg)
        return {
            'user_a': match_c.group(2),
            'user_b': match_c.group(3)
        }

    if actor_count == 2:
        pattern_b = re.compile(r"(Knock knock! |)(\w+) and (\w+) (have sent|liked your|reacted with)")
        match_b = pattern_b.search(msg)
        return {
            'user_a': match_b.group(2),
            'user_b': match_b.group(3)
        }

    if actor_count == 1:
        pattern_a = re.compile(r"(Knock knock! |)(\w+) (has sent|liked your|reacted with)")
        match_a = pattern_a.search(msg)
        return {
            'user_a': match_a.group(2) or match_a.group(4),
            'user_b': None
        }

    return {'user_a': None, 'user_b': None}


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
    elif noti_type == "reaction_response_noti":
        existing_notifications = existing_notifications.filter(origin_type=get_reaction_type())

    if existing_notifications.count() > 1:
        raise ValidationError("There are more than one notifications that satisfy this condition.")

    return existing_notifications.first()


def construct_message(noti_type, user_a_ko, user_b_ko, user_a_en, user_b_en, N, content_preview, emoji=None):
    if noti_type == "like_reply_noti" or noti_type == "like_comment_noti":
        if N == 0:
            return f'{user_a_ko}이 회원님의 댓글을 좋아합니다: {content_preview}', \
                f'{user_a_en} liked your comment: {content_preview}'
        elif N == 1:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 댓글을 좋아합니다: {content_preview}', \
                f'{user_a_en} and {user_b_en} liked your comment: {content_preview}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 1}명의 친구가 회원님의 댓글을 좋아합니다: {content_preview}', \
                f'{user_a_en}, {user_b_en}, and {N - 1} other friend(s) liked your comment: {content_preview}'
    elif noti_type == "like_response_noti":
        if N == 0:
            return f'{user_a_ko}이 회원님의 답변을 좋아합니다: {content_preview}', \
                f'{user_a_en} liked your response: {content_preview}'
        elif N == 1:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 답변을 좋아합니다: {content_preview}', \
                f'{user_a_en} and {user_b_en} liked your response: {content_preview}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 1}명의 친구가 회원님의 답변을 좋아합니다: {content_preview}', \
                f'{user_a_en}, {user_b_en}, and {N - 1} other friend(s) liked your response: {content_preview}'
    elif noti_type == "response_request_noti":
        if N == 0:
            return f'똑똑똑! {user_a_ko}으로부터 질문이 왔어요: {content_preview}', \
                f'Knock knock! {user_a_en} has sent you a question: {content_preview}'
        elif N == 1:
            return f'똑똑똑! {user_a_ko}과 {user_b_ko}으로부터 질문이 왔어요: {content_preview}', \
                f'Knock knock! {user_a_en} and {user_b_en} have sent you a question: {content_preview}'
        else:
            return f'똑똑똑! {user_a_ko}, {user_b_ko}, 외 {N - 1}명의 친구로부터 질문이 왔어요: {content_preview}', \
                f'Knock knock! {user_a_en}, {user_b_en}, and {N - 1} other friend(s) have sent you a question: {content_preview}'
    elif noti_type == "reaction_response_noti":
        if N == 0:
            return f'{user_a_ko}이 회원님의 답변에 {emoji} 반응을 남겼습니다: {content_preview}', \
                f'{user_a_en} reacted with {emoji} to your response: {content_preview}'
        elif N == 1:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 답변에 {emoji} 반응을 남겼습니다: {content_preview}', \
                f'{user_a_en} and {user_b_en} reacted with {emoji} to your response: {content_preview}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 1}명의 친구가 회원님의 답변에 {emoji} 반응을 남겼습니다: {content_preview}', \
                f'{user_a_en}, {user_b_en}, and {N - 1} other friend(s) reacted with {emoji} to your response: {content_preview}'
