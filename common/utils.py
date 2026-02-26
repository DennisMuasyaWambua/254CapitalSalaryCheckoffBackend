"""
Common utility functions used across the application.
"""

import re
import uuid
import random
import string
from typing import Optional
from django.core.cache import cache
from django.conf import settings


def generate_uuid() -> str:
    """Generate a UUID4 string."""
    return str(uuid.uuid4())


def generate_random_digits(length: int = 6) -> str:
    """
    Generate a random numeric string of specified length.

    Args:
        length: Number of digits to generate (default: 6)

    Returns:
        String of random digits
    """
    return ''.join(random.choices(string.digits, k=length))


def validate_kenyan_phone(phone_number: str) -> bool:
    """
    Validate Kenyan phone number format.

    Accepts formats:
    - +254712345678
    - 254712345678
    - 0712345678

    Args:
        phone_number: Phone number to validate

    Returns:
        Boolean indicating if phone number is valid
    """
    # Remove whitespace
    phone_number = phone_number.strip()

    # Pattern for Kenyan phone numbers
    patterns = [
        r'^\+254[17]\d{8}$',  # +254712345678
        r'^254[17]\d{8}$',     # 254712345678
        r'^0[17]\d{8}$',       # 0712345678
    ]

    return any(re.match(pattern, phone_number) for pattern in patterns)


def normalize_kenyan_phone(phone_number: str) -> str:
    """
    Normalize Kenyan phone number to international format (+254...).

    Args:
        phone_number: Phone number in any accepted format

    Returns:
        Normalized phone number in +254... format

    Raises:
        ValueError: If phone number is invalid
    """
    phone_number = phone_number.strip()

    if not validate_kenyan_phone(phone_number):
        raise ValueError(f'Invalid Kenyan phone number: {phone_number}')

    # Remove any non-digit characters except leading +
    if phone_number.startswith('+'):
        phone_number = '+' + re.sub(r'\D', '', phone_number)
    else:
        phone_number = re.sub(r'\D', '', phone_number)

    # Convert to +254 format
    if phone_number.startswith('+254'):
        return phone_number
    elif phone_number.startswith('254'):
        return f'+{phone_number}'
    elif phone_number.startswith('0'):
        return f'+254{phone_number[1:]}'
    else:
        raise ValueError(f'Cannot normalize phone number: {phone_number}')


def mask_phone_number(phone_number: str) -> str:
    """
    Mask phone number for display.

    Example: +254712345678 -> 07***678

    Args:
        phone_number: Phone number to mask

    Returns:
        Masked phone number
    """
    try:
        normalized = normalize_kenyan_phone(phone_number)
        # Convert to 07... format and mask middle digits
        local_format = f'0{normalized[4:]}'  # Remove +254
        if len(local_format) >= 10:
            return f'{local_format[:3]}***{local_format[-3:]}'
        return local_format
    except ValueError:
        # If normalization fails, return masked version of original
        if len(phone_number) >= 6:
            return f'{phone_number[:2]}***{phone_number[-3:]}'
        return '***'


def validate_national_id(national_id: str) -> bool:
    """
    Validate Kenyan National ID format.

    Kenyan National IDs are typically 7-8 digits.

    Args:
        national_id: National ID to validate

    Returns:
        Boolean indicating if National ID is valid
    """
    national_id = national_id.strip()
    # Kenyan National ID is 7-8 digits
    pattern = r'^\d{7,8}$'
    return bool(re.match(pattern, national_id))


def get_client_ip(request) -> str:
    """
    Get client IP address from request.

    Args:
        request: Django request object

    Returns:
        IP address string
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def cache_key(prefix: str, identifier: str) -> str:
    """
    Generate a cache key with app prefix.

    Args:
        prefix: Key prefix (e.g., 'otp', 'user')
        identifier: Unique identifier (e.g., phone number, user ID)

    Returns:
        Full cache key
    """
    return f'254capital:{prefix}:{identifier}'


def set_cache(key: str, value: any, timeout: Optional[int] = None) -> None:
    """
    Set value in cache with optional timeout.

    Args:
        key: Cache key
        value: Value to cache
        timeout: Timeout in seconds (None = default timeout from settings)
    """
    cache.set(key, value, timeout)


def get_cache(key: str, default: any = None) -> any:
    """
    Get value from cache.

    Args:
        key: Cache key
        default: Default value if key not found

    Returns:
        Cached value or default
    """
    return cache.get(key, default)


def delete_cache(key: str) -> None:
    """
    Delete value from cache.

    Args:
        key: Cache key
    """
    cache.delete(key)


def format_currency(amount, currency='KES') -> str:
    """
    Format amount as currency string.

    Args:
        amount: Numeric amount
        currency: Currency code (default: KES)

    Returns:
        Formatted currency string
    """
    return f'{currency} {amount:,.2f}'


def truncate_string(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """
    Truncate string to maximum length.

    Args:
        text: String to truncate
        max_length: Maximum length (default: 100)
        suffix: Suffix to add if truncated (default: ...)

    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
