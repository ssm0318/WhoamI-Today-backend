"""Chat signals — wit_bot follow-ups, etc."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from chat.models import ChatRoom, Message, OnboardingScreenshot


@receiver(post_save, sender=OnboardingScreenshot)
def notify_participant_on_review(sender, instance, created, **kwargs):
    """When admin transitions a screenshot to approved/rejected, DM the
    participant via wit_bot. On reject, also bounce intent back to widget
    collection so they can re-upload."""
    if created or instance.status == 'pending':
        return

    from chat.wit_bot import ensure_wit_bot_user
    from chat.wit_admin import _ordered_pair
    from chat.wit_bot_copy import WIDGET_APPROVED_DM, WIDGET_REJECTED_DM_TEMPLATE, t

    bot = ensure_wit_bot_user()
    u1, u2 = _ordered_pair(instance.user, bot)
    room = ChatRoom.objects.filter(user1=u1, user2=u2, is_group=False).first()
    if room is None:
        return

    user = instance.user
    if instance.status == 'approved':
        Message.objects.create(
            chat_room=room, sender=bot, receiver=user,
            content=t(WIDGET_APPROVED_DM, user),
        )
    elif instance.status == 'rejected':
        lang = getattr(user, 'language', 'en') or 'en'
        no_reason = '어드민이 사유를 안 적었어' if lang == 'ko' else 'admin gave no reason'
        Message.objects.create(
            chat_room=room, sender=bot, receiver=user,
            content=t(WIDGET_REJECTED_DM_TEMPLATE, user).format(
                reason=instance.rejection_reason or no_reason
            ),
        )
        from chat import wit_bot_state as state_mod
        state = state_mod.get_or_create_state(instance.user)
        state_mod.set_intent(state, 'kickoff_widget', step=0)
