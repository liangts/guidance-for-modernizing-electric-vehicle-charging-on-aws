"""Build a minimal source overlay over a pinned running image; optionally push it.

This avoids rebuilding OS/Python dependencies during the protocol cutover. It is
also usable when a local Docker daemon is unavailable. Only gateway.py enters the
new layer; credentials, certificates and the rest of the checkout never do.
"""
import argparse
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

import boto3
import requests


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, separators=(',', ':')).encode()


def upload_blob(client, repository, data):
    checksum = digest(data)
    response = client.batch_check_layer_availability(repositoryName=repository, layerDigests=[checksum])
    if any(item.get('layerAvailability') == 'AVAILABLE' for item in response.get('layers', [])):
        return checksum
    upload = client.initiate_layer_upload(repositoryName=repository)
    # These code/config blobs are small; one final part is sufficient.
    client.upload_layer_part(repositoryName=repository, uploadId=upload['uploadId'],
                             partFirstByte=0, partLastByte=len(data) - 1, layerPartBlob=data)
    client.complete_layer_upload(repositoryName=repository, uploadId=upload['uploadId'], layerDigests=[checksum])
    return checksum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--base-digest', required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--region', default='us-east-2')
    parser.add_argument('--push', action='store_true')
    args = parser.parse_args()
    client = boto3.client('ecr', region_name=args.region)
    image = client.batch_get_image(repositoryName=args.repository,
                                   imageIds=[{'imageDigest': args.base_digest}])['images'][0]
    original = image['imageManifest'].encode()
    assert digest(original) == args.base_digest
    manifest = json.loads(original)
    authorization = client.get_authorization_token()['authorizationData'][0]
    registry = authorization['proxyEndpoint']
    response = requests.get(f"{registry}/v2/{args.repository}/blobs/{manifest['config']['digest']}",
                            headers={'Authorization': 'Basic ' + authorization['authorizationToken']}, timeout=45)
    if response.status_code != 200:
        raise RuntimeError('Unable to retrieve the pinned image configuration')
    assert digest(response.content) == manifest['config']['digest']
    config = json.loads(response.content)
    assert config['architecture'] == 'arm64', 'This deployment targets the verified ARM64 gateway'
    source = args.source.read_bytes()
    compile(source, 'gateway.py', 'exec')
    assert b'AWS_SECRET_ACCESS_KEY' not in source and b'AKIA' not in source
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as layer:
        member = tarfile.TarInfo('home/appuser/ocpp-gateway/gateway.py')
        member.size = len(source)
        member.mode = 0o644
        member.mtime = 0
        layer.addfile(member, io.BytesIO(source))
    raw_layer = archive.getvalue()
    compressed = gzip.compress(raw_layer, mtime=0)
    now = datetime.now(timezone.utc).isoformat()
    config['rootfs']['diff_ids'].append(digest(raw_layer))
    config.setdefault('history', []).append({'created': now, 'created_by': 'PR3 gateway envelope overlay'})
    config['created'] = now
    config.setdefault('config', {}).setdefault('Labels', {}).update({
        'org.voltio.pr3.base-digest': args.base_digest,
        'org.voltio.pr3.gateway-source-sha256': digest(source),
    })
    config_bytes = encode(config)
    updated = copy.deepcopy(manifest)
    updated['config'].update(digest=digest(config_bytes), size=len(config_bytes))
    updated['layers'].append({'mediaType': 'application/vnd.docker.image.rootfs.diff.tar.gzip',
                              'size': len(compressed), 'digest': digest(compressed)})
    manifest_bytes = encode(updated)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in [('layer.tar.gz', compressed), ('config.json', config_bytes), ('manifest.json', manifest_bytes)]:
        (args.output / name).write_bytes(data)
    summary = {'baseDigest': args.base_digest, 'imageDigest': digest(manifest_bytes),
               'sourceSha256': digest(source), 'tag': args.tag, 'architecture': config['architecture']}
    if args.push:
        upload_blob(client, args.repository, compressed)
        upload_blob(client, args.repository, config_bytes)
        pushed = client.put_image(repositoryName=args.repository, imageTag=args.tag,
                                  imageManifest=manifest_bytes.decode(), imageDigest=digest(manifest_bytes))
        assert pushed['image']['imageId']['imageDigest'] == summary['imageDigest']
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
