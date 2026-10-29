import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class AuthenticationApiTests(TestCase):
    def post_json(self, url_name, payload):
        return self.client.post(
            reverse(url_name),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_registration_creates_user_and_returns_csrf_token(self):
        response = self.post_json('user_register', {
            'name': 'Test User',
            'email': 'test@example.com',
            'password': 'StrongPass!9274',
            'confirm': 'StrongPass!9274',
        })

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['ok'])
        self.assertTrue(response.json()['csrf_token'])
        user = User.objects.get(email='test@example.com')
        self.assertEqual(user.first_name, 'Test User')
        self.assertTrue(user.check_password('StrongPass!9274'))

    def test_registration_rejects_mismatched_passwords(self):
        response = self.post_json('user_register', {
            'name': 'Test User',
            'email': 'test@example.com',
            'password': 'StrongPass!9274',
            'confirm': 'DifferentPass!9274',
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])
        self.assertFalse(User.objects.exists())

    def test_login_authenticates_by_email(self):
        user = User.objects.create_user(
            username='test@example.com',
            email='test@example.com',
            password='StrongPass!9274',
            first_name='Test User',
        )

        response = self.post_json('user_login', {
            'email': 'TEST@example.com',
            'password': 'StrongPass!9274',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertTrue(response.json()['csrf_token'])
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_login_rejects_invalid_password(self):
        User.objects.create_user(
            username='test@example.com',
            email='test@example.com',
            password='StrongPass!9274',
        )

        response = self.post_json('user_login', {
            'email': 'test@example.com',
            'password': 'incorrect',
        })

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['ok'])

    def test_registration_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        payload = {
            'name': 'Test User',
            'email': 'test@example.com',
            'password': 'StrongPass!9274',
            'confirm': 'StrongPass!9274',
        }

        rejected = client.post(
            reverse('user_register'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(rejected.status_code, 403)

        client.get(reverse('index'))
        csrf_token = client.cookies['csrftoken'].value
        accepted = client.post(
            reverse('user_register'),
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(accepted.status_code, 201)
