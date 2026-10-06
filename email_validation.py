import logging
from typing import Dict, List

import dns.asyncresolver
import dns.exception
import dns.resolver

logger = logging.getLogger("leads_pipeline.email_validation")

_mx_cache: Dict[str, bool] = {}

async def domain_accepts_mail(domain: str) -> bool:
    """True if the domain publishes MX records. Lookup timeouts count as valid so a flaky
    resolver doesn't throw away real leads; only definite 'no mail server' answers reject."""
    domain = domain.lower()
    if domain in _mx_cache:
        return _mx_cache[domain]
    try:
        answers = await dns.asyncresolver.resolve(domain, "MX", lifetime=5)
        ok = len(answers) > 0
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        ok = False
    except dns.exception.DNSException as e:
        logger.debug(f"MX lookup for {domain} inconclusive ({e}); keeping it")
        ok = True
    _mx_cache[domain] = ok
    return ok

async def filter_deliverable(emails: List[str]) -> List[str]:
    """Drop addresses whose domain cannot receive email (typos, dead domains, asset names)."""
    kept = []
    for email in emails:
        domain = email.rsplit("@", 1)[-1]
        if await domain_accepts_mail(domain):
            kept.append(email)
        else:
            logger.info(f"Dropping undeliverable email {email} (no MX for {domain})")
    return kept
