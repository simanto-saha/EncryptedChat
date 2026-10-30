import json
import re
from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import Message, userProfile

PHONE_RE = re.compile(r'^\+?\d{10,15}$')


def _json_payload(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _normalize_phone(raw):
    # "+880 1712-345678" -> "+8801712345678"
    return re.sub(r'[\s\-().]', '', raw)


def _auth_required_json(view):
    """Like login_required, but answers JSON (401) instead of redirecting."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'ok': False, 'message': 'Please log in first.'}, status=401
            )
        return view(request, *args, **kwargs)
    return wrapper


@ensure_csrf_cookie
def view_details(request):
    # Already logged in? Go straight to the chat room.
    if request.user.is_authenticated:
        return redirect('chat_room')
    return render(request, 'Chat/home.html')


@require_POST
def user_login(request):
    data = _json_payload(request)
    if data is None:
        return JsonResponse(
            {'ok': False, 'message': 'Invalid request data.'}, status=400
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
            {'ok': False, 'message': 'Invalid email or password.'}, status=401
        )

    login(request, authenticated_user)
    return JsonResponse({
        'ok': True,
        'message': f'Welcome, {authenticated_user.first_name or authenticated_user.username}!',
        'csrf_token': get_token(request),
        'redirect': reverse('chat_room'),   # <-- frontend sends user here
    })


@require_POST
def user_logout(request):
    logout(request)
    return JsonResponse({
        'ok': True,
        'message': 'Logged out successfully.',
        'redirect': reverse('view_details'),
    })


@require_POST
def user_register(request):
    data = _json_payload(request)
    if data is None:
        return JsonResponse(
            {'ok': False, 'message': 'Invalid request data.'}, status=400
        )

    name = data.get('name')
    email = data.get('email')
    number = data.get('phone')
    password = data.get('password', '')
    confirm = data.get('confirm', '')

    if not isinstance(name, str) or not isinstance(email, str):
        return JsonResponse(
            {'ok': False, 'message': 'Name and email are required.'}, status=400
        )
    if not isinstance(number, str):
        return JsonResponse(
            {'ok': False, 'message': 'Phone number is required.'}, status=400
        )
    if not isinstance(password, str) or not isinstance(confirm, str):
        return JsonResponse(
            {'ok': False, 'message': 'Password and confirmation are required.'},
            status=400,
        )

    name = name.strip()
    email = email.strip().lower()
    number = _normalize_phone(number.strip())

    if not name or not email or not number or not password or not confirm:
        return JsonResponse(
            {'ok': False, 'message': 'All fields are required.'}, status=400
        )

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse(
            {'ok': False, 'message': 'Enter a valid email address.'}, status=400
        )

    # Phone: digits only (optional leading +), 10-15 characters
    if not PHONE_RE.match(number):
        return JsonResponse(
            {'ok': False,
             'message': 'Enter a valid phone number (10-15 digits, optional + at the start).'},
            status=400,
        )
    max_phone = userProfile._meta.get_field('number').max_length
    if len(number) > max_phone:
        return JsonResponse(
            {'ok': False, 'message': 'Phone number is too long.'}, status=400
        )

    if len(name) > User._meta.get_field('first_name').max_length:
        return JsonResponse(
            {'ok': False, 'message': 'Name is too long.'}, status=400
        )
    if len(email) > User._meta.get_field('username').max_length:
        return JsonResponse(
            {'ok': False, 'message': 'Email address is too long.'}, status=400
        )

    if password != confirm:
        return JsonResponse(
            {'ok': False, 'message': 'Passwords do not match.'}, status=400
        )

    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse(
            {'ok': False, 'message': 'An account with this email already exists.'},
            status=409,
        )
    if userProfile.objects.filter(number=number).exists():
        return JsonResponse(
            {'ok': False, 'message': 'An account with this phone number already exists.'},
            status=409,
        )

    try:
        validate_password(password)
    except ValidationError as error:
        return JsonResponse(
            {'ok': False, 'message': ' '.join(error.messages)}, status=400
        )

    # `number` is NOT a User field -> it lives on userProfile.
    # atomic = either both rows are created or neither.
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=name,
            )
            userProfile.objects.create(user=user, number=number)
    except IntegrityError:
        return JsonResponse(
            {'ok': False, 'message': 'An account with these details already exists.'},
            status=409,
        )

    return JsonResponse({
        'ok': True,
        'message': 'Account created successfully. Please log in.',
        'csrf_token': get_token(request),
        'user_id': user.pk,
    }, status=201)


# ----------------------------------------------------------------- chat ----

def chat_room(request):
    if not request.user.is_authenticated:
        return redirect('view_details')
    return render(request, 'Chat/chat_room.html', {'chat_user_id': request.user.pk})


@require_GET
@_auth_required_json
def api_users(request):
    """Left sidebar: every other user, newest conversation first."""
    me = request.user
    rows = []
    for u in User.objects.filter(is_active=True).exclude(pk=me.pk):
        last = (
            Message.objects
            .filter(Q(sender=me, receiver=u) | Q(sender=u, receiver=me))
            .order_by('-timestamp', '-id')
            .first()
        )
        rows.append({
            'id': u.pk,
            'name': u.first_name or u.username,
            'preview': (last.content[:40] if last else 'Say hello 👋'),
            'last_ts': last.timestamp.timestamp() if last else 0,
        })
    rows.sort(key=lambda r: (-r['last_ts'], r['name'].lower()))
    return JsonResponse({'ok': True, 'users': rows})


@require_GET
@_auth_required_json
def api_messages(request, user_id):
    """Conversation with one user. ?after=<id> returns only newer messages."""
    me = request.user
    try:
        other = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        return JsonResponse({'ok': False, 'message': 'User not found.'}, status=404)

    qs = Message.objects.filter(
        Q(sender=me, receiver=other) | Q(sender=other, receiver=me)
    ).order_by('id')
    try:
        after = int(request.GET.get('after', 0))
    except ValueError:
        after = 0
    if after:
        qs = qs.filter(id__gt=after)

    messages = [{
        'id': m.pk,
        'mine': m.sender_id == me.pk,
        'content': m.content,
        'time': timezone.localtime(m.timestamp).strftime('%H:%M'),
    } for m in qs[:200]]
    return JsonResponse({'ok': True, 'messages': messages})


@require_POST
@_auth_required_json
def api_send(request):
    data = _json_payload(request)
    if data is None:
        return JsonResponse(
            {'ok': False, 'message': 'Invalid request data.'}, status=400
        )

    content = data.get('content')
    to = data.get('to')
    if not isinstance(content, str) or not content.strip():
        return JsonResponse(
            {'ok': False, 'message': 'Message cannot be empty.'}, status=400
        )
    content = content.strip()
    if len(content) > 1000:
        return JsonResponse(
            {'ok': False, 'message': 'Message is too long (max 1000 characters).'},
            status=400,
        )
    if not isinstance(to, int) or to == request.user.pk:
        return JsonResponse(
            {'ok': False, 'message': 'Choose someone to message.'}, status=400
        )

    try:
        receiver = User.objects.get(pk=to, is_active=True)
    except User.DoesNotExist:
        return JsonResponse({'ok': False, 'message': 'User not found.'}, status=404)

    m = Message.objects.create(sender=request.user, receiver=receiver, content=content)
    return JsonResponse({
        'ok': True,
        'message': {
            'id': m.pk,
            'mine': True,
            'content': m.content,
            'time': timezone.localtime(m.timestamp).strftime('%H:%M'),
        },
    }, status=201)