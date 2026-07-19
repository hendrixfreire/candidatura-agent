"""Extrai com segurança o destino externo de uma página autenticada do LinkedIn."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit


def _is_linkedin(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def select_offsite_apply_url(anchors: Iterable[Mapping[str, str]]) -> str | None:
    """Retorna o link HTTPS externo associado à ação Apply/Aplicar.

    A página autenticada do LinkedIn contém vários links externos (privacidade,
    empresa e anúncios). Só um link com texto de ação é candidato a destino de
    candidatura; links LinkedIn nunca são devolvidos.
    """
    for anchor in anchors:
        href = str(anchor.get("href") or anchor.get("url") or "").strip()
        text = str(anchor.get("text") or "").strip().casefold()
        if not href.startswith("https://") or _is_linkedin(href):
            continue
        if any(token in text for token in ("apply", "aplicar", "candidate", "candidatar")):
            return href
    return None
