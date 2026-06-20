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
