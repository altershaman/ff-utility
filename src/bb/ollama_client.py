import os
import sys

import requests


def _base_url() -> str:
    host = os.environ.get('OLLAMA_HOST', 'localhost:11434')
    if not host.startswith('http'):
        host = f'http://{host}'
    return host.rstrip('/')


def check_ollama(model: str) -> None:
    base = _base_url()
    try:
        resp = requests.get(f'{base}/api/tags', timeout=5)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        print(
            f'error: ollama is not reachable at {base}\n'
            'Start it with: ollama serve',
            file=sys.stderr,
        )
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f'error: ollama request failed: {e}', file=sys.stderr)
        sys.exit(1)

    models = [m['name'].split(':')[0] for m in resp.json().get('models', [])]
    if model not in models:
        print(
            f'error: model "{model}" is not available in ollama\n'
            f'Pull it with: ollama pull {model}',
            file=sys.stderr,
        )
        sys.exit(1)


def get_embedding(model: str, text: str) -> list[float]:
    base = _base_url()
    resp = requests.post(
        f'{base}/api/embed',
        json={'model': model, 'input': text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()['embeddings'][0]
