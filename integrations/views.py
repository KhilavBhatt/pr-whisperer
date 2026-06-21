import secrets
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.shortcuts import redirect
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Developer
from core.crypto import encrypt_token


@api_view(['GET'])
@permission_classes([AllowAny])
def github_login(request):
    """
    Step 1 of OAuth: redirect the user to GitHub's authorization page.
    """
    state = secrets.token_urlsafe(24)
    request.session['oauth_state'] = state

    github_authorize_url = (
        'https://github.com/login/oauth/authorize'
        f'?client_id={settings.GITHUB_CLIENT_ID}'
        f'&redirect_uri={settings.GITHUB_OAUTH_CALLBACK_URL}'
        '&scope=repo,read:user'
        f'&state={state}'
    )
    return redirect(github_authorize_url)


@api_view(['GET'])
@permission_classes([AllowAny])
def github_callback(request):
    """
    Step 2 of OAuth: GitHub redirects here with a temporary 'code'.
    We exchange it for a real access token, fetch the user's GitHub
    profile, create or update our Developer record, and issue our
    own JWT pair for the frontend to use going forward.
    """
    code = request.GET.get('code')
    if not code:
        return Response({'error': 'Missing code parameter'}, status=status.HTTP_400_BAD_REQUEST)

    # Exchange the temporary code for a real GitHub access token
    token_response = requests.post(
        'https://github.com/login/oauth/access_token',
        headers={'Accept': 'application/json'},
        data={
            'client_id': settings.GITHUB_CLIENT_ID,
            'client_secret': settings.GITHUB_CLIENT_SECRET,
            'code': code,
            'redirect_uri': settings.GITHUB_OAUTH_CALLBACK_URL,
        },
    )
    token_data = token_response.json()
    github_access_token = token_data.get('access_token')

    if not github_access_token:
        return Response(
            {'error': 'Failed to obtain GitHub access token', 'details': token_data},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Use that token to fetch the user's GitHub profile
    profile_response = requests.get(
        'https://api.github.com/user',
        headers={'Authorization': f'Bearer {github_access_token}'},
    )
    profile_data = profile_response.json()

    github_username = profile_data.get('login')
    github_id = str(profile_data.get('id'))

    if not github_username or not github_id:
        return Response(
            {'error': 'Failed to fetch GitHub profile', 'details': profile_data},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create or update the Django User + Developer records
    user, _ = User.objects.get_or_create(
        username=f'github_{github_id}',
        defaults={'first_name': github_username},
    )

    developer, _ = Developer.objects.update_or_create(
        github_id=github_id,
        defaults={
            'user': user,
            'github_username': github_username,
            'access_token_encrypted': encrypt_token(github_access_token),
        },
    )

    # Issue our own JWT pair for the frontend to use going forward
    refresh = RefreshToken.for_user(user)
    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'developer': {
            'github_username': developer.github_username,
            'github_id': developer.github_id,
        },
    })


@api_view(['GET'])
def me(request):
    """
    Protected endpoint: returns the authenticated developer's info.
    Requires a valid JWT in the Authorization header. Proves the full
    OAuth + JWT chain works end-to-end.
    """
    try:
        developer = request.user.developer_profile
    except Developer.DoesNotExist:
        return Response(
            {'error': 'No developer profile linked to this user'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({
        'github_username': developer.github_username,
        'github_id': developer.github_id,
        'created_at': developer.created_at,
    })


import json
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.utils.decorators import method_decorator

from integrations.security import verify_github_signature
from integrations.tasks import process_webhook_event
from integrations.models import WebhookEvent
from core.models import Repository


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def github_webhook(request):
    """
    Receives GitHub webhook events. Verifies the signature, logs the
    raw payload immediately, queues async processing, and returns fast
    — GitHub expects a quick response and may retry on timeout.
    """
    signature = request.headers.get('X-Hub-Signature-256', '')
    if not verify_github_signature(request.body, signature):
        return JsonResponse({'error': 'Invalid signature'}, status=401)

    payload = json.loads(request.body)
    event_type = request.headers.get('X-GitHub-Event', 'unknown')
    delivery_id = request.headers.get('X-GitHub-Delivery', '')

    repo_full_name = payload.get('repository', {}).get('full_name')
    repo_github_id = str(payload.get('repository', {}).get('id', ''))

    repository, _ = Repository.objects.get_or_create(
        github_repo_id=repo_github_id,
        defaults={
            'full_name': repo_full_name,
            'owner': None,  # Claimed later when a Developer authenticates and connects this repo
            'webhook_active': True,
        },
    )

    event, created = WebhookEvent.objects.get_or_create(
        delivery_id=delivery_id,
        defaults={
            'repository': repository,
            'event_type': event_type,
            'raw_payload': payload,
        },
    )

    if created:
        process_webhook_event.delay(event.id)

    return JsonResponse({'status': 'received', 'event_id': event.id})
