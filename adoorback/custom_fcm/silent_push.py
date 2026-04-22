import traceback
from typing import Optional

from firebase_admin.messaging import (
    AndroidConfig,
    APNSConfig,
    APNSPayload,
    Aps,
    Message,
)
from firebase_admin._messaging_utils import UnregisteredError

from adoorback.utils.alerts import send_msg_to_slack

from .models import CustomFCMDevice


def send_version_change_push(
    user,
    new_ver: str,
    ver_changed_at: Optional[str] = None,
) -> int:
    """Send a data-only silent push to every active device for `user`.

    Data-only means no `notification=` field — required for iOS to honor
    `content-available: 1` and wake the app in the background without
    showing UI. On Android, `priority=high` wakes the app promptly even
    in Doze.

    Returns the number of devices successfully dispatched to.
    """
    devices = CustomFCMDevice.objects.filter(user_id=user.id, active=True)
    data = {
        "type": "version_change",
        "new_ver": new_ver,
        "ver_changed_at": ver_changed_at or "",
        "content-available": "1",
        "priority": "high",
    }
    sent = 0
    for device in devices:
        message = Message(
            data=data,
            android=AndroidConfig(priority="high"),
            apns=APNSConfig(
                headers={
                    "apns-push-type": "background",
                    "apns-priority": "5",
                },
                payload=APNSPayload(aps=Aps(content_available=True)),
            ),
        )
        try:
            device.send_message(message)
            sent += 1
        except UnregisteredError:
            device.active = False
            device.save()
        except Exception as e:
            stack_trace = traceback.format_exc()
            send_msg_to_slack(
                text=(
                    f"🚨 Failed to send silent version-change push to device "
                    f"{device.id} (user {user.id}): {e}\n```{stack_trace}```"
                ),
                level="ERROR",
            )
            print(
                f"🚨 Failed to send silent version-change push to device "
                f"{device.id}: {e}\n{stack_trace}"
            )
    return sent
