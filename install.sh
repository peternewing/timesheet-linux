#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ "$(id -u)" = 0 ]; then
    echo 'Run ./install.sh as your normal desktop user, not with sudo.' >&2
    exit 1
fi
if ! /usr/bin/python3 -c 'import sys; assert sys.version_info >= (3,10); import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); from gi.repository import Gtk, Adw; assert (Adw.get_major_version(), Adw.get_minor_version()) >= (1,5)' >/dev/null 2>&1; then
    echo 'Python 3.10+, PyGObject, GTK 4 and libadwaita 1.5+ are required.' >&2
    echo 'See docs/INSTALL.md for Ubuntu/Debian, Fedora, Arch and openSUSE commands.' >&2
    echo 'Ubuntu/Debian: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1' >&2
    exit 1
fi
if ! /usr/bin/python3 -c 'import reportlab' >/dev/null 2>&1; then
    echo 'Optional PDF export: install your distribution reportlab package (see docs/INSTALL.md).' >&2
fi
exec /usr/bin/python3 -m timesheet.app --install
