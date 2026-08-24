import asyncio

import dns.resolver
from email_validator import EmailNotValidError, validate_email


def _check_email_mx(value: str) -> str:
    try:
        normalized = validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError:
        return "invalid_format"
    domain = normalized.rsplit("@", 1)[1]
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=4)
        return "mx_valid" if len(answers) else "mx_not_found"
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.LifetimeTimeout):
        return "mx_not_found"
    except dns.exception.DNSException:
        return "dns_error"


async def check_email_mx(value: str) -> str:
    """Безопасная проверка формата и MX без SMTP-соединения и отправки писем."""
    return await asyncio.to_thread(_check_email_mx, value)
