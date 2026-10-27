"""Initial subscription catalogue. Prices are merchant-approved amounts, not FX conversions."""

from __future__ import annotations

PLAN_CODES = ("starter", "professional", "enterprise", "university")

# Annual India prices in minor units (paise). Monthly prices are not invented.
INR_ANNUAL_MINOR = {
    "starter": 6_000_000,
    "professional": 18_000_000,
    "enterprise": 45_000_000,
    "university": 150_000_000,
}

PLAN_DEFINITIONS = {
    "starter": {
        "name": "Starter",
        "trial_days": 14,
        "student_limit": 200,
        "teacher_limit": 20,
        "storage_mb": 50_000,
        "ai_tokens": 100_000,
        "ai_requests": 2_000,
        "institution_limit": 1,
        "course_limit": 20,
        "support_level": "email",
        "features": {
            "assessments": True,
            "study_buddy": True,
            "teacher_copilot": False,
            "adaptive_learning": False,
            "analytics": False,
            "gamification": True,
            "proctoring": False,
            "api_access": False,
        },
    },
    "professional": {
        "name": "Professional",
        "trial_days": 14,
        "student_limit": 1_000,
        "teacher_limit": 80,
        "storage_mb": 200_000,
        "ai_tokens": 500_000,
        "ai_requests": 10_000,
        "institution_limit": 1,
        "course_limit": 100,
        "support_level": "priority",
        "features": {
            "assessments": True,
            "study_buddy": True,
            "teacher_copilot": True,
            "adaptive_learning": True,
            "analytics": True,
            "gamification": True,
            "proctoring": True,
            "api_access": False,
        },
    },
    "enterprise": {
        "name": "Enterprise",
        "trial_days": 14,
        "student_limit": 5_000,
        "teacher_limit": 400,
        "storage_mb": 1_000_000,
        "ai_tokens": 2_000_000,
        "ai_requests": 50_000,
        "institution_limit": 5,
        "course_limit": 500,
        "support_level": "dedicated",
        "features": {
            "assessments": True,
            "study_buddy": True,
            "teacher_copilot": True,
            "adaptive_learning": True,
            "analytics": True,
            "gamification": True,
            "proctoring": True,
            "api_access": True,
        },
    },
    "university": {
        "name": "University",
        "trial_days": 14,
        "student_limit": 20_000,
        "teacher_limit": 2_000,
        "storage_mb": 5_000_000,
        "ai_tokens": 8_000_000,
        "ai_requests": 200_000,
        "institution_limit": 20,
        "course_limit": 2_000,
        "support_level": "dedicated",
        "features": {
            "assessments": True,
            "study_buddy": True,
            "teacher_copilot": True,
            "adaptive_learning": True,
            "analytics": True,
            "gamification": True,
            "proctoring": True,
            "api_access": True,
        },
    },
}

CURRENCIES = {
    "INR": {"name": "Indian rupee", "symbol": "₹", "minor_units": 2},
    "USD": {"name": "US dollar", "symbol": "$", "minor_units": 2},
    "GBP": {"name": "Pound sterling", "symbol": "£", "minor_units": 2},
    "EUR": {"name": "Euro", "symbol": "€", "minor_units": 2},
    "SGD": {"name": "Singapore dollar", "symbol": "S$", "minor_units": 2},
    "AED": {"name": "UAE dirham", "symbol": "AED ", "minor_units": 2},
    "AUD": {"name": "Australian dollar", "symbol": "A$", "minor_units": 2},
    "CAD": {"name": "Canadian dollar", "symbol": "CA$", "minor_units": 2},
}

EURO_AREA = {
    "AT", "BE", "HR", "CY", "EE", "FI", "FR", "DE", "GR", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PT", "SK", "SI", "ES",
}

REGIONS = {
    "IN": {"locale": "en-IN", "default_currency": "INR", "currencies": ["INR"], "gateways": ["razorpay", "stripe"], "address_required": True},
    "US": {"locale": "en-US", "default_currency": "USD", "currencies": ["USD"], "gateways": ["stripe", "paypal"], "address_required": True},
    "GB": {"locale": "en-GB", "default_currency": "GBP", "currencies": ["GBP"], "gateways": ["stripe", "paypal"], "address_required": True},
    "SG": {"locale": "en-SG", "default_currency": "SGD", "currencies": ["SGD"], "gateways": ["stripe"], "address_required": True},
    "AE": {"locale": "en-AE", "default_currency": "AED", "currencies": ["AED"], "gateways": ["stripe"], "address_required": True},
    "AU": {"locale": "en-AU", "default_currency": "AUD", "currencies": ["AUD"], "gateways": ["stripe", "paypal"], "address_required": True},
    "CA": {"locale": "en-CA", "default_currency": "CAD", "currencies": ["CAD"], "gateways": ["stripe", "paypal"], "address_required": True},
}
for _code in EURO_AREA:
    REGIONS[_code] = {
        "locale": "en-IE",
        "default_currency": "EUR",
        "currencies": ["EUR"],
        "gateways": ["stripe", "paypal"],
        "address_required": True,
    }

FEATURE_KEYS = (
    "assessments",
    "study_buddy",
    "teacher_copilot",
    "adaptive_learning",
    "analytics",
    "gamification",
    "proctoring",
    "api_access",
)
