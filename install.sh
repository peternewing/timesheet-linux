#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! /usr/bin/python3 -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); from gi.repository import Gtk, Adw; assert Adw.get_major_version()>1 or Adw.get_minor_version()>=5' >/dev/null 2>&1; then
    echo 'Install dependencies first:' >&2
    echo '  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1' >&2
    exit 1
fi
exec /usr/bin/python3 -m timesheet.app --install
