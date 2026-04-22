import contextlib
import threading

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import User


_thread_local = threading.local()


@contextlib.contextmanager
def suppress_version_push():
    """Context manager to prevent current_ver change signals from firing
    silent pushes. Used by management commands (e.g. `swap_versions --no-push`)
    and tests.
    """
    _thread_local.suppress_version_push = True
    try:
        yield
    finally:
        _thread_local.suppress_version_push = False


@receiver(pre_save, sender=User)
def _capture_original_current_ver(sender, instance, update_fields=None, **kwargs):
    if not instance.pk:
        instance._original_current_ver = None
        return
    if update_fields is not None and 'current_ver' not in update_fields:
        instance._original_current_ver = None
        return
    try:
        instance._original_current_ver = (
            User.objects.only('current_ver').get(pk=instance.pk).current_ver
        )
    except User.DoesNotExist:
        instance._original_current_ver = None


@receiver(post_save, sender=User)
def _notify_version_change(sender, instance, created, update_fields=None, **kwargs):
    if created:
        return
    if getattr(_thread_local, 'suppress_version_push', False):
        return
    if update_fields is not None and 'current_ver' not in update_fields:
        return
    original = getattr(instance, '_original_current_ver', None)
    if original is None or original == instance.current_ver:
        return

    new_ver = instance.current_ver
    ver_changed_at = (
        instance.ver_changed_at.isoformat() if instance.ver_changed_at else ""
    )

    def _dispatch():
        # Lazy import avoids any import-time cycle between account <-> custom_fcm.
        from custom_fcm.silent_push import send_version_change_push
        send_version_change_push(instance, new_ver, ver_changed_at)

    transaction.on_commit(_dispatch)
