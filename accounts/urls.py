from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("register/done/", views.register_done, name="register_done"),
    path("pending/", views.pending_view, name="pending"),
    path("people/", views.UserDirectoryView.as_view(), name="users"),
    path("people/<int:pk>/approve/", views.approve_user, name="approve_user"),
    path("people/<int:pk>/approval/", views.set_approval, name="set_approval"),
    path("people/<int:pk>/role/", views.set_role, name="set_role"),
]
