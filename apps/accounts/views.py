from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.core.ratelimit import ratelimit

from .forms import ProfileForm, SignupForm


@ratelimit(key_prefix='signup', limit=10, window_seconds=600)
def signup(request):
    if request.user.is_authenticated:
        return redirect('accounts:my_account')

    next_url = request.POST.get('next', request.GET.get('next', ''))
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = ''
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            from apps.core.mailer import notify
            from django.urls import reverse
            notify(user, 'Welcome to SeroTix', 'Your account is ready. Find your next experience and keep your tickets together.', reverse('accounts:my_account'))
            login(request, user)
            if next_url:
                return redirect(next_url)
            return redirect('accounts:seller_onboard' if form.cleaned_data.get('intent') == 'seller' else 'accounts:my_account')
    else:
        form = SignupForm()

    return render(request, 'accounts/signup.html', {'form': form, 'next': next_url})


@login_required(login_url='accounts:login')
def my_account(request):
    orders = (
        request.user.orders
        .select_related('event')
        .prefetch_related('items__ticket_type')
        .order_by('-created_at')
    )
    return render(request, 'accounts/my_account.html', {'orders': orders})


@login_required(login_url='accounts:login')
def account_settings(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your account details have been updated.')
            return redirect('accounts:settings')
    else:
        form = ProfileForm(instance=request.user)
    return render(request, 'accounts/settings.html', {'form': form})


@login_required(login_url='accounts:login')
def landing(request):
    from .permissions import role_for, has_gate_access
    role = role_for(request.user)
    if role == 'buyer' and has_gate_access(request.user):
        return redirect('tickets:scanner')
    return redirect({'superadmin': 'dashboard:home', 'admin': 'dashboard:home', 'scanner': 'tickets:scanner', 'seller': 'accounts:seller_home'}.get(role, 'accounts:my_account'))
