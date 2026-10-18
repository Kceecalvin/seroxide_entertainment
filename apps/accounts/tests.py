from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class AccountSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='jane@example.com', email='jane@example.com', password='OldPassw0rd!',
            first_name='Jane', last_name='Wanjiku',
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_settings_page_prefills_current_details(self):
        resp = self.client.get(reverse('accounts:settings'))
        self.assertContains(resp, 'Jane Wanjiku')
        self.assertContains(resp, 'jane@example.com')

    def test_can_update_name_and_email(self):
        resp = self.client.post(reverse('accounts:settings'), {
            'full_name': 'Jane Mwangi', 'email': 'jane.mwangi@example.com',
        })
        self.assertRedirects(resp, reverse('accounts:settings'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Jane')
        self.assertEqual(self.user.last_name, 'Mwangi')
        self.assertEqual(self.user.email, 'jane.mwangi@example.com')
        # username tracks email — otherwise login and email silently drift apart
        self.assertEqual(self.user.username, 'jane.mwangi@example.com')

    def test_cannot_take_another_users_email(self):
        User.objects.create_user(username='taken@example.com', email='taken@example.com', password='x')
        resp = self.client.post(reverse('accounts:settings'), {
            'full_name': 'Jane Wanjiku', 'email': 'taken@example.com',
        })
        self.assertEqual(resp.status_code, 200)  # re-renders with error, no redirect
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'jane@example.com')  # unchanged

    def test_settings_requires_login(self):
        anon_client = Client()
        resp = anon_client.get(reverse('accounts:settings'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:login'), resp.url)


class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='jane@example.com', email='jane@example.com', password='OldPassw0rd!',
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_correct_current_password_allows_change(self):
        resp = self.client.post(reverse('accounts:password_change'), {
            'old_password': 'OldPassw0rd!', 'new_password1': 'NewPassw0rd!2', 'new_password2': 'NewPassw0rd!2',
        })
        self.assertRedirects(resp, reverse('accounts:password_change_done'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPassw0rd!2'))

    def test_wrong_current_password_is_rejected(self):
        resp = self.client.post(reverse('accounts:password_change'), {
            'old_password': 'WrongPassword', 'new_password1': 'NewPassw0rd!2', 'new_password2': 'NewPassw0rd!2',
        })
        self.assertEqual(resp.status_code, 200)  # re-renders with error
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPassw0rd!'))  # unchanged

    def test_session_stays_valid_after_password_change(self):
        """Django's PasswordChangeView rotates the session auth hash — a
        buyer changing their password must not get logged out mid-flow."""
        self.client.post(reverse('accounts:password_change'), {
            'old_password': 'OldPassw0rd!', 'new_password1': 'NewPassw0rd!2', 'new_password2': 'NewPassw0rd!2',
        })
        resp = self.client.get(reverse('accounts:my_account'))
        self.assertEqual(resp.status_code, 200)
