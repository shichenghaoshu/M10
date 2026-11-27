#!/usr/bin/env python3
"""Check the public snapshot without printing matching secret values."""
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
SKIP={'.git','.venv','venv','.m10','build','__pycache__','.pytest_cache','.gradle','node_modules'}
PATTERNS={
    'private-key-material':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'github-token':re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'openai-key':re.compile(r'sk-(?:proj|svcacct)-[A-Za-z0-9_-]{20,}'),
    'aws-access-key':re.compile(r'AKIA[A-Z0-9]{16}'),
    'author-home-path':re.compile('/Users/'+'admin'),
}
errors=[]
count=0
for p in ROOT.rglob('*'):
    if not p.is_file() or any(x in SKIP for x in p.relative_to(ROOT).parts):continue
    if p.is_symlink():
        if not p.resolve().is_relative_to(ROOT):errors.append((str(p.relative_to(ROOT)),'external-symlink'))
        continue
    rel=str(p.relative_to(ROOT))
    if p.name in {'.env','local.properties'} or p.suffix in {'.pem','.key','.jks','.keystore','.p12','.rknn','.pt','.onnx','.tflite','.img'}:
        errors.append((rel,'excluded-file-type'))
    if p.stat().st_size>50*1024*1024:errors.append((rel,'file-over-50MiB'))
    try:s=p.read_text()
    except (UnicodeDecodeError,OSError):continue
    count+=1
    for name,pattern in PATTERNS.items():
        if pattern.search(s):errors.append((rel,name))
if errors:
    for rel,reason in errors:print(f'FAIL {reason}: {rel}')
    sys.exit(1)
print(f'PASS publication scan: {count} text files checked')
