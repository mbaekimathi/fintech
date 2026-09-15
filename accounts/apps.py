from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Identity and access"

    def ready(self):
        from accounts.role_urls import install_role_reverse_patch

        install_role_reverse_patch()
