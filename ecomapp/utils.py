from django.contrib.auth.tokens import PasswordResetTokenGenerator


class MyPasswordResetTokenGenerator(PasswordResetTokenGenerator):
    """Token generator used for password reset links."""

    def _make_hash_value(self, user, timestamp):
        return str(user.pk) + str(timestamp)


password_reset_token = MyPasswordResetTokenGenerator()
