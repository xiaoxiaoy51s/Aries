import re


def normalize_base_url(url: str) -> str:
    url = re.sub(r'[`\'"\s]', '', url or '')
    url = url.strip()
    if url and not url.startswith(('http://', 'https://', 'ws://', 'wss://')):
        url = 'https://' + url
    return url
