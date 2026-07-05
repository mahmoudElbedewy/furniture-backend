from .models import AdminNotification


def notify_admin(
    notification_type: str, related_object_id: str, message: str, buttons: list = None
) -> AdminNotification:
    """
    يسجل الإشعار في قاعدة البيانات فقط. الإرسال الفعلي لتليجرام
    بيحصل عن طريق الـ GitHub Actions bridge اللي بيسأل عن الإشعارات
    الجديدة كل فترة، عشان نتجنب مشاكل الشبكة الصادرة من HF.
    """
    notification = AdminNotification.objects.create(
        type=notification_type,
        related_object_id=str(related_object_id),
        message=message,
        buttons=buttons or [],
        sent_via_telegram=False,
    )
    return notification