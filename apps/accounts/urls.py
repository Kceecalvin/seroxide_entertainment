from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from apps.core.ratelimit import ratelimit

from . import views, seller, gates
from .forms import AccountAuthenticationForm, TrackedPasswordResetForm

app_name = 'accounts'

# Same reasoning as apps/dashboard/urls.py's login throttle — generous for a
# genuine typo, tight enough to slow credential stuffing.
_login_view = ratelimit(key_prefix='buyer-login', limit=20, window_seconds=600)(
    auth_views.LoginView.as_view(template_name='accounts/login.html', authentication_form=AccountAuthenticationForm, redirect_authenticated_user=True, next_page='accounts:landing')
)

urlpatterns = [
    path('studio/<int:pk>/gate-team/', gates.team, name='gate_team'),
    path('studio/<int:pk>/gate-team/<int:assignment_id>/revoke/', gates.revoke, name='gate_revoke'),
    path('studio/<int:pk>/gate-invites/<int:invitation_id>/revoke/', gates.revoke_invite, name='gate_invite_revoke'),
    path('gate-invites/<str:token>/', gates.accept, name='gate_accept'),
    path('home/', views.landing, name='landing'),
    path('sell/', seller.onboard, name='seller_onboard'),
    path('studio/', seller.home, name='seller_home'),
    path('studio/new/', seller.edit_event, name='seller_create'),
    path('studio/<int:pk>/', seller.edit_event, name='seller_edit'),
    path('studio/<int:pk>/preview/', seller.preview, name='seller_preview'),
    path('studio/<int:pk>/tickets/', seller.save_tier, name='seller_tier'),
    path('studio/<int:pk>/tickets/<int:tier_id>/', seller.save_tier, name='seller_tier_edit'),
    path('studio/<int:pk>/submit/', seller.submit, name='seller_submit'),
    path('studio/<int:pk>/withdraw/', seller.withdraw, name='seller_withdraw'),
    path('reset/', ratelimit(key_prefix='password-reset', limit=5, window_seconds=600)(auth_views.PasswordResetView.as_view(
        form_class=TrackedPasswordResetForm, template_name='accounts/reset.html',
        email_template_name='emails/password_reset.txt', html_email_template_name='emails/password_reset.html',
        success_url=reverse_lazy('accounts:reset_done'))), name='password_reset'),
    path('reset/sent/', auth_views.PasswordResetDoneView.as_view(template_name='accounts/reset_done.html'), name='reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='accounts/reset_confirm.html', success_url=reverse_lazy('accounts:reset_complete')), name='reset_confirm'),
    path('reset/complete/', auth_views.PasswordResetCompleteView.as_view(template_name='accounts/reset_complete.html'), name='reset_complete'),
    path('signup/', views.signup, name='signup'),
    path('login/', _login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='events:list'), name='logout'),
    path('my-account/', views.my_account, name='my_account'),
    path('settings/', views.account_settings, name='settings'),
    path(
        'settings/password/',
        auth_views.PasswordChangeView.as_view(
            template_name='accounts/password_change.html',
            success_url=reverse_lazy('accounts:password_change_done'),
        ),
        name='password_change',
    ),
    path(
        'settings/password/done/',
        auth_views.PasswordChangeDoneView.as_view(template_name='accounts/password_change_done.html'),
        name='password_change_done',
    ),
]
