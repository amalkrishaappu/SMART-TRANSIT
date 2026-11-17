import re

from django.utils.crypto import get_random_string

from apps.accounts.models import ParentProfile, User


def username_from_identifier(raw_value, prefix=''):
    """Build a unique Django username from an admission number or similar label."""
    base = re.sub(r'[^a-z0-9]+', '_', (raw_value or '').lower()).strip('_')
    if prefix:
        base = f"{prefix}{base}" if base else prefix.rstrip('_')
    if not base:
        base = 'user'
    base = base[:140]
    candidate = base
    suffix = 2
    while User.objects.filter(username__iexact=candidate).exists():
        candidate = f"{base[:140]}_{suffix}"
        suffix += 1
    return candidate


def normalize_phone(value):
    return re.sub(r'[\s\-()]', '', value or '')


def find_parent_by_phone(phone):
    target = normalize_phone(phone)
    if len(target) < 8:
        return None
    tail = target[-10:]
    for parent in ParentProfile.objects.select_related('user'):
        existing = normalize_phone(parent.user.phone_number)
        if existing and (existing == target or existing.endswith(tail) or target.endswith(existing[-10:])):
            return parent
    return None


def issue_temporary_password(user):
    """Hash a random temporary password. The plaintext is returned only to the caller."""
    temporary_password = get_random_string(12)
    user.set_password(temporary_password)
    user.must_change_password = True
    user.save(update_fields=['password', 'must_change_password'])
    return temporary_password


def split_person_name(full_name):
    parts = (full_name or '').split()
    if not parts:
        return 'Parent', ''
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], ' '.join(parts[1:])
