import threading
import logging
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _send_async(subject, message, from_email, recipient_list, **kwargs):
    try:
        send_mail(subject, message, from_email, recipient_list, fail_silently=True, **kwargs)
    except Exception as exc:
        logger.warning("Async email failed to %s: %s", recipient_list, exc)


def send_mail_async(subject, message, from_email, recipient_list, **kwargs):
    threading.Thread(
        target=_send_async,
        args=(subject, message, from_email, recipient_list),
        kwargs=kwargs,
        daemon=True,
    ).start()
