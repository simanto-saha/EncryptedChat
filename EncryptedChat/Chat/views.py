import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST


def _json_payload(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


@ensure_csrf_cookie
def view_details(request):
    return render(request, 'Chat/home.html')


@require_POST
def user_login(request):
    data = _json_payload(request)
    if data is None:
        return JsonResponse(
            {'ok': False, 'message': 'Invalid request data.'},
            status=400,
        )

    email = data.get('email')
    password = data.get('password')
    if not isinstance(email, str) or not isinstance(password, str):
        return JsonResponse(
            {'ok': False, 'message': 'Email and password are required.'},
            status=400,
        )
    email = email.strip().lower()
    if not email or not password:
        return JsonResponse(
            {'ok': False, 'message': 'Email and password are required.'},
            status=400,
        )

    user = User.objects.filter(email__iexact=email).first()
    authenticated_user = (
        authenticate(request, username=user.username, password=password)
        if user
        else None
    )
    if authenticated_user is None:
        return JsonResponse(
            {'ok': False, 'message': 'Invalid email or password.'},
            status=401,
        )

    login(request, authenticated_user)
    return JsonResponse({
        'ok': True,
        'message': f'Welcome, {authenticated_user.first_name or authenticated_user.username}!',
        'csrf_token': get_token(request),
    })


@require_POST
def user_logout(request):
    logout(request)
    return JsonResponse({'ok': True, 'message': 'Logged out successfully.'})


@require_POST
def user_register(request):
    data = _json_payload(request)
    if data is None:
        return JsonResponse(
            {'ok': False, 'message': 'Invalid request data.'},
            status=400,
        )

    name = data.get('name')
    email = data.get('email')
    password = data.get('password', '')
    confirm = data.get('confirm', '')
    if not isinstance(name, str) or not isinstance(email, str):
        return JsonResponse(
            {'ok': False, 'message': 'Name and email are required.'},
            status=400,
        )
    name = name.strip()
    email = email.strip().lower()
    if not isinstance(password, str) or not isinstance(confirm, str):
        return JsonResponse(
            {'ok': False, 'message': 'Password and confirmation are required.'},
            status=400,
        )
    if not name or not email or not password or not confirm:
        return JsonResponse(
            {'ok': False, 'message': 'All fields are required.'},
            status=400,
        )

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse(
            {'ok': False, 'message': 'Enter a valid email address.'},
            status=400,
        )

    if len(name) > User._meta.get_field('first_name').max_length:
        return JsonResponse(
            {'ok': False, 'message': 'Name is too long.'},
            status=400,
        )
    if len(email) > User._meta.get_field('username').max_length:
        return JsonResponse(
            {'ok': False, 'message': 'Email address is too long.'},
            status=400,
        )

    if password != confirm:
        return JsonResponse(
            {'ok': False, 'message': 'Passwords do not match.'},
            status=400,
        )

    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse(
            {'ok': False, 'message': 'An account with this email already exists.'},
            status=409,
        )

    try:
        validate_password(password)
    except ValidationError as error:
        return JsonResponse(
            {'ok': False, 'message': ' '.join(error.messages)},
            status=400,
        )

    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
        first_name=name,
    )
    return JsonResponse({
        'ok': True,
        'message': 'Account created successfully. Please log in.',
        'csrf_token': get_token(request),
        'user_id': user.pk,
    }, status=201)


def chat_room(request):
    if not request.user.is_authenticated:
        return render(request, 'Chat/home.html', {'error': 'You must be logged in to access the chat room.'})
    
    return render(request, 'Chat/chat_room.html', {'user': request.user})