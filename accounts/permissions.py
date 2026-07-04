from rest_framework.permissions import BasePermission

class IsAdminRole(BasePermission):
    """
    يسمح بالدخول فقط للمستخدم المسجل والذي يمتلك رتبة 'admin'.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'admin')