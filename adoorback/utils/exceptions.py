from rest_framework.exceptions import APIException


class BlockedUserTag(APIException):
    status_code = 400
    default_detail = "You cannot mention a user you blocked."
    default_code = "blocked_user_tag"


class BlockingUserTag(APIException):
    status_code = 400
    default_detail = "You cannot mention a user that blocked you."
    default_code = "blocking_user_tag"
    