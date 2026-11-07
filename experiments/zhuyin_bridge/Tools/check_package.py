#!/usr/bin/env python3
"""Static packaging checks. These do not compile or validate Apple APIs."""
from pathlib import Path
import json, plistlib, re, sys

root=Path(__file__).resolve().parents[1]
data=json.loads((root/'Data/bridge.json').read_text())
generated=(root/'Shared/BridgeData.swift').read_text()
embedded=generated.split('#"""\n',1)[1].split('\n"""#',1)[0]
assert json.loads(embedded)==data
assert json.loads((root/'Web/data.js').read_text().removeprefix('globalThis.BRIDGE_DATA = ').removesuffix(';\n'))==data
for relative in ('App/Info.plist','KeyboardExtension/Info.plist','PrivacyInfo.xcprivacy'):
    with (root/relative).open('rb') as f:plistlib.load(f)
with (root/'KeyboardExtension/Info.plist').open('rb') as f: extension=plistlib.load(f)
assert extension['NSExtension']['NSExtensionAttributes']['RequestsOpenAccess'] is False
assert extension['NSExtension']['NSExtensionPointIdentifier']=='com.apple.keyboard-service'
project=(root/'ZhuyinBridge.xcodeproj/project.pbxproj').read_text()
for path in re.findall(r'"path" = "([^"]+)";',project):
    if not path.endswith(('.app','.appex')):assert (root/path).is_file(),path
required=['App/TERMS_DRAFT.txt','docs/USER_TERMS_DRAFT_ZH.md','docs/APPLE_POLICY_PROPOSAL_ZH.md','docs/PR_DRAFT.md','README.md']
for p in required:assert (root/p).is_file(),p
terms = re.sub(r'^#+ ', '', (root/'docs/USER_TERMS_DRAFT_ZH.md').read_text(), flags=re.M)
assert (root/'App/TERMS_DRAFT.txt').read_text() == terms
honey='（ChatGPT好用吗？好用就在AppStore点个五星好评吧！）'
assert honey in (root/'App/ZhuyinBridgeApp.swift').read_text()
assert honey in (root/'Web/index.html').read_text()
assert 'ChatGPT' not in (root/'KeyboardExtension/KeyboardViewController.swift').read_text()
sources='\n'.join(p.read_text() for d in ['App','Shared','KeyboardExtension'] for p in (root/d).glob('*.swift'))
for forbidden in ['URLSession','UIPasteboard','UserDefaults','documentContextBeforeInput','documentContextAfterInput','import Network','import CloudKit','print(']:
    assert forbidden not in sources,forbidden
print('PASS: identical shared data, valid XML plists, no-open-access configuration, resource paths, user-requested copy, static network/storage/context checks.')
