"""
OTP (One-Time Password) system for phone number verification.

Uses Redis for temporary storage with TTL and attempt tracking.
"""

import random
import string
import hashlib
import logging
from typing import Tuple, Optional
from django.conf import settings
from django.core.cache import cache
from common.utils import cache_key, mask_phone_number

logger = logging.getLogger(__name__)


def generate_otp(length: int = 6) -> str:
    """
    Generate a random numeric OTP.

    Args:
        length: Length of OTP (default: 6)

    Returns:
        String of random digits
    """
    return ''.join(random.choices(string.digits, k=length))


def hash_otp(otp: str) -> str:
    """
    Hash OTP using SHA-256 for secure storage.

    Args:
        otp: Plain OTP to hash

    Returns:
        Hexadecimal hash string
    """
    # Add salt from Django secret key for additional security
    salted = f'{settings.SECRET_KEY}{otp}'
    return hashlib.sha256(salted.encode()).hexdigest()


def store_otp(phone_number: str, otp: str, ttl: Optional[int] = None) -> dict:
    """
    Store hashed OTP in Redis with TTL and attempt counter.

    Args:
        phone_number: Normalized phone number
        otp: Plain OTP to store (will be hashed)
        ttl: Time to live in seconds (default: from settings)

    Returns:
        Dict with storage details (masked_phone, expires_in)
    """
    if ttl is None:
        ttl = settings.OTP_EXPIRY_SECONDS

    hashed = hash_otp(otp)

    # Store OTP data
    otp_data = {
        'hash': hashed,
        'attempts': 0,
        'max_attempts': settings.OTP_MAX_ATTEMPTS,
    }

    key = cache_key('otp', phone_number)
    cache.set(key, otp_data, ttl)

    logger.info(f'OTP stored for {mask_phone_number(phone_number)}, expires in {ttl}s')

    return {
        'masked_phone': mask_phone_number(phone_number),
        'expires_in': ttl,
    }


def verify_otp(phone_number: str, submitted_otp: str) -> Tuple[bool, Optional[str]]:
    """
    Verify submitted OTP against stored hash.

    Checks:
    1. OTP exists for phone number
    2. Not expired (handled by Redis TTL)
    3. Attempt count not exceeded
    4. Hash matches

    Args:
        phone_number: Normalized phone number
        submitted_otp: OTP submitted by user

    Returns:
        Tuple of (is_valid, error_message)
        - (True, None) if valid
        - (False, error_message) if invalid
    """
    key = cache_key('otp', phone_number)
    otp_data = cache.get(key)

    if not otp_data:
        logger.warning(f'OTP verification failed for {mask_phone_number(phone_number)}: No OTP found or expired')
        return False, 'OTP has expired or does not exist. Please request a new one.'

    # Check attempt count
    if otp_data['attempts'] >= otp_data['max_attempts']:
        logger.warning(f'OTP verification failed for {mask_phone_number(phone_number)}: Max attempts exceeded')
        # Delete OTP to prevent further attempts
        cache.delete(key)
        return False, f'Maximum verification attempts ({otp_data["max_attempts"]}) exceeded. Please request a new OTP.'

    # Increment attempt counter
    otp_data['attempts'] += 1
    cache.set(key, otp_data, get_remaining_ttl(phone_number) or settings.OTP_EXPIRY_SECONDS)

    # Verify hash
    submitted_hash = hash_otp(submitted_otp)
    if submitted_hash == otp_data['hash']:
        # Success - delete OTP from cache
        cache.delete(key)
        logger.info(f'OTP verified successfully for {mask_phone_number(phone_number)}')
        return True, None
    else:
        remaining_attempts = otp_data['max_attempts'] - otp_data['attempts']
        logger.warning(
            f'OTP verification failed for {mask_phone_number(phone_number)}: '
            f'Invalid code. {remaining_attempts} attempts remaining'
        )
        return False, f'Invalid OTP. {remaining_attempts} attempts remaining.'


def get_remaining_ttl(phone_number: str) -> Optional[int]:
    """
    Get remaining TTL for OTP in seconds.

    Args:
        phone_number: Normalized phone number

    Returns:
        Seconds remaining or None if OTP doesn't exist
    """
    key = cache_key('otp', phone_number)
    ttl = cache.ttl(key) if hasattr(cache, 'ttl') else None

    # Fallback for cache backends that don't support TTL
    if ttl is None:
        otp_data = cache.get(key)
        if otp_data:
            # Return default TTL as we can't get exact remaining time
            return settings.OTP_EXPIRY_SECONDS
        return None

    return max(0, ttl) if ttl > 0 else None


def can_request_new_otp(phone_number: str) -> Tuple[bool, Optional[str]]:
    """
    Check if a new OTP can be requested for this phone number.

    Prevents too frequent OTP requests (rate limiting).

    Args:
        phone_number: Normalized phone number

    Returns:
        Tuple of (can_request, error_message)
    """
    key = cache_key('otp', phone_number)
    otp_data = cache.get(key)

    if not otp_data:
        # No existing OTP, can request new one
        return True, None

    # Check if there's significant time left on current OTP
    remaining = get_remaining_ttl(phone_number)
    if remaining and remaining > (settings.OTP_EXPIRY_SECONDS * 0.8):  # More than 80% time left
        return False, f'Please wait {remaining} seconds before requesting a new OTP.'

    # Allow new OTP request
    return True, None


def invalidate_otp(phone_number: str) -> None:
    """
    Manually invalidate/delete OTP for a phone number.

    Useful for cleanup or forced logout scenarios.

    Args:
        phone_number: Normalized phone number
    """
    key = cache_key('otp', phone_number)
    cache.delete(key)
    logger.info(f'OTP invalidated for {mask_phone_number(phone_number)}')


def get_otp_info(phone_number: str) -> Optional[dict]:
    """
    Get information about current OTP status for a phone number.

    Useful for debugging and admin purposes.

    Args:
        phone_number: Normalized phone number

    Returns:
        Dict with OTP info or None if no OTP exists
    """
    key = cache_key('otp', phone_number)
    otp_data = cache.get(key)

    if not otp_data:
        return None

    return {
        'exists': True,
        'attempts_used': otp_data.get('attempts', 0),
        'max_attempts': otp_data.get('max_attempts', settings.OTP_MAX_ATTEMPTS),
        'remaining_attempts': otp_data.get('max_attempts', settings.OTP_MAX_ATTEMPTS) - otp_data.get('attempts', 0),
        'remaining_ttl': get_remaining_ttl(phone_number),
        'masked_phone': mask_phone_number(phone_number),
    }
