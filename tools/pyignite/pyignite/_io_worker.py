"""Private stdin/stdout protocol for trusted process-isolated I/O providers."""
import contextlib
import hashlib
import importlib
import io
import json
import sys


def resolve(spec):
    module, sep, name = spec.partition(':')
    if not sep or not module or not name or any(p.startswith('_') for p in name.split('.')):
        raise ValueError('expected trusted module:public_callable')
    target = importlib.import_module(module)
    for part in name.split('.'):
        target = getattr(target, part)
    return target


def main():
    raw = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('request too large')
    request = json.loads(raw)
    if request.get('schema_version') != 1 or not isinstance(request.get('nonce'), str):
        raise ValueError('invalid protocol')
    action = request['action']
    # Provider stdout must not be mistaken for a protocol receipt.
    with contextlib.redirect_stdout(io.StringIO()):
        if action == 'read':
            value = resolve(request['reader_spec'])(**request['reader_kwargs'])
        else:
            store = resolve(request['store_spec'])(request['path'])
            if action == 'exists':
                value = store.exists()
            elif action == 'load':
                value = store.load()
            elif action == 'commit':
                value = store.commit(request['payload'])
                if value not in ('FILE_AND_DIRECTORY_FSYNC_COMPLETED', 'FILE_FSYNC_ONLY'):
                    raise ValueError('unknown durability receipt')
            else:
                raise ValueError('unsupported action')
    response = {'schema_version': 1, 'nonce': request['nonce'], 'action': action,
                'request_sha256': hashlib.sha256(raw).hexdigest(), 'ok': True, 'value': value}
    encoded = json.dumps(response, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(encoded.encode()) > 8 * 1024 * 1024:
        raise ValueError('response too large')
    print(encoded, flush=True)


if __name__ == '__main__':
    main()
