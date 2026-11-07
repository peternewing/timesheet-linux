#!/usr/bin/python3
"""Create an AppDir from distro packages. Build on the oldest target glibc."""
import glob,os,re,shutil,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]; app=Path(sys.argv[1]).resolve()
if app.exists(): raise SystemExit('Build directory already exists: '+str(app))
(app/'usr/bin').mkdir(parents=True);(app/'usr/lib').mkdir();(app/'usr/share').mkdir()
def cp(src,dst):
    src=Path(src);dst=Path(dst);dst.parent.mkdir(parents=True,exist_ok=True)
    if src.is_dir(): shutil.copytree(src,dst,symlinks=False,ignore_dangling_symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','test','tests','ensurepip'))
    else: shutil.copy2(src,dst,follow_symlinks=True)
cp(root/'packaging/appimage/AppRun',app/'AppRun')
cp(root/'packaging/appimage/org.local.TimeSheetLinux.desktop',app/'org.local.TimeSheetLinux.desktop')
cp(root/'resources/timesheet.svg',app/'org.local.TimeSheetLinux.svg')
cp('/usr/bin/python3',app/'usr/bin/python3')
cp('/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders',app/'usr/bin/gdk-pixbuf-query-loaders')
version=f'python{sys.version_info.major}.{sys.version_info.minor}'
cp('/usr/lib/'+version,app/'usr/lib'/version)
site=app/'usr/lib/python3/dist-packages';site.mkdir(parents=True)
for module in ('gi','cairo','reportlab','PIL','Xlib'):
    mod=__import__(module);cp(Path(mod.__file__).parent,site/module)
code=app/'usr/share/time-sheet-linux';code.mkdir()
for name in ('timesheet','resources'):cp(root/name,code/name)
cp('/usr/share/doc/fonts-dejavu-core/copyright',code/'resources/fonts/LICENSE-DejaVu.txt')
for font in ('DejaVuSans.ttf','DejaVuSans-Bold.ttf'):
    cp('/usr/share/fonts/truetype/dejavu/'+font,code/'resources/fonts'/font)
cp('/usr/lib/x86_64-linux-gnu/girepository-1.0',app/'usr/lib/girepository-1.0')
for item in ('glib-2.0/schemas','icons/Adwaita','icons/hicolor'):
    src=Path('/usr/share')/item
    if src.exists():cp(src,app/'usr/share'/item)
loaderdir=Path('/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/2.10.0/loaders')
# librsvg renamed this loader; Ubuntu 24.04 uses the hyphenated name.
loader=next((loaderdir/name for name in ('libpixbufloader_svg.so','libpixbufloader-svg.so') if (loaderdir/name).is_file()),None)
if loader is None: raise SystemExit('SVG pixbuf loader missing; install librsvg2-common')
cp(loader,app/'usr/lib/gdk-pixbuf/libpixbufloader_svg.so')
# Keep GIO modules compatible with the GLib shipped in the image.
giomod=app/'usr/lib/gio/modules';giomod.mkdir(parents=True)
for name in ('libdconfsettings.so','libgiognutls.so','libgiolibproxy.so'):
    src=Path('/usr/lib/x86_64-linux-gnu/gio/modules')/name
    if src.is_file(): cp(src,giomod/name)
# Resolve all ELF dependencies and typelib-declared libraries via the build host's ldconfig.
lookup={}
for line in subprocess.check_output(['ldconfig','-p'],text=True).splitlines():
    m=re.search(r'^\s*(\S+)\s+\([^)]*\)\s+=>\s+(\S+)',line)
    if m:lookup.setdefault(m[1],m[2])
queue=list(app.rglob('*.so'))+list(app.rglob('*.so.*'))+[app/'usr/bin/python3',app/'usr/bin/gdk-pixbuf-query-loaders']
for name in ('Adw-1','Gtk-4.0','Gdk-4.0','Gio-2.0','GObject-2.0','GLib-2.0','Graphene-1.0','Pango-1.0','PangoCairo-1.0','GdkPixbuf-2.0'):
    typ=app/'usr/lib/girepository-1.0'/(name+'.typelib')
    for lib in re.findall(r'[\w+.-]+\.so(?:\.\d+)*',subprocess.check_output(['strings',str(typ)],text=True)):
        if lib in lookup:queue.append(Path(lookup[lib]))
seen=set();exclude=re.compile(r'^(libc\.so|libm\.so|libpthread\.so|libdl\.so|librt\.so|libresolv\.so|libutil\.so|ld-linux)')
while queue:
    binary=Path(queue.pop())
    if not binary.exists() or str(binary) in seen:continue
    seen.add(str(binary))
    if not binary.is_relative_to(app):
        target=app/'usr/lib'/binary.name
        if not target.exists():cp(binary,target)
        binary=target
    result=subprocess.run(['ldd',str(binary)],capture_output=True,text=True)
    if 'not found' in result.stdout: raise SystemExit('Missing binary dependency: '+result.stdout)
    for lib,path in re.findall(r'\s*(\S+)\s+=>\s+(\/\S+)',result.stdout):
        if not exclude.match(lib):
            target=app/'usr/lib'/lib
            if not target.exists():cp(path,target);queue.append(target)
print('AppDir created at',app)
