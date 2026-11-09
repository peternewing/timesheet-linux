"""Read public release metadata only. Never download or execute an update."""
from __future__ import annotations
import json
import re
import urllib.request
from .jev import _NoRedirect

REPOSITORY='peternewing/timesheet-linux'
API='https://api.github.com/repos/'+REPOSITORY+'/releases?per_page=10'
PREFIX='https://github.com/'+REPOSITORY+'/releases/tag/'


def version(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?',value) if isinstance(value,str) and len(value)<80 else None
    if not match:raise ValueError('Unrecognised release version.')
    major,minor,patch,rc=match.groups()
    return int(major),int(minor),int(patch),int(rc) if rc else 10**9


def check(current,opener=None):
    client=opener or urllib.request.build_opener(_NoRedirect())
    try:
        request=urllib.request.Request(API,headers={'Accept':'application/vnd.github+json','User-Agent':'TimeSheetLinux-update-check'})
        with client.open(request,timeout=10) as response:body=response.read(512*1024+1)
        if len(body)>512*1024:raise ValueError('oversized release metadata')
        data=json.loads(body)
        if not isinstance(data,list) or len(data)>10:raise ValueError('invalid release list')
        releases=[]
        for item in data:
            if not isinstance(item,dict) or item.get('draft'):continue
            try:key=version(item.get('tag_name'))
            except ValueError:continue
            if item.get('html_url')!=PREFIX+item['tag_name']:continue
            assets=item.get('assets')
            if not isinstance(assets,list):continue
            names={a['name'] for a in assets if isinstance(a,dict) and isinstance(a.get('name'),str) and len(a['name'])<=128}
            if not {'TimeSheetLinux-x86_64.AppImage','TimeSheetLinux-x86_64.flatpak','SHA256SUMS'}<=names:continue
            releases.append((key,item['tag_name'],item['html_url'],'provenance.sigstore.json' in names))
        if not releases:raise ValueError('No complete published release was found.')
        latest=max(releases)
        return dict(version=latest[1],url=latest[2],newer=latest[0]>version(current),provenance=latest[3])
    except Exception as exc:
        raise ValueError('Could not verify the public release information. Check your connection or open GitHub Releases.') from None
