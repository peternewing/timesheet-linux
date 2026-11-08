#!/usr/bin/python3
"""Exercise libsecret's portal-only backend on a private D-Bus session.

Run through dbus-run-session. All stored values and portal secrets are synthetic.
Use --flatpak APP_ID to run the client in an already installed test bundle.
"""
from __future__ import annotations

import argparse
import os
import select
import subprocess
import sys
import warnings


CLIENT = r'''
import os
from pathlib import Path
import sys
import tempfile
with tempfile.TemporaryDirectory(prefix='timesheet-keyring-test-') as folder:
    os.environ['XDG_DATA_HOME']=folder
    os.environ['SECRET_BACKEND']='file'
    os.environ['GIO_USE_VFS']='local'
    # Native tests follow the same portal branch used by /.flatpak-info.
    os.environ['SNAP_NAME']='timesheet-keyring-test'
    os.environ.pop('SECRET_FILE_TEST_PATH',None)
    os.environ.pop('SECRET_FILE_TEST_PASSWORD',None)
    import gi
    gi.require_version('Secret','1')
    from gi.repository import Secret, GLib
    schema=Secret.Schema.new('org.local.TimeSheetLinux.PackagingTest',Secret.SchemaFlags.NONE,{'scope':Secret.SchemaAttributeType.STRING})
    value='synthetic-timesheet-key-never-a-real-credential'
    success=False
    try:
        success=Secret.password_store_sync(schema,{'scope':'disposable'},Secret.COLLECTION_DEFAULT,'Disposable packaging test',value,None)
    except GLib.Error:
        pass
    if sys.argv[1]=='missing':
        assert not success, 'Portal-only storage unexpectedly succeeded without the Secret portal'
        for file in Path(folder).rglob('*'):
            if file.is_file(): assert value.encode() not in file.read_bytes(), 'Plaintext secret was written'
        print('PASS: missing Secret portal fails closed',flush=True)
    else:
        assert success, 'Secret portal storage failed'
        assert Secret.password_lookup_sync(schema,{'scope':'disposable'},None)==value
        files=[file for file in Path(folder).rglob('*') if file.is_file()]
        assert files, 'Expected encrypted application-scoped secret file'
        for file in files: assert value.encode() not in file.read_bytes(), 'Plaintext secret was written'
        assert Secret.password_clear_sync(schema,{'scope':'disposable'},None)
        assert Secret.password_lookup_sync(schema,{'scope':'disposable'},None) is None
        print('PASS: portal-scoped encrypted key store/read/remove',flush=True)
'''


def serve(mode):
    warnings.filterwarnings('ignore',category=DeprecationWarning,message='Gio.DBusConnection.register_object is deprecated')
    import gi
    from gi.repository import Gio, GLib
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    if mode=='present':
        xml='''<node><interface name="org.freedesktop.portal.Secret">
        <property name="version" type="u" access="read"/>
        <method name="RetrieveSecret"><arg type="h" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
        </interface></node>'''
    else:
        xml='<node><interface name="org.local.TimeSheetNoSecretPortal"><method name="Ping"/></interface></node>'
    node=Gio.DBusNodeInfo.new_for_xml(xml)

    def method(connection,sender,path,interface,name,parameters,invocation):
        if name!='RetrieveSecret':
            invocation.return_value(None); return
        descriptor,options=parameters.unpack()
        descriptors=invocation.get_message().get_unix_fd_list()
        fds=descriptors.steal_fds()
        try: os.write(fds[descriptor],b'disposable-portal-master-secret!!'*2)
        finally:
            for fd in fds: os.close(fd)
        token=options['handle_token']
        handle='/org/freedesktop/portal/desktop/request/'+sender[1:].replace('.','_')+'/'+token
        invocation.return_value(GLib.Variant('(o)',(handle,)))
        def respond():
            connection.emit_signal(sender,handle,'org.freedesktop.portal.Request','Response',GLib.Variant('(ua{sv})',(0,{})))
            return False
        GLib.timeout_add(20,respond)

    def prop(*args): return GLib.Variant('u',1)
    registration=bus.register_object('/org/freedesktop/portal/desktop',node.interfaces[0],method,prop,None)
    owner=Gio.bus_own_name_on_connection(bus,'org.freedesktop.portal.Desktop',Gio.BusNameOwnerFlags.NONE,lambda *_:print('READY',flush=True),None)
    GLib.MainLoop().run()


def check(flatpak_id=None):
    if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        raise SystemExit('Run this test through dbus-run-session.')
    for mode in ('missing','present'):
        server=subprocess.Popen([sys.executable,__file__,'--serve',mode],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            if not select.select([server.stdout],[],[],10)[0] or server.stdout.readline().strip()!='READY':
                raise RuntimeError('Private test portal did not become ready')
            command=[sys.executable,'-c',CLIENT,mode]
            if flatpak_id:
                command=['flatpak','run','--user','--no-documents-portal','--env=SECRET_BACKEND=file','--command=python3',flatpak_id,'-c',CLIENT,mode]
            subprocess.run(command,check=True,timeout=30)
        finally:
            server.terminate()
            try: output,errors=server.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill();output,errors=server.communicate()
            if errors: print(errors,file=sys.stderr)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve',choices=('missing','present'))
    parser.add_argument('--flatpak',metavar='APP_ID')
    args=parser.parse_args()
    if args.serve: serve(args.serve)
    else: check(args.flatpak)
