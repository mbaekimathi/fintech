from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("switch-role/", views.switch_role, name="switch_role"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("register/done/", views.register_done, name="register_done"),
    path("pending/", views.pending_view, name="pending"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("people/", views.UserDirectoryView.as_view(), name="users"),
    path("people/<int:pk>/approve/", views.approve_user, name="approve_user"),
    path("people/<int:pk>/approval/", views.set_approval, name="set_approval"),
    path("people/<int:pk>/role/", views.set_role, name="set_role"),
    path("hr/", views.HRView.as_view(), name="hr"),
    path("hr/pending/", views.HRPendingApprovalsView.as_view(), name="hr-pending"),
    path("hr/employees/", views.HREmployeeManagementView.as_view(), name="hr-employees"),
    path("hr/employees/<int:pk>/", views.HREmployeeEditView.as_view(), name="hr-employee-edit"),
    path("hr/permissions/", views.HREmployeePermissionsView.as_view(), name="hr-permissions"),
    path(
        "hr/permissions/<int:pk>/toggle/",
        views.toggle_permission,
        name="hr-permission-toggle",
    ),
    path("hr/salaries/", views.HRSalariesView.as_view(), name="hr-salaries"),
    path("hr/salaries/<int:pk>/register/", views.HRSalaryRegisterView.as_view(), name="hr-salary-register"),
    path("hr/salaries/<int:pk>/update/", views.HRSalaryUpdateView.as_view(), name="hr-salary-update"),
]
