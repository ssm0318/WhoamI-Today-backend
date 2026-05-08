import re

from django.core.exceptions import ValidationError

from adoorback.utils.content_types import get_comment_type, get_like_type, get_response_type, get_reaction_type, \
    get_note_type, get_check_in_post_type



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
    elif noti_type in ("like_note_noti", "like_mission_note_noti"):
        existing_notifications = existing_notifications.filter(origin_type=get_note_type())
    elif noti_type == "like_check_in_post_noti":
        existing_notifications = existing_notifications.filter(origin_type=get_check_in_post_type())

    if existing_notifications.count() > 1:
        raise ValidationError("There are more than one notifications that satisfy this condition.")

    return existing_notifications.first()


COMPONENT_LABELS_KO = {
    'battery': '소셜 배터리',
    'mood': '기분',
    'thought': '한마디',
    'song': '노래',
}
COMPONENT_LABELS_EN = {
    'battery': 'social battery',
    'mood': 'mood',
    'thought': 'thought snippet',
    'song': 'song',
}


def construct_message(noti_type, user_a_ko, user_b_ko, user_a_en, user_b_en, N, content_en, content_ko, emoji=None, component=None):
    if noti_type == "like_reply_noti" or noti_type == "like_comment_noti":
        if N == 1:
            return f'{user_a_ko}이 회원님의 댓글을 좋아합니다: {content_ko}', \
                f'{user_a_en} liked your comment: {content_en}'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 댓글을 좋아합니다: {content_ko}', \
                f'{user_a_en} and {user_b_en} liked your comment: {content_en}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구가 회원님의 댓글을 좋아합니다: {content_ko}', \
                f'{user_a_en}, {user_b_en}, and {N - 2} other friend(s) liked your comment: {content_en}'
    elif noti_type == "like_response_noti":
        if N == 1:
            return f'{user_a_ko}이 회원님의 답변을 좋아합니다: {content_ko}', \
                f'{user_a_en} liked your response: {content_en}'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 답변을 좋아합니다: {content_ko}', \
                f'{user_a_en} and {user_b_en} liked your response: {content_en}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구가 회원님의 답변을 좋아합니다: {content_ko}', \
                f'{user_a_en}, {user_b_en}, and {N - 2} other friend(s) liked your response: {content_en}'
    elif noti_type == "like_note_noti":
        if N == 1:
            return f'{user_a_ko}이 회원님의 게시글을 좋아합니다: {content_ko}', \
                f'{user_a_en} liked your post: {content_en}'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 게시글을 좋아합니다: {content_ko}', \
                f'{user_a_en} and {user_b_en} liked your post: {content_en}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구가 회원님의 게시글을 좋아합니다: {content_ko}', \
                f'{user_a_en}, {user_b_en}, and {N - 2} other friend(s) liked your post: {content_en}'
    elif noti_type == "like_mission_note_noti":
        if N == 1:
            return f'{user_a_ko}이 회원님의 미션 응답을 좋아합니다', \
                f'{user_a_en} liked your mission response'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 미션 응답을 좋아합니다', \
                f'{user_a_en} and {user_b_en} liked your mission response'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구가 회원님의 미션 응답을 좋아합니다', \
                f'{user_a_en}, {user_b_en}, and {N - 2} other friend(s) liked your mission response'
    elif noti_type == "like_check_in_post_noti":
        if N == 1:
            return f'{user_a_ko}이 회원님의 데일리 스니펫을 좋아합니다', \
                f'{user_a_en} liked your daily snippet'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 데일리 스니펫을 좋아합니다', \
                f'{user_a_en} and {user_b_en} liked your daily snippet'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구가 회원님의 데일리 스니펫을 좋아합니다', \
                f'{user_a_en}, {user_b_en}, and {N - 2} other friend(s) liked your daily snippet'
    elif noti_type == "response_request_noti":
        if N == 1:
            return f'똑똑똑! {user_a_ko}으로부터 질문이 왔어요: {content_ko}', \
                f'Knock knock! {user_a_en} has sent you a question: {content_en}'
        elif N == 2:
            return f'똑똑똑! {user_a_ko}과 {user_b_ko}으로부터 질문이 왔어요: {content_ko}', \
                f'Knock knock! {user_a_en} and {user_b_en} have sent you a question: {content_en}'
        else:
            return f'똑똑똑! {user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구로부터 질문이 왔어요: {content_ko}', \
                f'Knock knock! {user_a_en}, {user_b_en}, and {N - 2} other friend(s) have sent you a question: {content_en}'
    elif noti_type == "reaction_response_noti":
        if N == 1:
            return f'{user_a_ko}이 회원님의 답변에 {emoji} 반응을 남겼습니다: {content_ko}', \
                f'{user_a_en} reacted with {emoji} to your response: {content_en}'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 답변에 반응을 남겼습니다: {content_ko}', \
                f'{user_a_en} and {user_b_en} reacted to your response: {content_en}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구가 회원님의 답변에 {emoji} 반응을 남겼습니다: {content_ko}', \
                f'{user_a_en}, {user_b_en}, and {N - 2} other friend(s) reacted with {emoji} to your response: {content_en}'
    elif noti_type == "reaction_mission_note_noti":
        if N == 1:
            return f'{user_a_ko}이 회원님의 미션 응답에 {emoji} 반응을 남겼습니다', \
                f'{user_a_en} reacted with {emoji} to your mission response'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 미션 응답에 반응을 남겼습니다', \
                f'{user_a_en} and {user_b_en} reacted to your mission response'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구가 회원님의 미션 응답에 {emoji} 반응을 남겼습니다', \
                f'{user_a_en}, {user_b_en}, and {N - 2} other friend(s) reacted with {emoji} to your mission response'
    elif noti_type == "reaction_checkin_noti":
        comp_ko = COMPONENT_LABELS_KO.get(component, '체크인')
        comp_en = COMPONENT_LABELS_EN.get(component, 'check-in')
        if N == 1:
            return f'{user_a_ko}이 회원님의 {comp_ko}에 {emoji} 반응을 남겼습니다', \
                f'{user_a_en} reacted with {emoji} to your {comp_en}'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 {comp_ko}에 {emoji} 반응을 남겼습니다', \
                f'{user_a_en} and {user_b_en} reacted with {emoji} to your {comp_en}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구가 회원님의 {comp_ko}에 {emoji} 반응을 남겼습니다', \
                f'{user_a_en}, {user_b_en}, and {N - 2} other friend(s) reacted with {emoji} to your {comp_en}'
    elif noti_type == "reaction_comment_noti":
        if N == 1:
            return f'{user_a_ko}이 회원님의 댓글에 반응을 남겼습니다: {content_ko}', \
                f'{user_a_en} reacted to your comment: {content_en}'
        elif N == 2:
            return f'{user_a_ko}과 {user_b_ko}이 회원님의 댓글에 반응을 남겼습니다: {content_ko}', \
                f'{user_a_en} and {user_b_en} reacted to your comment: {content_en}'
        else:
            return f'{user_a_ko}, {user_b_ko}, 외 {N - 2}명의 친구가 회원님의 댓글에 반응을 남겼습니다: {content_ko}', \
                f'{user_a_en}, {user_b_en}, and {N - 2} other friend(s) reacted to your comment: {content_en}'
