import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const XML = `<node><interface name="org.local.TimeSheetCapture">
  <method name="GetState"><arg type="s" direction="out"/><arg type="s" direction="out"/><arg type="x" direction="out"/><arg type="b" direction="out"/></method>
</interface></node>`;

export default class TimeSheetCapture extends Extension {
    enable() {
        this._object = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this._object.export(Gio.DBus.session, '/org/local/TimeSheetCapture');
        this._owner = Gio.bus_own_name_on_connection(Gio.DBus.session,
            'org.local.TimeSheetCapture', Gio.BusNameOwnerFlags.NONE, null, null);
        this._indicator = new PanelMenu.Button(0.0, 'Time Sheet Linux');
        this._indicator.add_child(new St.Icon({icon_name: 'alarm-symbolic', style_class: 'system-status-icon'}));
        this._status = new PopupMenu.PopupMenuItem('Time Sheet Linux', {reactive: false});
        this._indicator.menu.addMenuItem(this._status);
        this._indicator.menu.addAction('Open timesheet', () => this._launch());
        this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._indicator.menu.addAction('Pause automatic tracking', () => this._launch('Pause'));
        this._indicator.menu.addAction('Resume automatic tracking', () => this._launch('Resume'));
        Main.panel.addToStatusArea(this.uuid, this._indicator);
        this._timeout = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 5, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
        this._refresh();
    }
    _launch(action = null) {
        const app = Gio.DesktopAppInfo.new('org.local.TimeSheetLinux.desktop');
        if (!app) return;
        if (action) app.launch_action(action, null);
        else app.launch([], null);
    }
    _refresh() {
        let status = 'Open Time Sheet Linux to get started';
        try {
            const path = GLib.build_filenamev([GLib.get_user_data_dir(), 'time-sheet-linux', 'health.json']);
            const [, bytes] = GLib.file_get_contents(path);
            const data = JSON.parse(new TextDecoder().decode(bytes));
            const fresh = Date.now() / 1000 - data.at < 15;
            if (fresh) {
                const labels = {active: 'Tracking automatically', paused: 'Tracking paused',
                    setup_required: 'Waiting for capture', degraded: 'Tracking needs attention', error: 'Recording failed', stopped: 'Tracking stopped'};
                status = labels[data.status] ?? 'Open timesheet';
            } else status = 'Tracking stopped';
        } catch (_) {}
        this._status.label.text = status;
    }
    GetState() {
        const win = global.display.focus_window;
        const app = win ? Shell.WindowTracker.get_default().get_window_app(win) : null;
        let idle = -1;
        try { idle = global.backend.get_core_idle_monitor().get_idletime(); } catch (_) {}
        let locked = true;
        try {
            const value = Main.screenShield.locked;
            if (typeof value === 'boolean') locked = value;
        } catch (_) {}
        return [app?.get_name() ?? '', win?.get_title() ?? '', idle, locked];
    }
    disable() {
        if (this._timeout) GLib.source_remove(this._timeout);
        this._timeout = 0;
        this._indicator?.destroy();
        this._indicator = null;
        this._status = null;
        if (this._owner) Gio.bus_unown_name(this._owner);
        this._object?.unexport();
        this._object = null;
        this._owner = 0;
    }
}
