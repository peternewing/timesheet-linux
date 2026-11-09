"""A local-first desktop activity timeline and billing review app."""
from __future__ import annotations
import argparse
import calendar
import fcntl
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
gi.require_version('Graphene','1.0')
from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gtk, Pango
from .store import Store, DATA_DIR, parse_money, parse_hours, local_timestamp
from . import desktop, __version__
from .automation_ui import AutomationUI
from .simple_ui import SimpleUI

APP_ID=desktop.APP_ID
ROOT=desktop.ROOT
PAGES=('Today','Calendar','History','Projects','Rules','Reports','Settings')
PAGE_ICONS=('go-home-symbolic','x-office-calendar-symbolic','document-open-recent-symbolic','folder-symbolic','emblem-system-symbolic','x-office-spreadsheet-symbolic','preferences-system-symbolic')

def fmt_duration(seconds):
    seconds=max(0,int(seconds))
    if seconds<60: return f'{seconds}s'
    return f'{seconds//3600}h {(seconds%3600)//60:02d}m {seconds%60:02d}s' if seconds>=3600 else f'{seconds//60}m {seconds%60:02d}s'

def fmt_timer(seconds):
    seconds=max(0,int(seconds))
    return f'{seconds//3600:02d}:{(seconds%3600)//60:02d}:{seconds%60:02d}'

def set_changed_text(widget,text):
    if widget.get_text()!=text: widget.set_text(text)

def fmt_time(ts): return datetime.fromtimestamp(ts).strftime('%d %b %H:%M')
def money(minor): return f'{Decimal(minor)/100:,.2f}'
def day_bounds(day):
    return (int(datetime.combine(day,datetime.min.time()).timestamp()),
            int(datetime.combine(day+timedelta(days=1),datetime.min.time()).timestamp()))
def parse_local(text): return local_timestamp(text)
def button(text,callback,primary=False):
    w=Gtk.Button(label=text); w.connect('clicked',callback)
    child=w.get_child()
    if isinstance(child,Gtk.Label):child.set_wrap(True);child.set_wrap_mode(Pango.WrapMode.WORD_CHAR);child.set_max_width_chars(60)
    if primary: w.add_css_class('suggested-action')
    return w

def label(text,css=None,*,selectable=True):
    if css in ('title-1','title-3','heading','metric','brand','field-label'): selectable=False
    w=Gtk.Label(label=str(text),xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,selectable=selectable)
    if css: w.add_css_class(css)
    return w

def field(box,title,default='',placeholder=''):
    group=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6,hexpand=True); box.append(group)
    caption=label(title,'field-label',selectable=False); group.append(caption)
    w=Gtk.Entry(); w.set_text(str(default)); w.set_placeholder_text(placeholder); w.set_activates_default(True)
    w.update_property([Gtk.AccessibleProperty.LABEL],[title]); caption.set_mnemonic_widget(w); group.append(w); return w

def dropdown(box,title,values):
    group=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6,hexpand=True); box.append(group)
    caption=label(title,'field-label',selectable=False); group.append(caption)
    w=Gtk.DropDown.new_from_strings([name for _,name in values] or ['No choices yet']); w._values=values
    factory=Gtk.SignalListItemFactory()
    def setup(_,item):item.set_child(Gtk.Label(xalign=0,ellipsize=Pango.EllipsizeMode.END,max_width_chars=60,hexpand=True))
    def bind(_,item):
        text=item.get_item().get_string();item.get_child().set_text(text);item.get_child().set_tooltip_text(text)
    factory.connect('setup',setup);factory.connect('bind',bind);w.set_factory(factory)
    if len(values)>8: w.set_enable_search(True)
    w.update_property([Gtk.AccessibleProperty.LABEL],[title]); caption.set_mnemonic_widget(w); group.append(w); return w

def action_bar():
    return Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=8,row_spacing=8,
                       homogeneous=False,min_children_per_line=1,max_children_per_line=8)

def selected(w):
    i=w.get_selected(); return w._values[i][0] if i<len(w._values) else None

def select_id(w,value):
    for i,(v,_) in enumerate(w._values):
        if v==value: w.set_selected(i); break

def append_in_batches(container, items, render, size=50):
    """Render a bounded number of rows at a time without hiding later results."""
    rows=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10); container.append(rows)
    more=button('Show more',lambda _:load()); container.append(more)
    offset=0
    def load():
        nonlocal offset
        for item in items[offset:offset+size]: render(rows,item)
        offset=min(len(items),offset+size)
        more.set_visible(offset<len(items))
        if offset<len(items): more.set_label(f'Show more ({len(items)-offset} remaining)')
    load()

def margins(w,n):
    for side in ('start','end','top','bottom'): getattr(w,'set_margin_'+side)(n)
    return w

def group_activity(records):
    groups=[]
    for record in records:
        key=(record['app'],record['title'],record['state'],record['closed'],datetime.fromtimestamp(record['start']).date())
        if groups and groups[-1]['key']==key and groups[-1]['end']==record['start']:
            groups[-1]['end']=record['end']; groups[-1]['blocks'].append(record)
        else:
            groups.append(dict(record,key=key,blocks=[record]))
    return groups

class Timeline(Gtk.Widget):
    """Native GTK snapshot rendering; no optional Cairo bindings required."""
    def __init__(self,start,end,records):
        super().__init__(hexpand=True)
        self.start,self.end,self.records=start,end,records
        self.set_size_request(100,52)
        self.set_tooltip_text('24-hour activity timeline. The activity list below provides exact times and states.')
        self.update_property([Gtk.AccessibleProperty.LABEL],['24-hour activity timeline. Exact times and states are listed below.'])
    def do_snapshot(self,snapshot):
        width=self.get_width();height=26
        def rectangle(color,x,w):
            rgba=Gdk.RGBA();rgba.parse(color)
            rect=Graphene.Rect();rect.init(float(x),0,float(w),float(height));snapshot.append_color(rgba,rect)
        rectangle('rgba(128,128,128,0.15)',0,width)
        colors={'active':'#4c87ce','personal':'#6da68b','away':'#9299a4','locked':'#555e6c','excluded':'#b4834c','unknown':'#bf6464'}
        for r in self.records:
            x=(r['start']-self.start)/(self.end-self.start)*width;z=(r['end']-self.start)/(self.end-self.start)*width
            rectangle(colors.get(r['state'],'#888888'),x,max(1,z-x))
        date=datetime.fromtimestamp(self.start).date()
        for hour in (0,6,12,18,24):
            tick=self.end if hour==24 else int(datetime.combine(date,datetime.min.time()).replace(hour=hour).timestamp())
            text=f'{hour:02d}:00';layout=self.create_pango_layout(text);layout.set_font_description(Pango.FontDescription.from_string('Sans 9'))
            text_width,_=layout.get_pixel_size();x=(tick-self.start)/(self.end-self.start)*width
            x=max(0,min(width-text_width,x-text_width/2))
            point=Graphene.Point();point.init(x,32);color=Gdk.RGBA();color.parse('#999999')
            snapshot.save();snapshot.translate(point);snapshot.append_layout(layout,color);snapshot.restore()


class TimeSheet(SimpleUI,AutomationUI,Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.store=Store(); self.win=None; self.day=datetime.now().date(); self.page='Today'
        self.automation_repo()
        self.dialog_count=0; self.last_refresh=0; self.history_search=''; self.history_period='month'; self.history_status='all'
        self.dialogs=[]
        self.timer_label=None; self.timer_started=None
        self.live_signature=None; self.today_metrics={}; self.today_apps={}; self.calendar_live={}; self.history_live={}
        self.project_live={}; self.task_live={}; self.task_projects={}
        self.history_kind='tasks'
        self.history_from=datetime.now().date().replace(day=1); self.history_to=datetime.now().date(); self.history_billable='all'; self.project_search=''
        self.activity_filter='all'; self.selected_entries=set(); self.selected_blocks=[]; self.rendered_signature=None

    def do_activate(self):
        if self.win:
            self.win.present(); return
        self.win=Adw.ApplicationWindow(application=self,title='Time Sheet Linux',default_width=960 if self.simple_mode() else 1120,default_height=800)
        self.win.set_icon_name(APP_ID)
        self.win.connect('close-request',self.close_window)
        provider=Gtk.CssProvider(); provider.load_from_path(str(ROOT/'resources/style.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.toasts=Adw.ToastOverlay(); self.win.set_content(self.toasts)
        layout=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.toasts.set_child(layout)
        header=Adw.HeaderBar(); layout.append(header)
        self.status=Gtk.Label(label='Starting…'); self.status.add_css_class('status-pill'); header.pack_start(self.status)
        self.timer_button=button('00:00:00',lambda _:self.show_page('Today'))
        self.timer_button.add_css_class('timer-digits'); self.timer_button.set_tooltip_text('Running task timer · hours:minutes:seconds · Open Today')
        self.timer_button.set_visible(False); header.pack_start(self.timer_button)
        self.capture_button=button('Pause',self.toggle_capture); header.pack_end(self.capture_button)
        self.start_timer_button=button('Start timer',lambda _:self.timer_dialog()); header.pack_start(self.start_timer_button);self.start_timer_button.set_visible(not self.simple_mode())
        self.undo_button=button('Undo',lambda _:self.run_action(self.store.undo,lambda action:self.toast(action+' undone'))); header.pack_end(self.undo_button);self.undo_button.set_visible(not self.simple_mode())
        if not self.simple_mode():header.pack_end(button('Refresh',lambda _:self.show_page(self.page)))
        if not self.simple_mode():header.pack_end(button('About',lambda _:self.info('About Time Sheet Linux', 'Version '+__version__+'\n\nRecording stays local. Optional Jev requests send only the data permitted by your chosen policy.')) )
        if not self.simple_mode():header.pack_end(button('Help',lambda _:self.info('From activity to a client report',
            '1. Projects: create a client, project and task. Set an hourly rate for billable work.\n\n'
            '2. Calendar: review captured activity and assign it to a task. Use Add time for work you recorded manually.\n\n'
            '3. History: check your entries and approve the drafts. Approval freezes the rate.\n\n'
            '4. Reports: create a report from approved work, export it, then mark it billed with your invoice reference.\n\n'
            'Draft = editable work. Approved = reviewed and ready to report. Billed = locked to protect your invoice history.\n\n'
            'Keyboard: Ctrl+1–7 opens pages, Ctrl+N creates a project, Ctrl+Z undoes an entry edit, Ctrl+R refreshes. Escape closes an edit form.')))
        split=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL); split.set_vexpand(True); layout.append(split)
        sidebar=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4); sidebar.add_css_class('sidebar'); margins(sidebar,12); sidebar.set_size_request(140 if self.simple_mode() else 172,-1); split.append(sidebar)
        sidebar.append(margins(label('TIME SHEET','brand'),8)); self.nav={}
        for name,icon in zip(PAGES,PAGE_ICONS):
            display_name='Past days' if name=='Calendar' and self.simple_mode() else name
            b=Gtk.Button(); inner=Gtk.Box(spacing=10); inner.append(Gtk.Image.new_from_icon_name(icon)); inner.append(label(display_name,selectable=False)); b.set_child(inner)
            b.add_css_class('flat'); b.update_property([Gtk.AccessibleProperty.LABEL],[display_name]); b.set_tooltip_text(f'{display_name} (Ctrl+{len(self.nav)+1})'); b.connect('clicked',lambda _,n=name:self.show_page(n)); sidebar.append(b); self.nav[name]=b
            if self.simple_mode():b.set_visible(name in ('Today','Calendar','Settings'))
        spacer=Gtk.Box(); spacer.set_vexpand(True); sidebar.append(spacer); sidebar.append(label('Private • on this computer','dim-label'))
        self.stack=Gtk.Stack(hexpand=True,vexpand=True); split.append(self.stack)
        for name in PAGES:
            scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            clamp=Adw.Clamp(maximum_size=1200,tightening_threshold=900)
            body=margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16),24)
            clamp.set_child(body); scroll.set_child(clamp); self.stack.add_named(scroll,name); setattr(self,'body_'+name.lower(),body)
        desktop.start_collector(); self.show_page('Today'); self.tick()
        self.tick_source=GLib.timeout_add(250,self.tick)
        self.timer_source=None if self.simple_mode() else GLib.timeout_add(200,self.update_timer_display); self.win.present()
        for name,callback,keys in [
            ('today',lambda *_:self.show_page('Today'),['<Control>1']),
            ('calendar',lambda *_:self.show_page('Calendar'),['<Control>2']),
            ('history',lambda *_:self.show_page('History'),['<Control>3']),
            ('projects',lambda *_:self.show_page('Projects'),['<Control>4']),
            ('rules',lambda *_:self.show_page('Rules'),['<Control>5']),
            ('reports',lambda *_:self.show_page('Reports'),['<Control>6']),
            ('settings',lambda *_:self.show_page('Settings'),['<Control>7']),
            ('new-project',self.quick_setup,['<Control>n']),
            ('undo',lambda *_:self.run_action(self.store.undo),['<Control>z']),
            ('refresh',lambda *_:self.show_page(self.page),['<Control>r'])]:
            action=Gio.SimpleAction.new(name,None); action.connect('activate',callback); self.add_action(action); self.set_accels_for_action('app.'+name,keys)

    def close_window(self,*_):
        if getattr(self,'tick_source',None): GLib.source_remove(self.tick_source); self.tick_source=None
        if getattr(self,'timer_source',None): GLib.source_remove(self.timer_source); self.timer_source=None
        self.store.close(); self.win=None
        return False

    def toast(self,message): self.toasts.add_toast(Adw.Toast(title=str(message),timeout=4))
    def info(self,title,message): self.message(title,message)
    def error(self,message): self.message('Could not complete that action',str(message))
    def message(self,title,message):
        d=Adw.AlertDialog(heading=title,body=str(message)); d.add_response('close','Close'); d.set_default_response('close'); d.present(self.dialogs[-1] if self.dialogs else self.win)
    def confirm(self,title,body,action):
        d=Adw.AlertDialog(heading=title,body=body); d.add_response('cancel','Cancel'); d.add_response('confirm','Continue'); d.set_response_appearance('confirm',Adw.ResponseAppearance.DESTRUCTIVE); d.set_close_response('cancel')
        d.connect('response',lambda _,r:self.run_action(action) if r=='confirm' else None); d.present(self.dialogs[-1] if self.dialogs else self.win)
    def ai_consent(self,title,preview,respond,send_label='Send and suggest'):
        """Scrollable data preview; opening it never reads a key or sends data."""
        parent=self.dialogs[-1] if self.dialogs else self.win
        window=Adw.Window(title=title,transient_for=parent,modal=True,default_width=620,default_height=620)
        self.dialogs.append(window); self.dialog_count=len(self.dialogs); sent=[False]
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);window.set_content(box)
        header=Adw.HeaderBar();box.append(header)
        header.pack_start(button('Cancel',lambda _:window.close()))
        def send(_):
            sent[0]=True;window.close()
            GLib.idle_add(lambda:(respond(True),False)[1])
        header.pack_end(button(send_label,send,True))
        scroll=Gtk.ScrolledWindow(vexpand=True);box.append(scroll)
        content=margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12),20);scroll.set_child(content)
        self.heading(content,title,'TypeSafe receives the information below using your own account.')
        content.append(label(preview))
        def closed(*_):
            self.dialog_closed(window)
            if not sent[0]: respond(False)
            return False
        keys=Gtk.EventControllerKey()
        keys.connect('key-pressed',lambda _,key,*args:(window.close(),True)[1] if key==Gdk.KEY_Escape else False)
        window.add_controller(keys)
        window.connect('close-request',closed);window.present()
    def run_action(self,fn,success=None):
        try:
            result=fn()
            if success: success(result)
            # Finish the click/keyboard event before replacing its focused widget.
            GLib.idle_add(self.refresh_after_action)
        except (ValueError,sqlite3.Error,OSError,OverflowError) as exc: self.error(self.friendly_error(exc))
    def refresh_after_action(self):
        if self.win: self.show_page(self.page)
        return False
    def friendly_error(self,exc):
        if isinstance(exc,sqlite3.IntegrityError) and 'UNIQUE constraint' in str(exc): return 'That name is already in use here. Choose a different name or edit the existing item.'
        if isinstance(exc,OverflowError): return 'That number is too large. Enter a smaller value.'
        return str(exc)
    def dialog(self,title,build,save):
        d=Adw.Window(title=title,transient_for=self.dialogs[-1] if self.dialogs else self.win,modal=True,default_width=480,default_height=620)
        self.dialog_count+=1
        self.dialogs.append(d)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); d.set_content(box)
        head=Adw.HeaderBar(); box.append(head)
        content=margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10),20)
        scroll=Gtk.ScrolledWindow(vexpand=True); scroll.set_child(content); box.append(scroll)
        fields=build(content)
        def commit(_):
            try: save(fields)
            except (ValueError,sqlite3.Error,OSError,OverflowError) as exc: self.error(self.friendly_error(exc)); return
            d.close(); self.show_page(self.page)
        head.pack_start(button('Cancel',lambda _:d.close())); save_button=button('Save',commit,True); head.pack_end(save_button); d.set_default_widget(save_button)
        keys=Gtk.EventControllerKey()
        def key_pressed(_,key,*args):
            if key==Gdk.KEY_Escape: d.close(); return True
            return False
        keys.connect('key-pressed',key_pressed); d.add_controller(keys)
        d.connect('close-request',lambda *_:self.dialog_closed(d)); d.present()
    def dialog_closed(self,d):
        if d in self.dialogs: self.dialogs.remove(d)
        self.dialog_count=len(self.dialogs); return False
    def clear(self,box):
        focus=self.win.get_focus()
        if focus and (focus==box or focus.is_ancestor(box)): self.win.set_focus(None)
        while box.get_first_child(): box.remove(box.get_first_child())
    def heading(self,box,title,subtitle=''):
        box.append(label(title,'title-1'))
        if subtitle: box.append(label(subtitle,'dim-label'))
    def row(self,box,main,detail,actions=()):
        row=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8); row.add_css_class('card'); row.append(label(main,'heading')); row.append(label(detail,'dim-label'))
        if actions:
            controls=action_bar()
            for text,cb in actions: controls.append(button(text,cb,text in ('Approve','Assign','Open report')))
            row.append(controls)
        box.append(row); return row
    def empty(self,box,title,body,action=None):
        status=Adw.StatusPage(title=title,description=body,icon_name='alarm-symbolic'); status.set_vexpand(False)
        if action: status.set_child(button(action[0],action[1],True))
        box.append(status)
    def task_choices(self): return [(r['id'],f"{r['client']} / {r['project']} / {r['task']}") for r in self.store.tasks()]
    def client_choices(self): return [(r['id'],r['name']) for r in self.store.rows('SELECT * FROM clients WHERE archived=0 ORDER BY name')]
    def project_choices(self): return [(r['id'],f"{r['client']} / {r['name']}") for r in self.store.rows('SELECT p.*,c.name client FROM projects p JOIN clients c ON c.id=p.client_id WHERE p.archived=0 AND c.archived=0 ORDER BY c.name,p.name')]
    def show_page(self,name):
        self.page=name; self.stack.set_visible_child_name(name)
        self.live_signature=None
        for n,b in self.nav.items():
            if n==name: b.add_css_class('selected')
            else: b.remove_css_class('selected')
        getattr(self,'refresh_'+name.lower())(); self.last_refresh=time.monotonic()
    def tick(self):
        if not self.win: return False
        try:
            now=int(time.time())
            health=desktop.read_health(self.store); status=health['status']; rt=self.store.runtime()
            self.timer_started=rt['started'] if rt['state']=='running' else None
            self.start_timer_button.set_visible(not self.simple_mode() and self.timer_started is None)
            self.update_timer_display(now)
            names={'active':'Tracking automatically','paused':'Tracking paused','setup_required':'Finish setup','stopped':'Tracking stopped','error':'Recording failed','degraded':'Tracking needs attention'}
            self.status.set_text(names.get(status,'Starting…'))
            self.capture_button.set_label('Resume' if self.store.get('capture_enabled','0')!='1' else 'Pause')
            if self.simple_mode():
                self.status.set_text({'active':'Recording','paused':'Paused','setup_required':'Needs setup','stopped':'Stopped','error':'Needs attention','degraded':'Needs attention'}.get(status,'Starting…'))
                self.simple_tick(rt,health,now=now);return True
            if self.page=='Today':
                ai=self.store.db.execute('SELECT MAX(updated) FROM ai_jobs').fetchone()
                focus=self.store.db.execute('SELECT task_id,end FROM ai_focus WHERE start<=? AND end>? ORDER BY start DESC LIMIT 1',(int(time.time()),int(time.time()))).fetchone()
                signature=(rt['state'],rt['capture_status'],rt['app'],datetime.now().date(),tuple(ai),tuple(focus) if focus else None,self.store.get('ai_pause_reason'))
                if signature!=self.rendered_signature and not self.dialog_count:
                    self.refresh_today(); self.rendered_signature=signature
            elif self.page=='Calendar' and not self.dialog_count and not self.selected_blocks and time.monotonic()-self.last_refresh>15:
                self.refresh_calendar_details(); self.last_refresh=time.monotonic()
            now=int(time.time())
            signature=(self.page,rt['collector_seen'],rt['state'],rt['started'],now if rt['state']=='running' else None)
            if signature!=self.live_signature:
                self.update_live_counts(rt,now); self.live_signature=signature
        except (sqlite3.Error,OSError) as exc: self.status.set_text('Recording needs attention')
        return True
    def update_timer_display(self,now=None):
        if not self.win: return False
        self.timer_button.set_visible(self.timer_started is not None)
        if self.timer_started is not None:
            text=fmt_timer((time.time() if now is None else now)-self.timer_started)
            if self.timer_button.get_label()!=text: self.timer_button.set_label(text)
            if self.timer_label is not None and self.timer_label.get_text()!=text: self.timer_label.set_text(text)
        return True
    def update_live_counts(self,rt,now):
        if self.page in ('Today','Calendar'):
            day=datetime.fromtimestamp(now).date() if self.page=='Today' else self.day
            start,end=day_bounds(day)
            summary=self.store.day_summary(start,end,include_running=True,now=now)
            if self.page=='Today':
                for key,w in self.today_metrics.items(): set_changed_text(w,fmt_duration(summary[key]))
                durations=dict(summary['apps'])
                for name,(detail,progress) in self.today_apps.items():
                    duration=durations.get(name,0); set_changed_text(detail,fmt_duration(duration))
                    progress.set_fraction(duration/max(1,summary['active']))
            else:
                current=self.current_live_id(start,end)
                if current!=self.calendar_seen_live and not self.selected_blocks and not self.dialog_count:
                    self.refresh_calendar_details(); self.last_refresh=time.monotonic()
                set_changed_text(self.calendar_summary,self.calendar_summary_text(summary))
                self.calendar_timeline.records=self.store.activity_for(start,end); self.calendar_timeline.queue_draw()
                self.update_live_rows(self.calendar_live)
        elif self.page=='History' and self.history_kind=='usage':
            start,end=self.history_bounds(); current=self.current_live_id(start,end)
            if current!=self.history_seen_live and not self.dialog_count: self.history_update()
            self.update_live_rows(self.history_live)
        elif self.page=='Projects':
            task_seconds={r['task_id']:r['seconds'] for r in self.store.rows('SELECT task_id,SUM(end-start) seconds FROM entries WHERE deleted=0 GROUP BY task_id')}
            if rt['state']=='running' and rt['started'] is not None and now>rt['started']:
                start=rt['started']
                overlaps=self.store.entries(start,now)
                live=now-start-sum(max(0,min(now,r['end'])-max(start,r['start'])) for r in overlaps)
                task_seconds[rt['task_id']]=task_seconds.get(rt['task_id'],0)+live
            project_seconds={}
            for task_id,seconds in task_seconds.items():
                project_id=self.task_projects.get(task_id)
                if project_id is not None: project_seconds[project_id]=project_seconds.get(project_id,0)+seconds
            for project_id,(detail,budget,progress) in self.project_live.items():
                seconds=project_seconds.get(project_id,0); set_changed_text(detail,self.project_detail(seconds,budget))
                if progress: progress.set_fraction(min(1,seconds/budget))
            for task_id,(detail,budget) in self.task_live.items(): set_changed_text(detail,self.task_detail(task_seconds.get(task_id,0),budget))
    def update_live_rows(self,rows):
        for aid,(detail,format_detail) in rows.items():
            record=self.store.db.execute('SELECT * FROM activity WHERE id=?',(aid,)).fetchone()
            if record: set_changed_text(detail,format_detail(record))
    def current_live_id(self,start,end):
        row=self.store.db.execute('SELECT id FROM activity WHERE closed=0 AND start<? AND end>? ORDER BY id DESC LIMIT 1',(end,start)).fetchone()
        return row['id'] if row else None
    def calendar_summary_text(self,summary):
        return f"Active {fmt_duration(summary['active'])} · Assigned {fmt_duration(summary['assigned'])} · Unassigned {fmt_duration(summary['unassigned'])} · Away {fmt_duration(summary['away'])}"
    def project_detail(self,seconds,budget):
        detail='Spent '+fmt_duration(seconds)
        if budget is not None:
            delta=budget-seconds; detail+=' · Budget '+fmt_duration(budget)+' · '+(fmt_duration(delta)+' remaining' if delta>=0 else fmt_duration(-delta)+' over budget')
        return detail
    def task_detail(self,seconds,budget):
        detail=fmt_duration(seconds)+' recorded'
        if budget is not None: detail+=' · '+fmt_duration(budget)+' budget'
        return detail
    def toggle_capture(self,*_):
        paused=self.store.get('capture_enabled','0')!='1'
        desktop.set_paused(self.store,not paused); desktop.start_collector(); self.tick(); self.show_page(self.page)
        self.toast('Automatic tracking resumed' if paused else 'Automatic tracking paused')
    def pause_for(self,minutes):
        desktop.set_paused(self.store,True,minutes); self.show_page(self.page); self.toast(f'Paused for {minutes} minutes')
    def quick_setup(self,*_,after=None):
        def build(b):
            b.append(label('Create a client, project and first task together. For an existing client with different billing settings, use Add project in Projects.','dim-label'))
            return (field(b,'Client',''),field(b,'Project',''),field(b,'First task','General'),field(b,'Hourly rate (optional)','','e.g. 60.00'),dropdown(b,'Currency',[(x,x) for x in ('GBP','EUR','USD')]),field(b,'Project budget in hours (optional)'))
        def save(f):
            c,p,t,r,cur,b=f; self.store.quick_project(c.get_text(),p.get_text(),t.get_text(),parse_money(r.get_text()),selected(cur),parse_hours(b.get_text())); self.toast('Project ready')
            if after: GLib.idle_add(lambda:(after(),False)[1])
        self.dialog('New project',build,save)

    def refresh_today(self):
        if self.simple_mode():return self.simple_today()
        self.timer_label=None
        b=self.body_today; self.clear(b); now=int(time.time()); start,end=day_bounds(datetime.now().date()); rt=self.store.runtime(); summary=self.store.day_summary(start,end,include_running=True,now=now)
        self.today_metrics={}; self.today_apps={}
        self.timer_started=rt['started'] if rt['state']=='running' else None; self.update_timer_display()
        self.heading(b,'Today',datetime.now().strftime('%A, %d %B')+' · Review your day and record your work')
        if self.task_choices():self.automation_summary(b)
        if not self.task_choices():
            self.row(b,'Start with a project','Create a client, project and task. Then add time manually or assign captured activity. Review drafts in History before creating a client report.',[('Create your first project',self.quick_setup)])
            guide=Gtk.Expander(label='How to get started'); details=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
            details.append(label('1. Create a project. You can leave the rate and budget empty.'))
            details.append(label('2. Start a task timer or add time manually. If automatic tracking is available, review captured activity and assign it to a task.'))
            details.append(label('3. Review drafts before approving them. Client reports include approved billable work only.'))
            details.append(label('Your data stays on this computer. Window titles are off by default; Settings explains tracking and privacy.','dim-label'))
            guide.set_child(details); b.append(guide)
        health=desktop.read_health(self.store); state=health['status']
        if state=='setup_required':
            description='Desktop capture needs setup. Check docs/INSTALL.md for your desktop, install its dependencies and helper, then sign out and back in.' if desktop.supported_desktop() else 'Automatic capture is unavailable. Check desktop dependencies in docs/INSTALL.md. Manual timers and timesheets remain available.'
            self.row(b,'Finish automatic tracking setup',description,[('Check setup',lambda _:self.show_page('Settings'))])
        elif state=='paused':
            self.row(b,'Automatic tracking is paused','Resume when you are ready. Titles are stored only if you enable them in Settings.',[('Resume tracking',self.toggle_capture)])
        elif state in ('stopped','error','degraded'):
            self.row(b,'Tracking needs attention',health.get('error') or 'Restart the tracker or check setup.',[('Restart tracking',lambda _:self.run_action(lambda:desktop.start_collector(),lambda _:self.toast('Tracker started'))),('Settings',lambda _:self.show_page('Settings'))])
        else:
            activity=rt['activity_state']
            title=('Now using '+rt['app']) if activity=='active' and rt['app'] else {
                'away':'Away from keyboard','locked':'Screen locked','excluded':'Excluded application',
                'unknown':'Waiting for reliable activity information','paused':'Tracking paused'}.get(activity,'Tracking is ready')
            self.row(b,title,'Away and locked time are kept separate from active work.', [('Pause 15 min',lambda _:self.pause_for(15))])
        metrics=Gtk.Box(spacing=12,homogeneous=True)
        for key,title in [('active','Active desktop use'),('assigned','Assigned to tasks'),('unassigned','Needs assignment')]:
            card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4); card.add_css_class('card'); value=label(fmt_duration(summary[key]),'metric'); card.append(value); self.today_metrics[key]=value; card.append(label(title,'dim-label')); metrics.append(card)
        b.append(metrics)
        b.append(label('Active is desktop use; assigned includes task time, including manual entries. Unassigned is captured activity still to review. Neither total is automatically billable.', 'dim-label'))
        bar=action_bar(); b.append(bar)
        bar.append(button('Review today',lambda _:self.review_dialog(datetime.now().date()),True)); bar.append(button('Open timeline',lambda _:self.review_today())); bar.append(button('Add time',lambda _:self.entry_dialog())); bar.append(button('New project',self.quick_setup))
        if summary['assigned']:
            work={}
            for entry in self.store.entries(start,end):
                name=f"{entry['client']} / {entry['project']} / {entry['task']}"
                work[name]=work.get(name,0)+min(end,entry['end'])-max(start,entry['start'])
            lines=[f'{name} · {fmt_duration(seconds)}' for name,seconds in sorted(work.items(),key=lambda x:x[1],reverse=True)[:6]]
            if len(work)>6:lines.append(f'{len(work)-6} more tasks · Open day entries for the full list')
            if work:self.row(b,'Work recorded today','\n'.join(lines),[('Review day entries',lambda _:self.review_drafts(datetime.now().date(),status='all'))])
        if rt['state']=='running':
            task=next((r for r in self.store.tasks() if r['id']==rt['task_id']),None)
            timer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8); timer.add_css_class('card'); b.append(timer)
            timer.append(label('Running timer · '+(task['task'] if task else 'Task'),'heading'))
            self.timer_started=rt['started']; self.timer_label=label(fmt_timer(time.time()-rt['started']),'metric')
            self.timer_label.add_css_class('timer-digits'); timer.append(self.timer_label)
            timer.append(label('Hours : minutes : seconds · Updates every second','dim-label'))
            timer.append(button('Stop and save time',lambda _:self.run_action(self.store.stop_timer,lambda _:self.toast('Timer stopped; time saved as draft'))))
        elif self.task_choices():
            with_task=Gtk.Expander(label='Optional: focus on a task with a timer'); with_task.set_expanded(getattr(self,'focus_expanded',False)); with_task.connect('notify::expanded',lambda w,*_:setattr(self,'focus_expanded',w.get_expanded()))
            inner=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8); choices=dropdown(inner,'Task',self.task_choices()); select_id(choices,getattr(self,'focus_task',None)); choices.connect('notify::selected',lambda *_:setattr(self,'focus_task',selected(choices)))
            inner.append(button('Start task timer',lambda _:self.run_action(lambda:self.start_timer(selected(choices))))); with_task.set_child(inner); b.append(with_task)
        week_start=datetime.now().date()-timedelta(days=datetime.now().date().weekday())
        weekly=self.store.period_summary(day_bounds(week_start)[0],end)
        self.row(b,'This week (saved entries)',f"Recorded {fmt_duration(weekly['recorded'])} · Approved {fmt_duration(weekly['approved'])} · Billable {fmt_duration(weekly['billable'])} · Capture gaps {fmt_duration(weekly['gaps'])}",
                 [('Review week',lambda _:self.review_week())])
        if summary['drafts']:
            self.row(b,f"{summary['drafts']} draft entries today",'Review the task, description and rate, then approve time for client reports.',[('Review drafts',lambda _:self.review_drafts())])
        for notice in self.store.rows('SELECT id,message FROM notices WHERE read=0 ORDER BY id DESC LIMIT 3'):
            self.row(b,'Tracking notice',notice['message'],[('Dismiss',lambda _,i=notice['id']:self.run_action(lambda:self.dismiss_notice(i)))])
        b.append(label('Apps today','title-3'))
        if not summary['apps']: b.append(label('Usage appears here as soon as automatic tracking is available.','dim-label'))
        for app,duration in summary['apps'][:8]:
            card=self.row(b,app,fmt_duration(duration),[('Assign usage',lambda _,a=app:self.assign_app(a,start,end))])
            progress=Gtk.ProgressBar(fraction=duration/max(1,summary['active'])); card.append(progress)
            self.today_apps[app]=(card.get_first_child().get_next_sibling(),progress)
    def dismiss_notice(self,notice_id):
        with self.store.db: self.store.db.execute('UPDATE notices SET read=1 WHERE id=?',(notice_id,))
    def review_today(self): self.day=datetime.now().date(); self.activity_filter='unassigned'; self.show_page('Calendar')
    def review_week(self): self.history_kind='tasks'; self.history_period='week'; self.history_status='all'; self.history_billable='all'; self.history_search=''; self.show_page('History')
    def timer_dialog(self):
        if not self.task_choices(): self.quick_setup(after=self.timer_dialog); return
        def build(b):
            b.append(label('Choose a task. The running timer stays visible in the header.'))
            task=dropdown(b,'Task',self.task_choices()); select_id(task,getattr(self,'focus_task',None)); return task
        def save(task):
            self.focus_task=selected(task); self.start_timer(self.focus_task); self.toast('Timer started')
        self.dialog('Start timer',build,save)

    def start_timer(self,task):
        rt=self.store.runtime()
        if not rt['collector_seen'] or time.time()-rt['collector_seen']>12: desktop.start_collector(); raise ValueError('The tracker is starting. Try again in a moment.')
        self.store.start_timer(task)
    def assign_app(self,app,start,end):
        blocks=[r for r in self.store.activity_for(start,end,True) if r['app']==app and r['closed']]
        self.assign_dialog(blocks,app)
    def entry_row(self,box,row,selectable=False):
        eid=row['id']; title=f"{row['client']} / {row['project']} / {row['task']}"
        start=datetime.fromtimestamp(row['start']); end=datetime.fromtimestamp(row['end'])
        end_text=end.strftime('%d %b %H:%M' if start.date()!=end.date() else '%H:%M')
        detail=f"{start:%d %b %H:%M} – {end_text} · {fmt_duration(row['end']-row['start'])} · {row['status'].capitalize()} · "+('Billable' if row['billable'] else 'Non-billable')
        if row['billable']:
            rate=row['suggested_rate'] if row['status']=='draft' else row['rate']
            detail+=' · '+('Set an hourly rate before approval' if rate is None else f"{row['currency'] or row['client_currency']} {money(rate)}/hour")
        if row['description']: detail+='\n'+row['description']
        if row['origin']=='jev':detail+='\nOriginally organised by Jev.'
        actions=[]
        if row['status']!='billed':
            actions=[('Edit',lambda _,i=eid:self.entry_dialog(i)),('Split',lambda _,r=row:self.split_dialog(r)),('Delete',lambda _,i=eid:self.confirm('Delete this time entry?','This can be undone until the entry changes again.',lambda:self.store.delete_entry(i)))]
            if row['status']=='draft': actions.insert(0,('Approve',lambda _,i=eid:self.run_action(lambda:self.store.approve(i),lambda _:self.toast('Time approved'))))
            if row['origin']=='jev':actions.append(('Why Jev chose this task',lambda _,i=eid:self.entry_decision(i)))
        else: actions=[('View billing details',lambda _,r=row:self.info('Billed time',f"Invoice: {r['invoice']}\nRate: {r['currency']} {money(r['rate'] or 0)} per hour\nThis entry is locked to protect your billing history."))]
        card=self.row(box,title,detail,actions)
        if selectable and row['status']!='billed':
            cb=Gtk.CheckButton(label='Select entry'); cb.set_active(eid in self.selected_entries)
            cb.update_property([Gtk.AccessibleProperty.LABEL],[f'Select {title}, {start:%d %b %H:%M}'])
            def changed(w,i=eid):
                if w.get_active(): self.selected_entries.add(i)
                else: self.selected_entries.discard(i)
                self.update_history_selection()
            cb.connect('toggled',changed); card.prepend(cb)
            self.history_checks.append(cb)
    def entry_dialog(self,eid=None,start=None,end=None,task_id=None):
        entry=self.store.db.execute('SELECT * FROM entries WHERE deleted=0 AND id=?',(eid,)).fetchone() if eid else None
        choices=self.task_choices()
        if entry and not any(i==entry['task_id'] for i,_ in choices):
            old=self.store.entries(entry['start'],entry['end'])
            old=next((x for x in old if x['id']==eid),None)
            if old: choices.append((entry['task_id'],f"{old['client']} / {old['project']} / {old['task']} (archived)"))
        if not choices: self.quick_setup(after=lambda:self.entry_dialog(eid,start,end,task_id)); return
        if entry and entry['status']=='billed': self.error('Billed time is locked.'); return
        now=int(time.time()); a=entry['start'] if entry else (start if start is not None else now-1800); z=entry['end'] if entry else (end if end is not None else now)
        def build(b):
            d=dropdown(b,'Task',choices); select_id(d,entry['task_id'] if entry else task_id)
            s=field(b,'Start',datetime.fromtimestamp(a).strftime('%Y-%m-%d %H:%M:%S'),'YYYY-MM-DD HH:MM')
            e=field(b,'End',datetime.fromtimestamp(z).strftime('%Y-%m-%d %H:%M:%S'),'YYYY-MM-DD HH:MM')
            if not entry and start is None and end is None:
                shortcuts=action_bar(); b.append(shortcuts)
                def recent(minutes):
                    finish=datetime.now().replace(microsecond=0); begin=finish-timedelta(minutes=minutes)
                    s.set_text(begin.strftime('%Y-%m-%d %H:%M:%S')); e.set_text(finish.strftime('%Y-%m-%d %H:%M:%S'))
                for minutes in (15,30,60): shortcuts.append(button(f'Last {minutes} minutes',lambda _,m=minutes:recent(m)))
            desc=field(b,'Client-facing description',entry['description'] if entry else '')
            bill=Gtk.CheckButton(label='Billable'); bill.set_active(bool(entry['billable']) if entry else True); b.append(bill)
            b.append(label('Overlapping time is prevented. Editing approved time returns it to draft.','dim-label'))
            return d,s,e,desc,bill
        def save(f):
            d,s,e,desc,bill=f; args=(selected(d),parse_local(s.get_text()),parse_local(e.get_text()),desc.get_text(),bill.get_active())
            if entry: self.store.update_entry(eid,*args,expected_revision=entry['revision'])
            else: self.store.add_entry(*args)
            self.toast('Time saved')
        self.dialog('Edit time' if entry else 'Add time',build,save)
    def split_dialog(self,row):
        def build(b): return field(b,'Split at',datetime.fromtimestamp((row['start']+row['end'])//2).strftime('%Y-%m-%d %H:%M:%S'))
        self.dialog('Split time',build,lambda w:self.store.split_entry(row['id'],parse_local(w.get_text())))
    def assign_dialog(self,blocks,app=None,suggested_task=None,review_result=False,after_save=None,review_decision=None):
        if not blocks: self.toast('No completed, unassigned activity yet. Live usage becomes assignable when you switch apps.'); return
        if not self.task_choices(): self.quick_setup(after=lambda:self.assign_dialog(blocks,app,suggested_task,review_result,after_save,review_decision)); return
        seconds=sum(b['end']-b['start'] for b in blocks)
        ai_suggestion=[review_decision.get('task') if review_decision else None]; ai_probability=[review_decision.get('probability') if review_decision else None]
        def build(b):
            b.append(label(f'{fmt_duration(seconds)} of activity. Time already assigned to a task will be skipped.'))
            form=self.dialogs[-1]; closed=threading.Event(); revision=[0]
            form.connect('close-request',lambda *_:(closed.set(),False)[1])
            task=dropdown(b,'Assign to',[(None,'Choose a task…')]+self.task_choices())
            task.connect('notify::selected',lambda *_:revision.__setitem__(0,revision[0]+1))
            budget=label('','dim-label'); b.append(budget)
            def update_budget(*_):
                from .review import budget_warning
                row=self.store.db.execute('''SELECT p.budget,COALESCE((SELECT SUM(e.end-e.start) FROM entries e JOIN tasks q ON q.id=e.task_id WHERE q.project_id=p.id AND e.deleted=0),0) spent FROM tasks t JOIN projects p ON p.id=t.project_id WHERE t.id=?''',(selected(task),)).fetchone()
                warning=budget_warning(row['spent'],row['budget']) if row else None
                budget.set_text((warning+' based on saved entries. Check the project budget before assigning.') if warning else '')
            task.connect('notify::selected',update_budget); update_budget()
            if len(blocks)==1:
                suggestion=self.store.matching_task(blocks[0]['app'],blocks[0]['title'])
                if suggestion: select_id(task,suggestion)
            apps={str(r['app']) for r in blocks if r['state']=='active' and r['app']}
            from .review import load_preferences
            preferences=load_preferences(self.store.get('jev_preferences','{}'),[i for i,_ in self.task_choices()])
            has_rule=any(rule['enabled'] and not (rule['task_archived'] or rule['project_archived'] or rule['client_archived']) and rule['app'].casefold()==r['app'].casefold() and rule['title'].casefold() in r['title'].casefold() for r in blocks for rule in self.rule_rows())
            if len(apps)==1 and not has_rule:
                remembered=preferences.get(next(iter(apps)).casefold())
                if remembered:
                    select_id(task,remembered); b.append(label('Task preselected from your saved local choice. Check it before saving.','dim-label'))
            if review_result:
                select_id(task,suggested_task if suggested_task in [i for i,_ in self.task_choices()] else None)
                b.append(label('Check the review result and choose a task before saving.','dim-label'))
            elif suggested_task in [i for i,_ in self.task_choices()]:
                select_id(task,suggested_task); b.append(label('Preselected from your review queue. Check it before saving.','dim-label'))
            status=label('Optional: get a TypeSafe suggestion using your own key. Nothing is sent until you confirm.','dim-label'); b.append(status)
            more=Gtk.Expander(label='Optional context'); context_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6); more.set_child(context_box); b.append(more)
            context=field(context_box,'Context to send (remove names and sensitive details)','','Optional; leave empty to send none')
            context.connect('changed',lambda *_:revision.__setitem__(0,revision[0]+1))
            context_box.append(label('Only what you type here is sent. Window titles are never added automatically.','dim-label'))
            alternatives=action_bar(); b.append(alternatives)
            if review_decision:
                from .decision_policy import ambiguous
                if ambiguous(review_decision):
                    select_id(task,None);status.set_text('Jev needs your choice. These are alternatives, not an automatic assignment.')
                    names=dict(self.task_choices())
                    for option,_ in review_decision.get('alternatives',[])[:2]:
                        if option in names:alternatives.append(button(names[option],lambda _,i=option:select_id(task,i)))
                    alternatives.append(button('Neither',lambda _:select_id(task,None)))
            pending=[None]
            def cancel_suggestion(_):
                if pending[0] is not None: pending[0].set()
                status.set_text('Cancelling. The current request may still finish.')
                cancel_request.set_sensitive(False)
            cancel_request=button('Cancel suggestion',cancel_suggestion); cancel_request.set_visible(False); b.append(cancel_request)
            def ask_jev(_):
                from . import jev
                from .review import load_categories,add_categories
                raw_choices=self.task_choices(); categories=load_categories(self.store.get('jev_categories','{}'),[i for i,_ in raw_choices])
                candidates=add_categories(raw_choices,categories); apps=sorted({str(r['app']) for r in blocks if r['state']=='active' and r['app']})
                if not apps: self.error('Select completed application activity to request a suggestion.'); return
                if len(candidates)>254: self.error('There are too many active tasks for one suggestion. Archive unused tasks first.'); return
                if len(apps)>5: self.error('Select activity from no more than five applications.'); return
                current=selected(task); current_revision=revision[0]; extra=context.get_text().strip()
                if len(extra)>1000: self.error('Optional context must be 1,000 characters or fewer.'); return
                try: payload=jev.prepare_request(apps,candidates,context=extra)
                except jev.JevError as exc: self.error(str(exc)); return
                apps=payload['state']['applications']
                preview='Applications: '+', '.join(apps)+'\n\nActive client / project / task options:\n'+'\n'.join(name for _,name in candidates)
                preview+='\n\nOptional context: '+(extra if extra else '(none)')
                warning='\n\nOnly category labels shown here are included. This information goes to api.typesafe.ai and may use your paid API credits. Window titles, entry descriptions and times are not added automatically. Jev may be wrong.'
                ask.set_sensitive(False)
                def response(approved):
                    if not approved:
                        if not closed.is_set(): ask.set_sensitive(True)
                        return
                    if closed.is_set(): return
                    cancelled=threading.Event(); pending[0]=cancelled
                    cancel_request.set_visible(True); cancel_request.set_sensitive(True)
                    status.set_text('Asking TypeSafe…'); ask.set_sensitive(False); self.clear(alternatives); ai_suggestion[0]=None; ai_probability[0]=None
                    def work():
                        try:
                            key=jev.get_key()
                            if closed.is_set(): return
                            answer=None if cancelled.is_set() else jev.suggest(apps,candidates,key,context=extra,detailed=True)
                            error=None
                        except jev.JevError as exc: answer=None; error=str(exc)
                        except Exception: answer=None; error='The suggestion failed. Check your connection and try again.'
                        def finish():
                            if closed.is_set() or self.win is None or task.get_root() is None: return False
                            ask.set_sensitive(True); cancel_request.set_visible(False); pending[0]=None
                            if cancelled.is_set(): status.set_text('Suggestion cancelled. Your task selection was kept.')
                            elif error: status.set_text(error)
                            elif revision[0]!=current_revision or selected(task)!=current: status.set_text('Suggestion arrived after you changed the form; your choice was kept.')
                            elif answer['task'] is None:
                                select_id(task,None)
                                note=' This may be personal; check it on the Calendar.' if answer['personal'] is not None and answer['personal']>=0.8 else ''
                                status.set_text('No match was selected. Choose a task yourself.'+note)
                            elif answer['task'] not in [i for i,_ in self.task_choices()]: status.set_text('The suggested task is no longer available. Choose another task.')
                            else:
                                ai_suggestion[0]=answer['task']; ai_probability[0]=answer['probability']; options=answer['alternatives']; personal=answer['personal']
                                note=' This may be personal; check before assigning.' if personal is not None and personal>=0.8 else ''
                                if len(options)>=2 and options[0][0]==answer['task'] and options[0][1]-options[1][1]<0.15:
                                    select_id(task,None)
                                    status.set_text('Two tasks look similar. Choose one, or neither.'+note)
                                    names=dict(candidates)
                                    for option,_ in options[:2]:
                                        alternatives.append(button(names[option],lambda _,i=option:select_id(task,i)))
                                    alternatives.append(button('Neither',lambda _:select_id(task,None)))
                                else:
                                    select_id(task,answer['task']); probability='' if answer['probability'] is None else f" (model probability {answer['probability']:.0%})"
                                    status.set_text('Suggested task selected'+probability+'. Check it before saving.'+note)
                            if answer and not error and not cancelled.is_set() and isinstance(answer.get('usage'),dict):
                                status.set_text(status.get_text()+f" Reported input: {answer['usage']['input_tokens']:,} tokens.")
                            return False
                        GLib.idle_add(finish)
                    threading.Thread(target=work,daemon=True).start()
                self.ai_consent('Send this data to TypeSafe?',preview+warning,response)
            ask=button('Suggest a task with TypeSafe',ask_jev); b.append(ask)
            desc=field(b,'Client-facing description (optional)')
            remember=Gtk.CheckButton(label='Create a rule for future use of this app')
            same=len({r['app'] for r in blocks})==1 and all(r['state']=='active' for r in blocks)
            remember.set_sensitive(same); b.append(remember)
            local_choice=Gtk.CheckButton(label='Remember this choice locally (and count whether AI was changed)')
            local_choice.set_sensitive(same); b.append(local_choice)
            b.append(label('A rule automatically assigns future completed usage of this app to this task as draft time. Use it only when the app belongs to one task. Local choices only preselect a task for your next review. Neither option sends data.','dim-label'))
            return task,desc,remember,local_choice
        def save(f):
            task,desc,remember,local_choice=f; chosen=selected(task)
            if chosen not in dict(self.task_choices()): raise ValueError('Choose an active task before assigning time.')
            count=self.store.assign_remaining(blocks,chosen,desc.get_text(),remember.get_active())
            if local_choice.get_active():
                from .review import load_preferences,feedback
                try:
                    preferences=load_preferences(self.store.get('jev_preferences','{}'),[i for i,_ in self.task_choices()])
                    preferences[next(iter({str(r['app']) for r in blocks if r['state']=='active' and r['app']})).casefold()]=chosen
                    self.store.set('jev_preferences',json.dumps(preferences))
                    if ai_suggestion[0] is not None:
                        self.store.set('jev_feedback',json.dumps(feedback(self.store.get('jev_feedback','{}'),ai_suggestion[0],chosen,ai_probability[0])))
                except (sqlite3.Error,ValueError,StopIteration):
                    self.toast('Time saved, but the local choice could not be remembered.')
                    if after_save: GLib.idle_add(lambda:(after_save(),False)[1])
                    return
            self.toast(f'{count} activity periods assigned')
            if after_save:
                GLib.idle_add(lambda:(after_save(),False)[1])
        self.dialog('Assign activity',build,save)

    def review_dialog(self,day,previous_results=()):
        """Show local suggestions; the user chooses every action."""
        from . import review
        start,end=day_bounds(day)
        blocks=self.store.activity_for(start,end,True)
        activity=self.store.activity_for(start,end)
        facts=review.readiness(self.store.entries(start,end),activity)
        counts=self.store.rows("""SELECT a.app,e.task_id,COUNT(DISTINCT e.activity_id) count FROM entries e
            JOIN activity a ON a.id=e.activity_id WHERE e.deleted=0 AND e.origin='assigned'
            AND a.state='active' GROUP BY a.app,e.task_id""")
        preferences={app.casefold():task for app,task,_ in review.rule_hints(counts)}
        assigned_barriers=[dict(start=max(start,e['start']),end=min(end,e['end']),state='assigned',closed=1) for e in self.store.entries(start,end)]
        groups=review.rank_sessions(review.sessions(blocks,barriers=activity+assigned_barriers),preferences)
        current={(r['id'],r['start'],r['end']) for r in blocks}
        saved_results=[item for item in previous_results if (item[0]['id'],item[0]['start'],item[0]['end']) in current]
        window=Adw.Window(title='Review suggestions',transient_for=self.dialogs[-1] if self.dialogs else self.win,modal=True,default_width=750,default_height=700)
        self.dialogs.append(window); self.dialog_count=len(self.dialogs)
        window.connect('close-request',lambda *_:self.dialog_closed(window))
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);window.set_content(outer)
        header=Adw.HeaderBar();outer.append(header);header.pack_end(button('Close',lambda _:window.close()))
        scroll=Gtk.ScrolledWindow(vexpand=True);outer.append(scroll)
        body=margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12),20);scroll.set_child(body)
        self.heading(body,'Review '+day.strftime('%d %B %Y'),'Local suggestions. Nothing changes until you choose an action.')
        body.append(label(f"{facts['drafts']} drafts · {facts['missing_description']} without descriptions · {facts['missing_rate']} without a rate · {fmt_duration(facts['gap_seconds'])} of capture gaps",'dim-label'))
        if facts['gap_seconds']: body.append(label('Capture gaps are unknown time. Add genuine work manually if needed; no time is inferred.','dim-label'))
        self.row(body,'Check draft time','Review this day’s entries and missing details before approving them.',[('Open drafts',lambda _:(window.close(),self.review_drafts(day)))])
        selected_blocks=[]
        toolbar=action_bar();body.append(toolbar)
        def reopen_review():
            window.close(); self.review_dialog(day,saved_results)
        assign=button('Assign selected',lambda _:self.assign_dialog(list(selected_blocks),after_save=reopen_review),True);assign.set_sensitive(False);toolbar.append(assign)
        ask_quick=button('Ask Jev',lambda _:(batch.set_expanded(True),ask_batch(None)));ask_quick.set_sensitive(False);toolbar.append(ask_quick)
        checks=[]
        toolbar.append(button('Select shown',lambda _:[c.set_active(True) for c in checks]))
        toolbar.append(button('Clear selection',lambda _:[c.set_active(False) for c in checks]))
        selection_summary=label('Select activity below, then assign a task or ask Jev for suggestions.','dim-label');body.append(selection_summary)
        def select_block(widget,block):
            if widget.get_active(): selected_blocks.append(block)
            elif block in selected_blocks: selected_blocks.remove(block)
            assign.set_sensitive(bool(selected_blocks));assign.set_label(f'Assign selected ({len(selected_blocks)})' if selected_blocks else 'Assign selected')
            selection_summary.set_text(f"{len(selected_blocks)} selected · {fmt_duration(sum(r['end']-r['start'] for r in selected_blocks))}" if selected_blocks else 'Select activity below, then assign a task or ask Jev for suggestions.')
            ask.set_sensitive(bool(selected_blocks) and job[0] is None)
            ask_quick.set_sensitive(bool(selected_blocks) and job[0] is None)
        batch=Gtk.Expander(label='Optional AI suggestions for selected blocks');body.append(batch)
        panel=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);batch.set_child(panel)
        panel.append(label('Select blocks below. Each result needs your review before any time is saved.','dim-label'))
        limit=dropdown(panel,'Maximum requests',[(1,'1'),(3,'3'),(5,'5'),(10,'10')]);select_id(limit,5)
        batch_status=label('No requests sent.','dim-label');panel.append(batch_status)
        batch_results=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);panel.append(batch_results)
        actions=action_bar();panel.append(actions)
        closed_window=threading.Event(); job=[None]
        def stop_batch(_):
            if job[0] is not None: job[0].set()
            batch_status.set_text('Cancelling after the current request…');cancel.set_sensitive(False)
        cancel=button('Cancel remaining requests',stop_batch);cancel.set_visible(False);actions.append(cancel)
        def close_batch(*_):
            closed_window.set()
            if job[0] is not None: job[0].set()
            return False
        window.connect('close-request',close_batch)
        def display_result(block,result,error):
            from .decision_policy import ambiguous
            rich=result if isinstance(result,dict) else None
            match=(None if ambiguous(rich) else rich['task']) if rich else result[0] if result else None
            active=dict(self.task_choices());name=active.get(match,'Needs your choice')
            detail=error or ('Suggested: '+name+'. Review before assigning.')
            result_actions=[] if error else [('Review' if match in active else 'Choose manually',lambda _,b=block,t=match,r=rich:self.assign_dialog([b],suggested_task=t,review_result=True,after_save=reopen_review,review_decision=r))]
            self.row(batch_results,block['app'],detail,result_actions)
        def ask_batch(_):
            from . import jev
            if job[0] is not None or closed_window.is_set(): return
            from .review import load_categories,add_categories
            chosen=list(selected_blocks); cap=selected(limit); raw=self.task_choices()
            if not chosen: self.error('Select activity blocks first.'); return
            if len(chosen)>cap: self.error(f'Select no more than {cap} blocks, or raise the request limit.'); return
            if len(chosen)>10 or len(raw)>254: self.error('Select at most ten blocks and 254 active tasks.'); return
            cats=load_categories(self.store.get('jev_categories','{}'),[i for i,_ in raw]); candidates=add_categories(raw,cats)
            apps=[]
            try:
                for block in chosen:
                    if not block.get('app') or block.get('state')!='active': raise jev.JevError('Select named application activity only.')
                    payload=jev.prepare_request([block['app']],candidates)
                    apps.append(payload['state']['applications'][0])
            except jev.JevError as exc: self.error(str(exc)); return
            preview='Applications, one request each:\n'+'\n'.join(apps)+'\n\nActive client / project / task options:\n'+'\n'.join(name for _,name in candidates)
            preview+=f'\n\nOnly category labels shown here are sent. Up to {len(chosen)} paid requests to api.typesafe.ai, each capped at 32,000 request bytes. No titles, descriptions or times are sent. Actual charges depend on token usage. Cancelling stops later requests; the current request may finish.'
            ask.set_sensitive(False);ask_quick.set_sensitive(False)
            def approved(allow):
                if closed_window.is_set(): return
                if not allow: ask.set_sensitive(bool(selected_blocks));ask_quick.set_sensitive(bool(selected_blocks)); return
                cancelled=threading.Event();job[0]=cancelled
                cancel.set_visible(True);cancel.set_sensitive(True);self.clear(batch_results);saved_results.clear();batch_status.set_text('Starting…')
                def available():
                    return not closed_window.is_set() and self.win is not None and job[0] is cancelled and batch_status.get_root() is not None
                def worker():
                    failure=None
                    try:
                        if cancelled.is_set(): key=None
                        else: key=jev.get_key()
                    except jev.JevError as exc: key=None;failure=str(exc)
                    except Exception: key=None;failure='Could not access the keyring. Try again after unlocking it.'
                    def on_result(index,result,error):
                        block=chosen[index]
                        def display():
                            if not available() or cancelled.is_set():return False
                            saved_results.append((block,result,error));display_result(block,result,error)
                            batch_status.set_text(f'{index+1} of {len(chosen)} requests finished.')
                            return False
                        GLib.idle_add(display)
                    if key and not cancelled.is_set() and not closed_window.is_set():
                        try: jev.suggest_batch(apps,candidates,key,cancelled.is_set,on_result,detailed=True)
                        except jev.JevError as exc:failure=str(exc)
                        except Exception:failure='The suggestion request failed.'
                    def done():
                        if available():
                            if cancelled.is_set():batch_status.set_text('Cancelled. No later requests were sent.')
                            elif failure:batch_status.set_text(failure)
                            ask.set_sensitive(bool(selected_blocks));ask_quick.set_sensitive(bool(selected_blocks));cancel.set_visible(False);job[0]=None
                        return False
                    GLib.idle_add(done)
                threading.Thread(target=worker,daemon=True).start()
            self.ai_consent('Send selected blocks to TypeSafe?',preview,approved,send_label='Send')
        ask=button('Suggest for selected blocks',ask_batch);ask.set_sensitive(False);actions.append(ask)
        panel.append(button('Set up my TypeSafe key',lambda _:(window.close(),self.show_page('Settings'))))
        if saved_results:
            batch.set_expanded(True);batch_status.set_text('Remaining suggestions from this review. No additional requests sent.')
            for block,result,error in saved_results:display_result(block,result,error)
        body.append(label('Suggested sessions','title-3'))
        body.append(label('Nearby activity is grouped for review. Select or clear individual blocks to split or combine sessions; gaps are never added to time.','dim-label'))
        if not groups: body.append(label('No completed unassigned activity for this day.','dim-label'))
        def show_group(target,group):
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);box.add_css_class('card');target.append(box)
            box.append(label(f"{fmt_time(group['start'])} – {datetime.fromtimestamp(group['end']):%H:%M} · {fmt_duration(group['seconds'])}",'heading'))
            for block in group['blocks']:
                text=f"{block['app']} · {datetime.fromtimestamp(block['start']):%H:%M:%S}–{datetime.fromtimestamp(block['end']):%H:%M:%S} · {fmt_duration(block['end']-block['start'])}"
                row=Gtk.Box(spacing=8); box.append(row)
                cb=Gtk.CheckButton(label=text); cb.set_hexpand(True); cb.connect('toggled',select_block,block);row.append(cb);checks.append(cb)
                original=self.store.db.execute('SELECT start,end FROM activity WHERE id=?',(block['id'],)).fetchone()
                if original and original['start']==block['start'] and original['end']==block['end']:
                    def mark(_,item=block):
                        def apply(): self.store.set_personal([item['id']]);reopen_review();self.toast('Marked personal')
                        self.confirm('Mark this activity personal?', 'It will leave the assignment queue. You can return it to review from Calendar.',apply)
                    row.append(button('Mark personal',mark))
        append_in_batches(body,groups,show_group)
        hints=review.rule_hints(counts)
        conflicts=review.inconsistencies(counts)
        if hints or conflicts: body.append(label('Patterns to check','title-3'))
        choices=dict(self.task_choices())
        for app,task,count in hints:
            if task not in choices or self.store.matching_task(app,'') is not None: continue
            def offer(_,app=app,task=task):
                self.rule_dialog(application=app,task_id=task)
            self.row(body,app+' → '+choices[task],f'Assigned this way {count} times. A rule is optional.',[('Create rule',offer)])
        for app,count in conflicts:
            self.row(body,app+' has been assigned to multiple tasks',f'{count} tasks found in retained activity. This may be expected; check only if useful.')
        window.present()

    def refresh_calendar(self):
        if self.simple_mode():return self.simple_past_days()
        b=self.body_calendar; self.clear(b); self.selected_blocks=[]
        self.heading(b,'Calendar','Your activity and task history, day by day')
        top=Gtk.Box(spacing=20); b.append(top)
        cal=Gtk.Calendar(); cal.set_valign(Gtk.Align.START); cal.select_day(GLib.DateTime.new_local(self.day.year,self.day.month,self.day.day,12,0,0)); top.append(cal)
        guide=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8); guide.set_hexpand(True); top.append(guide)
        guide.append(label('Review your day','title-3')); guide.append(label('Select a date. Assign captured usage to a project, recover genuine work from away time, then approve the timesheet.','dim-label'))
        mode=dropdown(guide,'Show', [('all','All activity'),('unassigned','Unassigned activity'),('entries','Timesheet entries only')]); select_id(mode,self.activity_filter)
        mode.connect('notify::selected',lambda *_:self.set_activity_filter(selected(mode)))
        guide.append(button('Jump to today',lambda _:self.jump_today()))
        def marks(c):
            dt=c.get_date(); first=datetime(dt.get_year(),dt.get_month(),1).date(); length=calendar.monthrange(first.year,first.month)[1]
            c.clear_marks()
            start,end=day_bounds(first)[0],day_bounds(first+timedelta(days=length))[0]
            for row in self.store.entries(start,end):
                for offset in range(length):
                    day=first+timedelta(days=offset); a,z=day_bounds(day)
                    if row['start']<z and row['end']>a: c.mark_day(day.day)
            for row in self.store.activity_for(start,end): c.mark_day(datetime.fromtimestamp(row['start']).day)
        def changed(c):
            dt=c.get_date(); self.day=datetime(dt.get_year(),dt.get_month(),dt.get_day_of_month()).date(); self.selected_blocks=[]; self.refresh_calendar_details()
        cal.connect('day-selected',changed)
        for signal in ('next-month','prev-month','next-year','prev-year'): cal.connect(signal,marks)
        marks(cal)
        self.calendar_detail=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12); b.append(self.calendar_detail); self.refresh_calendar_details()
    def set_activity_filter(self,value): self.activity_filter=value; self.selected_blocks=[]; self.refresh_calendar_details()
    def jump_today(self): self.day=datetime.now().date(); self.show_page('Calendar')
    def refresh_calendar_details(self):
        b=self.calendar_detail; self.clear(b); start,end=day_bounds(self.day); summary=self.store.day_summary(start,end,include_running=True)
        self.calendar_live={}; self.calendar_seen_live=self.current_live_id(start,end); self.heading(b,self.day.strftime('%A, %d %B'),self.calendar_summary_text(summary)); self.calendar_summary=b.get_last_child()
        records=self.store.activity_for(start,end)
        self.calendar_timeline=Timeline(start,end,records); b.append(self.calendar_timeline)
        b.append(label('Timeline: blue active · green personal · grey away or locked · brown excluded · red capture gap. Exact states and times are listed below.', 'dim-label'))
        bar=Gtk.Box(spacing=8); b.append(bar); bar.append(label('Task entries','title-3')); bar.append(button('Add time',lambda _:self.entry_dialog(start=int(datetime.combine(self.day,datetime.min.time()).replace(hour=9).timestamp()),end=int(datetime.combine(self.day,datetime.min.time()).replace(hour=10).timestamp()))))
        entries=self.store.entries(start,end)
        for r in entries: self.entry_row(b,r)
        if not entries: b.append(label('No task entries for this date.','dim-label'))
        if self.activity_filter=='entries': return
        b.append(label('Captured activity','title-3'))
        source=self.store.activity_for(start,end,self.activity_filter=='unassigned')
        groups=group_activity(source)
        if not groups: b.append(label('No activity to show for this date.','dim-label')); return
        self.selected_blocks=[]
        bar=action_bar(); b.append(bar)
        bar.append(button('Review suggestions',lambda _:self.review_dialog(self.day)))
        assign_selected=button('Assign selected',lambda _:self.assign_dialog([x for group in self.selected_blocks for x in group]),True)
        assign_selected.set_sensitive(False); bar.append(assign_selected)
        bar.append(button('Apply saved rules to this day',lambda _:self.run_action(lambda:self.store.apply_rules(start=start,end=end),lambda count:self.toast(f'{count} entries assigned'))))
        def render_group(target,group):
            name=group['app'] if group['state']=='active' else 'Personal · '+group['app'] if group['state']=='personal' else {'away':'Away from keyboard','locked':'Screen locked','unknown':'Capture gap','excluded':'Excluded application','paused':'Paused'}.get(group['state'],group['state'])
            if group['title']: name+=' · '+group['title']
            duration=group['end']-group['start']; live=not group['closed']
            detail=f"{datetime.fromtimestamp(group['start']):%H:%M:%S} – {datetime.fromtimestamp(group['end']):%H:%M:%S} · {fmt_duration(duration)}"+(' · Live' if live else '')
            remaining=sum(z-a for r in group['blocks'] for a,z in self.store.uncovered(r['start'],r['end']))
            actions=[]
            if group['state'] in ('active','away') and not live:
                if remaining:
                    actions=[('Assign' if group['state']=='active' else 'Recover as work',lambda _,g=group:self.assign_dialog(g['blocks']))]
                    if group['state']=='active' and all(sum(z-a for a,z in self.store.uncovered(r['start'],r['end']))==r['end']-r['start'] for r in group['blocks']): actions.append(('Mark personal',lambda _,g=group:self.run_action(lambda:self.store.set_personal([r['id'] for r in g['blocks']]),lambda _:self.toast('Personal usage removed from assignment queue'))))
                    detail+=' · '+fmt_duration(remaining)+' unassigned'
                else: detail+=' · Assigned'
            elif group['state']=='personal': actions=[('Return to review',lambda _,g=group:self.run_action(lambda:self.store.set_personal([r['id'] for r in g['blocks']],False)))]
            card=self.row(target,name or 'Desktop',detail,actions)
            if live:
                first=group['start']; start_text=datetime.fromtimestamp(first).strftime('%H:%M:%S')
                def format_live(r,first=first,start_text=start_text,limit=end):
                    finish=min(r['end'],limit)
                    return f"{start_text} – {datetime.fromtimestamp(finish):%H:%M:%S} · {fmt_duration(finish-first)}"+(' · Live' if not r['closed'] else '')
                self.calendar_live[group['blocks'][-1]['id']]=(card.get_first_child().get_next_sibling(),format_live)
            if group['state'] in ('active','away') and not live and remaining:
                cb=Gtk.CheckButton(label='Select activity')
                def changed(w,g=group['blocks']):
                    if w.get_active(): self.selected_blocks.append(g)
                    elif g in self.selected_blocks: self.selected_blocks.remove(g)
                    assign_selected.set_sensitive(bool(self.selected_blocks)); assign_selected.set_label(f'Assign selected ({len(self.selected_blocks)})' if self.selected_blocks else 'Assign selected')
                cb.connect('toggled',changed); card.prepend(cb)
        append_in_batches(b,groups,render_group)
    def history_bounds(self):
        today=datetime.now().date()
        if self.history_period=='custom': return day_bounds(self.history_from)[0],day_bounds(self.history_to)[1]
        start=today if self.history_period=='today' else today-timedelta(days=today.weekday()) if self.history_period=='week' else today.replace(day=1) if self.history_period=='month' else datetime(1970,1,1).date()
        return day_bounds(start)[0],day_bounds(today)[1]
    def refresh_history(self):
        b=self.body_history; self.clear(b); self.selected_entries=set(); self.heading(b,'Timesheet history','Review, edit and approve your work. Billed time remains protected.')
        bar=Gtk.Box(spacing=10); b.append(bar)
        kind=dropdown(bar,'View',[('tasks','Task entries'),('usage','Desktop usage')]);select_id(kind,self.history_kind)
        period=dropdown(bar,'Period',[('today','Today'),('week','This week'),('month','This month'),('all','All time'),('custom','Custom dates')]); select_id(period,self.history_period)
        status=dropdown(bar,'Status',[('all','All entries'),('draft','Needs review'),('approved','Approved'),('billed','Billed')]); select_id(status,self.history_status)
        billing=dropdown(b,'Billing',[('all','All time entries'),('billable','Billable'),('nonbillable','Non-billable')]); select_id(billing,self.history_billable)
        dates=Gtk.Box(spacing=10); b.append(dates)
        date_from=field(dates,'From date',self.history_from.isoformat(),'YYYY-MM-DD'); date_to=field(dates,'Through date',self.history_to.isoformat(),'YYYY-MM-DD')
        dates.set_visible(self.history_period=='custom')
        search=Gtk.SearchEntry(hexpand=True); search.set_placeholder_text('Search client, task or description'); search.set_text(self.history_search); b.append(search)
        controls=action_bar(); b.append(controls)
        approve=button('Approve selected drafts',lambda _:self.run_action(lambda:self.store.approve_many(sorted(self.selected_entries & self.history_draft_ids)),lambda _:self.toast('Selected drafts approved')),True); controls.append(approve)
        merge=button('Merge selected',lambda _:self.run_action(lambda:self.store.merge_entries(sorted(self.selected_entries)),lambda _:self.toast('Entries merged'))); controls.append(merge)
        controls.append(button('Add time',lambda _:self.entry_dialog()))
        controls.append(button('Undo last edit',lambda _:self.run_action(self.store.undo,lambda a:self.toast(a+' undone'))))
        selection_bar=action_bar(); b.append(selection_bar)
        selection_bar.append(button('Select visible entries',lambda _:[c.set_active(True) for c in self.history_checks]))
        selection_bar.append(button('Clear selection',lambda _:[c.set_active(False) for c in self.history_checks]))
        selection_count=label('No entries selected','dim-label'); b.append(selection_count)
        def selection_changed():
            count=len(self.selected_entries); drafts=len(self.selected_entries & self.history_draft_ids)
            approve.set_sensitive(drafts>0); approve.set_label(f'Approve selected drafts ({drafts})' if drafts else 'Approve selected drafts')
            merge.set_sensitive(count>=2); selection_count.set_text(f'{count} selected · {drafts} draft' if count else 'Select entries below to approve drafts or merge adjacent time for the same task.')
        self.update_history_selection=selection_changed
        results=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10); b.append(results)
        def update(*_):
            self.history_kind=selected(kind);self.history_period=selected(period); self.history_status=selected(status); self.history_billable=selected(billing); dates.set_visible(self.history_period=='custom'); self.history_search=search.get_text(); self.selected_entries=set(); self.history_checks=[]; self.history_draft_ids=set(); self.clear(results)
            self.history_live={}
            usage=self.history_kind=='usage';controls.set_visible(not usage);selection_bar.set_visible(not usage);selection_count.set_visible(not usage);status.set_sensitive(not usage);billing.set_sensitive(not usage)
            search.set_placeholder_text('Search app, window title or activity state' if usage else 'Search client, project, task or description')
            a,z=self.history_bounds(); rows=self.store.entries(a,z,status=None if self.history_status=='all' else self.history_status,search=self.history_search)
            self.history_seen_live=self.current_live_id(a,z)
            if not usage and self.history_billable!='all': rows=[r for r in rows if bool(r['billable'])==(self.history_billable=='billable')]
            if usage:
                source=self.store.activity_for(a,z);needle=self.history_search.casefold()
                groups=group_activity([r for r in source if needle in (r['app']+' '+r['title']+' '+r['state']).casefold()])
                results.append(label(f'{len(groups)} usage groups','heading'))
                def render_usage(target,group):
                    date=datetime.fromtimestamp(group['start']).date()
                    def open_day(_,day=date):self.day=day;self.activity_filter='all';self.show_page('Calendar')
                    def format_usage(r,first=group['start'],limit=z):
                        finish=min(r['end'],limit)
                        return f"{fmt_time(first)} – {datetime.fromtimestamp(finish):%H:%M:%S} · {fmt_duration(finish-first)} · {r['state']}"+(' · Live' if not r['closed'] else '')+('\n'+r['title'] if r['title'] else '')
                    card=self.row(target,group['app'] or group['state'].capitalize(),format_usage(group),[('Review day',open_day)])
                    if not group['closed']: self.history_live[group['blocks'][-1]['id']]=(card.get_first_child().get_next_sibling(),format_usage)
                append_in_batches(results,groups,render_usage)
                if not groups:self.empty(results,'No matching usage','Try another app name or period.')
                return
            self.history_draft_ids={r['id'] for r in rows if r['status']=='draft'}; selection_changed()
            results.append(label(f'{len(rows)} entries · '+fmt_duration(sum(min(z,r['end'])-max(a,r['start']) for r in rows)),'heading'))
            append_in_batches(results,rows,lambda target,r:self.entry_row(target,r,True))
            if not rows: self.empty(results,'No matching time','Try another period or record your first task.')
        def apply_dates(_):
            try:
                a=datetime.strptime(date_from.get_text().strip(),'%Y-%m-%d').date(); z=datetime.strptime(date_to.get_text().strip(),'%Y-%m-%d').date()
                if z<a: raise ValueError('Through date must not be before From date.')
                self.history_from,self.history_to=a,z; update()
            except ValueError as exc: self.error(str(exc) if 'Through date' in str(exc) else 'Enter dates as YYYY-MM-DD.')
        dates.append(button('Apply dates',apply_dates))
        self.history_update=update
        kind.connect('notify::selected',update);period.connect('notify::selected',update); status.connect('notify::selected',update); billing.connect('notify::selected',update); search.connect('search-changed',update); update()
        exp=Gtk.Expander(label='Recent changes'); changes=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8); exp.set_child(changes)
        for r in self.store.rows('SELECT * FROM audit ORDER BY id DESC LIMIT 30'): changes.append(label(f"{fmt_time(r['at'])} · {r['action']}"))
        b.append(exp)
    def refresh_projects(self):
        self.project_live={}; self.task_live={}; self.task_projects={}
        b=self.body_projects; self.clear(b); self.heading(b,'Projects','See where your hours went and how much budget remains.')
        tools=Gtk.Box(spacing=8); b.append(tools); tools.append(button('New project',self.quick_setup,True)); tools.append(button('Add client',lambda _:self.client_dialog())); tools.append(button('Add task',lambda _:self.task_dialog()))
        clients=self.store.rows('SELECT * FROM clients ORDER BY archived,name')
        if not clients: self.empty(b,'Your first project','Create a client, project and task together in one step.',('New project',self.quick_setup)); return
        search=Gtk.SearchEntry(hexpand=True); search.set_placeholder_text('Search clients, projects or tasks'); search.set_text(self.project_search); b.append(search)
        results=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10); b.append(results)
        def render(*_):
            self.project_search=search.get_text(); needle=self.project_search.strip().casefold()
            self.project_live={}; self.task_live={}; self.task_projects={}; self.clear(results); shown=0
            for client in clients:
                projects=[]
                for project in self.store.rows('SELECT * FROM projects WHERE client_id=? ORDER BY archived,name',(client['id'],)):
                    tasks=self.store.rows('SELECT t.*,COALESCE((SELECT SUM(e.end-e.start) FROM entries e WHERE e.deleted=0 AND e.task_id=t.id),0) spent FROM tasks t WHERE project_id=? ORDER BY archived,name',(project['id'],))
                    parent_matches=not needle or needle in client['name'].casefold() or needle in project['name'].casefold()
                    visible_tasks=[t for t in tasks if parent_matches or needle in t['name'].casefold()]
                    if parent_matches or visible_tasks: projects.append((project,tasks,visible_tasks))
                if needle and needle not in client['name'].casefold() and not projects: continue
                shown+=1
                title=client['name']+(' · Archived' if client['archived'] else '')
                rate='No default rate' if client['rate'] is None else client['currency']+' '+money(client['rate'])+'/hour'
                actions=[('Edit client',lambda _,r=client:self.client_dialog(r))]
                if not client['archived']: actions.append(('Add project',lambda _,i=client['id']:self.project_dialog(client_id=i)))
                self.row(results,title,rate,actions)
                for project,tasks,visible_tasks in projects:
                    for task in tasks: self.task_projects[task['id']]=project['id']
                    seconds=sum(t['spent'] for t in tasks)
                    detail=self.project_detail(seconds,project['budget'])
                    card=self.row(results,project['name']+(' · Archived' if project['archived'] else ''),detail,[('Edit project',lambda _,r=project:self.project_dialog(r))])
                    progress=None
                    if project['budget']:
                        progress=Gtk.ProgressBar(fraction=min(1,seconds/project['budget'])); card.append(progress)
                    self.project_live[project['id']]=(card.get_first_child().get_next_sibling(),project['budget'],progress)
                    for task in visible_tasks:
                        detail=self.task_detail(task['spent'],task['budget'])
                        actions=[('Edit task',lambda _,r=task:self.task_dialog(r))]
                        if not task['archived'] and not project['archived']:actions.append(('Describe for Jev',lambda _,i=task['id']:self.task_guidance_dialog(i)))
                        if not task['archived'] and not project['archived']:actions.append(('Use as Jev focus',lambda _,i=task['id']:self.focus_dialog(i)))
                        card=self.row(results,'  '+task['name']+(' · Archived' if task['archived'] else ''),detail,actions)
                        self.task_live[task['id']]=(card.get_first_child().get_next_sibling(),task['budget']); self.task_projects[task['id']]=project['id']
            if not shown: self.empty(results,'No matching projects','Try a client, project or task name.')
        search.connect('search-changed',render); render()
    def client_dialog(self,row=None):
        def build(b):
            n=field(b,'Client name',row['name'] if row else ''); c=field(b,'Currency code (GBP, EUR or USD)',row['currency'] if row else 'GBP'); rate=field(b,'Default hourly rate',f"{row['rate']/100:.2f}" if row and row['rate'] is not None else '', 'e.g. 60.00')
            a=Gtk.CheckButton(label='Archived'); a.set_active(bool(row['archived']) if row else False); b.append(a); return n,c,rate,a
        def save(f):
            n,c,r,a=f; rate=parse_money(r.get_text()); currency=c.get_text().strip().upper(); name=n.get_text().strip()
            if not name or currency not in ('GBP','EUR','USD'): raise ValueError('Enter a name and choose GBP, EUR or USD.')
            if not row: self.store.add_client(name,currency,rate); return
            if currency!=row['currency'] and self.store.db.execute('SELECT 1 FROM entries e JOIN tasks t ON e.task_id=t.id JOIN projects p ON t.project_id=p.id WHERE p.client_id=? AND e.status!=\'draft\' LIMIT 1',(row['id'],)).fetchone(): raise ValueError('Currency cannot be changed for a client with approved or billed entries. Create a separate client instead.')
            with self.store.db:
                self.store.db.execute('UPDATE clients SET name=?,currency=?,rate=?,archived=? WHERE id=?',(name,currency,rate,int(a.get_active()),row['id'])); self.store.audit('client edited',{'id':row['id']})
        self.dialog('Edit client' if row else 'Add client',build,save)
    def project_dialog(self,row=None,client_id=None):
        choices=self.client_choices()
        if row and not any(i==row['client_id'] for i,_ in choices):
            parent=self.store.db.execute('SELECT name FROM clients WHERE id=?',(row['client_id'],)).fetchone(); choices.append((row['client_id'],parent['name']+' (archived)'))
        if not choices: self.error('Create a client first.'); return
        def build(b):
            c=dropdown(b,'Client',choices)
            if row: select_id(c,row['client_id']); c.set_sensitive(False)
            elif client_id: select_id(c,client_id)
            n=field(b,'Project name',row['name'] if row else ''); bud=field(b,'Time budget in hours (optional)',str(row['budget']/3600) if row and row['budget'] is not None else '')
            rate=field(b,'Hourly rate override (optional)',f"{row['rate']/100:.2f}" if row and row['rate'] is not None else '')
            a=Gtk.CheckButton(label='Archived'); a.set_active(bool(row['archived']) if row else False); b.append(a); return c,n,bud,rate,a
        def save(f):
            c,n,bud,rate,a=f; name=n.get_text().strip(); budget=parse_hours(bud.get_text()); r=parse_money(rate.get_text())
            if not name: raise ValueError('Enter a project name.')
            if not row: self.store.add_project(selected(c),name,budget,r); return
            with self.store.db:
                self.store.db.execute('UPDATE projects SET name=?,budget=?,rate=?,archived=? WHERE id=?',(name,budget,r,int(a.get_active()),row['id'])); self.store.audit('project edited',{'id':row['id']})
        self.dialog('Edit project' if row else 'Add project',build,save)
    def task_dialog(self,row=None):
        choices=self.project_choices()
        if row and not any(i==row['project_id'] for i,_ in choices):
            parent=self.store.db.execute('SELECT p.name,c.name client FROM projects p JOIN clients c ON c.id=p.client_id WHERE p.id=?',(row['project_id'],)).fetchone(); choices.append((row['project_id'],parent['client']+' / '+parent['name']+' (archived)'))
        if not choices: self.error('Create a project first.'); return
        def build(b):
            p=dropdown(b,'Project',choices)
            if row: select_id(p,row['project_id']); p.set_sensitive(False)
            n=field(b,'Task name',row['name'] if row else ''); bud=field(b,'Time budget in hours (optional)',str(row['budget']/3600) if row and row['budget'] is not None else '')
            rate=field(b,'Hourly rate override (optional)',f"{row['rate']/100:.2f}" if row and row['rate'] is not None else '')
            a=Gtk.CheckButton(label='Archived'); a.set_active(bool(row['archived']) if row else False); b.append(a); return p,n,bud,rate,a
        def save(f):
            p,n,bud,rate,a=f; name=n.get_text().strip(); budget=parse_hours(bud.get_text()); r=parse_money(rate.get_text())
            if not name: raise ValueError('Enter a task name.')
            if not row: self.store.add_task(selected(p),name,budget,r); return
            with self.store.db:
                self.store.db.execute('UPDATE tasks SET name=?,budget=?,rate=?,archived=? WHERE id=?',(name,budget,r,int(a.get_active()),row['id'])); self.store.audit('task edited',{'id':row['id']})
        self.dialog('Edit task' if row else 'Add task',build,save)
    def rule_rows(self):
        return self.store.rows('''SELECT r.*,t.name task,p.name project,c.name client,
            t.archived task_archived,p.archived project_archived,c.archived client_archived
            FROM rules r JOIN tasks t ON t.id=r.task_id JOIN projects p ON p.id=t.project_id
            JOIN clients c ON c.id=p.client_id ORDER BY r.priority DESC,r.id''')
    def refresh_rules(self):
        from .rules import describe_rule,rule_health
        b=self.body_rules; self.clear(b); self.heading(b,'Assignment rules','Automatically assign matching recorded usage to a task as draft time.')
        b.append(label('A rule is a shortcut you choose once: “When I use this app, put its time on this task.” For example, a design app can go to your Design task. You still review the draft before approving it.','dim-label'))
        b.append(label('Use a rule only when an app usually belongs to one task. For a browser or app shared between projects, use daily review and optional Jev suggestions instead. Rules work locally, without an API.','dim-label'))
        controls=action_bar();b.append(controls)
        controls.append(button('Create assignment rule',lambda _:self.rule_dialog(),True))
        controls.append(button('Review today instead',lambda _:self.review_dialog(datetime.now().date())))
        b.append(label('New rules apply to future completed activity after the idle check. To use them on an earlier day, open that date in Calendar and choose “Apply saved rules to this day”. Existing task entries stay unchanged.','dim-label'))
        rules=self.rule_rows(); titles=self.store.get('capture_titles','0')=='1'
        if not rules: self.empty(b,'No assignment rules yet','Add a rule to match an application and choose the task that should receive its time.'); return
        for r in rules:
            health=rule_health(r,rules,capture_titles=titles)
            detail=('Enabled' if r['enabled'] else 'Paused')+f" · Priority {r['priority']}"
            if health: detail+='\n'+'\n'.join(x['message'] for x in health)
            self.row(b,describe_rule(r),detail,[
                ('Edit',lambda _,x=r:self.rule_dialog(x)),('Pause' if r['enabled'] else 'Enable',lambda _,x=r:self.run_action(lambda:self.toggle_rule(x))),('Delete',lambda _,i=r['id']:self.confirm('Delete this rule?','Existing time entries stay as they are.',lambda:self.delete_rule(i)))])
    def toggle_rule(self,row):
        from .rules import rule_health
        if not row['enabled']:
            proposed=dict(row,enabled=1)
            issues=rule_health(proposed,self.rule_rows(),capture_titles=self.store.get('capture_titles','0')=='1')
            blocked=[x['message'] for x in issues if x['code'] in ('target_archived','target_missing','duplicate','exact_conflict','titles_off')]
            if blocked: raise ValueError(' '.join(blocked))
        with self.store.db: self.store.db.execute('UPDATE rules SET enabled=? WHERE id=?',(0 if row['enabled'] else 1,row['id']))
    def delete_rule(self,rid):
        with self.store.db: self.store.db.execute('DELETE FROM rules WHERE id=?',(rid,)); self.store.audit('rule deleted',{'id':rid})
    def rule_dialog(self,row=None,application=None,task_id=None):
        from .rules import describe_rule,evaluate_rule,rule_health
        choices=self.task_choices()
        if not choices: self.quick_setup(after=lambda:self.rule_dialog(row,application,task_id)); return
        apps=[r['app'] for r in self.store.rows("SELECT DISTINCT app FROM activity WHERE state='active' AND app!='' ORDER BY app")]
        initial_app=row['app'] if row else application or ''
        if initial_app and initial_app not in apps: apps.insert(0,initial_app)
        rules=self.rule_rows(); titles=self.store.get('capture_titles','0')=='1'
        sample=self.store.rows("SELECT * FROM activity WHERE state='active' AND closed=1 ORDER BY end DESC LIMIT 2000")
        def build(b):
            b.append(label('Pick an app, then a task. No code, patterns or special words are needed.','dim-label'))
            known=dropdown(b,'1. When I use this application',[(None,'Choose an application…')]+[(a,a) for a in apps])
            custom=Gtk.Expander(label='App not listed? Enter its exact name');b.append(custom)
            custom_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);custom.set_child(custom_box)
            app=field(custom_box,'Application name',initial_app,'Use the name shown in recorded activity')
            custom_box.append(label('An app appears in the list after tracking records it. You can return here later instead of entering a name.','dim-label'))
            if not apps:b.append(label('No apps recorded yet. Use an app with tracking enabled, then return here to select it.','dim-label'))
            known.connect('notify::selected',lambda *_:app.set_text(selected(known) or ''))
            if initial_app:select_id(known,initial_app)
            task=dropdown(b,'2. Put its time on this task',[(None,'Choose a task…')]+choices)
            if row or task_id: select_id(task,row['task_id'] if row else task_id)
            b.append(label('3. Check the preview below, then Save. Future matching time is saved as draft time, never approved automatically.','dim-label'))
            title_options=Gtk.Expander(label='Optional: match a window title');b.append(title_options)
            title_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);title_options.set_child(title_box)
            title=field(title_box,'Window title contains (optional)',row['title'] if row else '')
            title_box.append(label('Leave blank for all windows in this app. Use plain words that appear in a recorded title. Window-title collection must be enabled in Settings.','dim-label'))
            if row and row['title']:title_options.set_expanded(True)
            advanced=Gtk.Expander(label='Advanced: priority'); b.append(advanced)
            ab=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6); advanced.set_child(ab)
            priority=field(ab,'Priority',str(row['priority']) if row else '0')
            ab.append(label('Higher priority wins. If equal highest priorities select different tasks, matching usage stays unassigned.','dim-label'))
            sentence=label('Choose an application and a task to preview your rule.');b.append(sentence)
            preview_details=Gtk.Expander(label='Preview: recorded matches and conflicts');b.append(preview_details)
            preview=label('','dim-label');preview_details.set_child(preview)
            pending=[0]
            def cancel_preview(*_):
                if pending[0]: GLib.source_remove(pending[0]); pending[0]=0
                return False
            self.dialogs[-1].connect('close-request',cancel_preview)
            def update(*_):
                if pending[0]: GLib.source_remove(pending[0])
                def render():
                    pending[0]=0
                    try: p=int(priority.get_text())
                    except ValueError: preview.set_text('Enter a whole-number priority to see the preview.'); return False
                    proposed=dict(id=row['id'] if row else None,app=app.get_text().strip(),title=title.get_text().strip(),task_id=selected(task),priority=p,enabled=1)
                    result=evaluate_rule(proposed,rules,sample,capture_titles=titles)
                    text=describe_rule(proposed,dict(choices).get(selected(task),'choose a task'))
                    sentence.set_text(text if app.get_text().strip() and selected(task) else 'Choose an application and a task to preview your rule.')
                    text+=f"\n\nPreview of up to 2,000 most recent retained completed activity periods: {fmt_duration(result['matched_seconds'])} matches; {fmt_duration(result['conflict_seconds'])} has an observed conflict; {fmt_duration(result['shadowed_seconds'])} is overridden by higher priority. This includes already assigned time and does not predict new assignments."
                    if result['examples']:
                        text+='\nExamples: '+ '; '.join((x['title'] or x['app'])[:100] for x in result['examples'])
                    if result['health']: text+='\n'+'\n'.join(x['message'] for x in result['health'])
                    preview.set_text(text); return False
                pending[0]=GLib.timeout_add(200,render)
            for widget in (app,title,priority): widget.connect('changed',update)
            task.connect('notify::selected',update); update()
            return app,title,task,priority
        def save(f):
            app,title,task,priority=f
            try: p=int(priority.get_text())
            except ValueError: raise ValueError('Priority must be a whole number.')
            if not -(2**63)<=p<2**63: raise ValueError('Priority is too large.')
            if selected(task) not in dict(self.task_choices()): raise ValueError('Choose an active task.')
            proposed=dict(id=row['id'] if row else None,app=app.get_text().strip(),title=title.get_text().strip(),task_id=selected(task),priority=p,enabled=1)
            issues=rule_health(proposed,self.rule_rows(),capture_titles=titles)
            blocked=[x['message'] for x in issues if x['code'] in ('application_missing','duplicate','exact_conflict','titles_off')]
            if blocked: raise ValueError(' '.join(blocked))
            if row: self.store.update_rule(row['id'],app.get_text(),title.get_text(),selected(task),p)
            else: self.store.add_rule(app.get_text(),title.get_text(),selected(task),p)
            self.toast('Assignment rule saved')
        self.dialog('Edit rule' if row else 'New rule',build,save)
    def refresh_reports(self):
        b=self.body_reports; self.clear(b); self.heading(b,'Client reports','Reviewed time, clear amounts and a saved billing history.')
        choices=self.client_choices()
        # Archived clients can still have approved work and saved billing history.
        choices += [(r['id'],r['name']+' (archived)') for r in self.store.rows('SELECT id,name FROM clients WHERE archived=1 ORDER BY name')]
        if not choices: self.empty(b,'Create a client first','Once you approve billable time, it can be included in a client report.',('New project',self.quick_setup)); return
        today=datetime.now().date(); client=dropdown(b,'Client',choices)
        b.append(label('Reports include approved, billable time only. Drafts must be approved in History first. Exporting a report does not mark time as billed.','dim-label'))
        dates=Gtk.Box(spacing=12); b.append(dates)
        start=field(dates,'From',today.replace(day=1).isoformat(),'YYYY-MM-DD'); end=field(dates,'Through',today.isoformat(),'YYYY-MM-DD')
        def create(_):
            def action():
                try:
                    a=datetime.strptime(start.get_text().strip(),'%Y-%m-%d').date(); z=datetime.strptime(end.get_text().strip(),'%Y-%m-%d').date()
                except ValueError: raise ValueError('Enter dates as YYYY-MM-DD.')
                if z<a: raise ValueError('End date must follow the start date.')
                return self.store.create_report(selected(client),day_bounds(a)[0],day_bounds(z)[1])
            self.run_action(action,self.preview_report)
        b.append(button('Create report from approved time',create,True))
        all_clients=Gtk.CheckButton(label='Include all clients in internal CSV'); b.append(all_clients)
        grouping=dropdown(b,'Internal CSV grouping',[('entries','Individual entries'),('client','Client'),('project','Project'),('task','Task'),('week','Week')])
        def internal(_):
            try:
                a=datetime.strptime(start.get_text().strip(),'%Y-%m-%d').date(); z=datetime.strptime(end.get_text().strip(),'%Y-%m-%d').date()
                if z<a: raise ValueError('End date must follow the start date.')
                content=self.store.internal_csv(day_bounds(a)[0],day_bounds(z)[1],None if all_clients.get_active() else selected(client),selected(grouping))
            except ValueError as exc:
                self.error(str(exc)); return
            self.save_file('Save internal time report','internal-time.csv',lambda path:Path(path).write_text(content,encoding='utf-8'))
        b.append(label('Internal CSV includes draft, approved and billed entries, including non-billable time. It does not change billing status.','dim-label'))
        b.append(button('Export internal time CSV',internal))
        b.append(button('Review drafts in History',lambda _:self.review_drafts()))
        b.append(label('Saved reports','title-3'))
        rows=self.store.rows('SELECT r.*,c.name client FROM reports r JOIN clients c ON c.id=r.client_id ORDER BY r.id DESC')
        if not rows: b.append(label('No reports yet. Review and approve time in History first.','dim-label'))
        for r in rows:
            items=self.store.report(r['id']); amount=sum(x['amount'] for x in items); state=self.report_state(r['id'])
            self.row(b,f"{r['client']} · {items[0]['currency']} {money(amount)}",f"Report #{r['id']} · {len(items)} entries · {datetime.fromtimestamp(r['start']):%d %b} – {datetime.fromtimestamp(r['end']-1):%d %b %Y} · {state}",[('Open report',lambda _,i=r['id']:self.preview_report(i))])
    def review_drafts(self,day=None,status='draft'):
        self.history_kind='tasks'; self.history_status=status; self.history_period='custom' if day else 'all'; self.history_billable='all'; self.history_search=''
        if day:self.history_from=day;self.history_to=day
        self.show_page('History')
    def report_state(self,rid):
        billing=self.store.db.execute('SELECT * FROM report_billing WHERE report_id=?',(rid,)).fetchone()
        if billing: return 'Billed · '+billing['invoice'] if billing['state']=='billed' else 'Corrected · retained snapshot'
        rows=self.store.rows('SELECT e.status,e.deleted,e.revision,re.revision saved FROM report_entries re JOIN entries e ON e.id=re.entry_id WHERE re.report_id=?',(rid,))
        if rows and all(r['status']=='billed' and not r['deleted'] for r in rows): return 'Billed'
        if any(r['deleted'] or r['status']!='approved' or r['revision']!=r['saved'] for r in rows): return 'Snapshot only · entries changed'
        return 'Ready to bill'
    def preview_report(self,rid):
        rows=self.store.report(rid); w=Adw.Window(title=f'Timesheet report {rid}',transient_for=self.win,modal=True,default_width=760,default_height=650)
        self.dialogs.append(w); self.dialog_count=len(self.dialogs)
        w.connect('close-request',lambda *_:self.dialog_closed(w))
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); w.set_content(box); head=Adw.HeaderBar(); box.append(head)
        head.pack_start(button('PDF',lambda _:self.export_report(rid,'pdf'))); head.pack_start(button('Invoice PDF',lambda _:self.invoice_pdf_dialog(rid))); head.pack_start(button('CSV',lambda _:self.export_report(rid,'csv'))); head.pack_start(button('Printable report',lambda _:self.export_report(rid,'html')))
        if self.report_state(rid)=='Ready to bill': head.pack_end(button('Mark billed',lambda _:self.bill_dialog(rid,w),True))
        billing=self.store.db.execute('SELECT * FROM report_billing WHERE report_id=?',(rid,)).fetchone()
        if billing and billing['state']=='billed': head.pack_end(button('Record correction',lambda _:self.correct_report_dialog(rid,w)))
        scroll=Gtk.ScrolledWindow(vexpand=True); box.append(scroll); body=margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12),24); scroll.set_child(body)
        self.heading(body,rows[0]['client'],f'Report #{rid} · '+self.report_state(rid))
        body.append(label(rows[0]['currency']+' '+money(sum(r['amount'] for r in rows)),'metric'))
        body.append(label('Exact recorded duration. Rates and amounts are frozen in this report.','dim-label'))
        for r in rows:
            self.row(body,f"{r['project']} / {r['task']}",f"{r.get('report_date','')} · {fmt_duration(r['end']-r['start'])} · {r['currency']} {money(r['rate'])}/h · {money(r['amount'])}\n{r['description']}")
        w.present()
    def correct_report_dialog(self,rid,preview=None):
        def build(b):
            b.append(label('Use this after correcting or cancelling the invoice in your invoicing system. The original report remains in history, and its entries return to draft for review.'))
            reason=field(b,'Reason for correction')
            confirm=Gtk.CheckButton(label='I have handled the invoice correction externally'); b.append(confirm)
            return reason,confirm
        def save(f):
            if not f[1].get_active(): raise ValueError('Confirm that the invoice has been handled externally.')
            self.store.reopen_report(rid,f[0].get_text()); self.toast('Correction recorded; entries need review')
            if preview: GLib.idle_add(lambda:(preview.close(),False)[1])
        self.dialog('Record billing correction',build,save)
    def bill_dialog(self,rid,preview=None):
        def build(b):
            b.append(label('Billed entries are locked and excluded from future billing reports.'))
            return field(b,'Invoice reference','','e.g. INV-2026-001')
        def save(w):
            self.store.mark_billed(rid,w.get_text()); self.toast('Report marked billed')
            if preview: GLib.idle_add(lambda:(preview.close(),False)[1])
        self.dialog('Mark report billed',build,save)
    def save_file(self,title,name,handler):
        chooser=Gtk.FileChooserNative(title=title,transient_for=self.dialogs[-1] if self.dialogs else self.win,action=Gtk.FileChooserAction.SAVE,accept_label='Save',cancel_label='Cancel'); chooser.set_current_name(name)
        def response(c,r):
            if r==Gtk.ResponseType.ACCEPT:
                f=c.get_file()
                try:
                    if not f or not f.get_path(): raise ValueError('Choose a local file.')
                    handler(f.get_path()); self.toast('Saved '+Path(f.get_path()).name)
                except (ValueError,sqlite3.Error,OSError) as exc: self.error(exc)
            c.destroy()
        chooser.connect('response',response); chooser.show()
    def invoice_pdf_dialog(self,rid):
        def build(b):
            b.append(label('Create a draft invoice PDF from this saved report. No tax is calculated; review before issuing. Export does not mark work billed.'))
            fields=[field(b,title,value) for title,value in [
                ('Invoice reference',''),('Seller name and address',self.store.get('invoice_seller','')),
                ('Customer name and address',self.store.report(rid)[0]['client']),
                ('Issue date (YYYY-MM-DD)',datetime.now().strftime('%Y-%m-%d')),
                ('Due date (YYYY-MM-DD)',datetime.now().strftime('%Y-%m-%d')),('Payment details',self.store.get('invoice_payment',''))]]
            remember=Gtk.CheckButton(label='Remember seller and payment details on this computer')
            remember.set_active(self.store.get('remember_invoice_details','0')=='1'); b.append(remember)
            b.append(label('Saved details are stored locally in the unencrypted database. Turn this off and save to forget them.','dim-label'))
            return fields,remember
        def save(form):
            from .pdf_export import report_pdf,write_pdf
            fields,remember=form
            invoice=dict(zip(('number','seller','customer','issued','due','payment'),[w.get_text() for w in fields]))
            content=report_pdf(self.store.report(rid),rid,invoice=invoice)
            self.store.set('remember_invoice_details',int(remember.get_active()))
            self.store.set('invoice_seller',invoice['seller'] if remember.get_active() else '')
            self.store.set('invoice_payment',invoice['payment'] if remember.get_active() else '')
            GLib.idle_add(lambda:(self.save_file('Save invoice draft',f'invoice-draft-{rid}.pdf',lambda path:write_pdf(path,content)),False)[1])
        self.dialog('Invoice PDF',build,save)

    def export_report(self,rid,kind):
        if kind=='pdf':
            from .pdf_export import report_pdf,write_pdf
            content=report_pdf(self.store.report(rid),rid)
            self.save_file('Save PDF report',f'timesheet-{rid}.pdf',lambda path:write_pdf(path,content))
            return
        content=self.store.csv_report(rid) if kind=='csv' else self.store.html_report(rid)
        self.save_file('Save report',f'timesheet-{rid}.{kind}',lambda p:Path(p).write_text(content,encoding='utf-8'))
    def append_ai_settings(self,b):
        from . import jev
        from .review import load_categories
        self.heading(b,'Optional Jev assistance')
        b.append(button('Set up Jev automation',lambda _:self.automation_dialog(),True))
        b.append(button('Describe work for Jev',lambda _:self.task_guidance_dialog()))
        b.append(label('Connect your own TypeSafe key to ask for task suggestions. Each suggestion has a data preview before you send it.','dim-label'))
        b.append(label('The key is held by your desktop keyring or the app’s secret portal, outside your timesheet database.','dim-label'))
        buttons=action_bar();b.append(buttons)
        connection=label('No connection check has been made.','dim-label');b.append(connection)
        def key_dialog(_):
            def build(box):
                box.append(label('Enter your own TypeSafe API key. Your account is billed by TypeSafe.'))
                key=field(box,'TypeSafe API key');key.set_visibility(False);key.set_input_purpose(Gtk.InputPurpose.PASSWORD);return key
            def save(key):
                jev.save_key(key.get_text());key.set_text('');self.toast('TypeSafe key saved securely')
            self.dialog('Connect TypeSafe',build,save)
        buttons.append(button('Add or replace TypeSafe key',key_dialog))
        def check(_):
            check_button.set_sensitive(False);connection.set_text('Checking TypeSafe… No activity is sent.')
            def work():
                try:
                    models=jev.check_connection(jev.get_key())
                    message='Connected. Jev is available.' if 'jev-latest' in models else 'Key accepted. Jev is not listed for this account; check access in the TypeSafe console.'
                except jev.JevError as exc:message=str(exc)
                except Exception:message='The connection check failed. Unlock your keyring and try again.'
                def done():
                    if self.win is not None and connection.get_root() is not None:
                        check_button.set_sensitive(True);connection.set_text(message)
                    return False
                GLib.idle_add(done)
            threading.Thread(target=work,daemon=True).start()
        check_button=button('Check connection',check);buttons.append(check_button)
        def remove_key():
            repo=self.automation_repo();repo.configure({**repo.config(),'mode':'off'})
            jev.delete_key()
        buttons.append(button('Remove TypeSafe key',lambda _:self.confirm('Remove TypeSafe key?','Background automation will turn off and the saved key will be removed from secure storage. An in-flight request may already have been sent.',remove_key)))
        expander=Gtk.Expander(label='Preferences and categories');b.append(expander)
        advanced=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);expander.set_child(advanced)
        advanced.append(label('These optional preferences stay in the local database and its backups.','dim-label'))
        tools=action_bar();advanced.append(tools)
        def category_dialog(_):
            choices=self.task_choices()
            if not choices:self.error('Create a task first.');return
            def build(box):
                name=field(box,'Category name','','e.g. design, admin, meetings');target=dropdown(box,'Map to task',choices)
                preview=label('','dim-label');box.append(preview)
                def update(*_):
                    chosen=next((n for i,n in choices if i==selected(target)),'')
                    preview.set_text((name.get_text().strip() or 'Category')+' → '+chosen+'. Used for future suggestions; existing time is unchanged.')
                name.connect('changed',update);target.connect('notify::selected',update);update();return name,target
            def save(form):
                name,target=form;value=name.get_text().strip()
                if not value or len(value)>80 or any(ord(c)<32 for c in value):raise ValueError('Enter a category of 1–80 characters without line breaks.')
                categories=load_categories(self.store.get('jev_categories','{}'),[i for i,_ in choices])
                previous=next((label for label in categories if label.casefold()==value.casefold()),None)
                if len(categories)>=50 and previous is None:raise ValueError('At most 50 categories can be saved.')
                if previous is not None:categories.pop(previous)
                candidate={**categories,value:selected(target)}
                validated=load_categories(json.dumps(candidate),[i for i,_ in choices])
                if value not in validated:raise ValueError('Use a category name without hidden control characters.')
                self.store.set('jev_categories',json.dumps(validated));self.toast('Category saved')
            self.dialog('Add or update category',build,save)
        tools.append(button('Add or update category',category_dialog))
        categories=load_categories(self.store.get('jev_categories','{}'),[i for i,_ in self.task_choices()])
        if categories:
            selector=dropdown(advanced,'Saved category',[(name,name) for name in sorted(categories,key=str.casefold)])
            def remove_category():
                categories.pop(selected(selector),None);self.store.set('jev_categories',json.dumps(categories));self.toast('Category removed')
            tools.append(button('Remove selected category',lambda _:self.confirm('Remove category?','Existing time and tasks remain unchanged.',remove_category)))
        def clear_learning():
            self.store.set('jev_preferences','{}');self.store.set('jev_feedback','{}');self.toast('Saved local choices cleared')
        tools.append(button('Clear saved local choices',lambda _:self.confirm('Clear saved choices?','Saved app-to-task choices and feedback counts will be removed.',clear_learning)))
        try:
            counts=json.loads(self.store.get('jev_feedback','{}'));accepted=int(counts.get('accepted',0));changed=int(counts.get('changed',0))
            if accepted<0 or changed<0:raise ValueError('invalid counts')
            advanced.append(label(f'Your opt-in sample: {accepted} AI choices kept and {changed} changed. This is not a measure of overall accuracy.','dim-label'))
            bins=counts.get('bins',{})
            if isinstance(bins,dict) and bins:
                details_exp=Gtk.Expander(label='Suggestion feedback by probability');details=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4);details_exp.set_child(details);advanced.append(details_exp)
                for label_name in ('0–49%','50–74%','75–89%','90–100%'):
                    value=bins.get(label_name,{})
                    if isinstance(value,dict):details.append(label(f"{label_name}: {value.get('accepted',0)} kept, {value.get('changed',0)} changed",'dim-label'))
                details.append(label('Small, self-selected samples can be misleading. This feedback does not calibrate or change background automation thresholds.','dim-label'))
        except (ValueError,TypeError,AttributeError,OverflowError):advanced.append(label('Local feedback counts unavailable.','dim-label'))
        advanced.append(Gtk.LinkButton(uri='https://console.typesafe.ai/',label='Open TypeSafe console'))
        advanced.append(Gtk.LinkButton(uri='https://help.typesafe.ai/articles/5974925716',label='TypeSafe data handling information'))

    def refresh_settings(self):
        if self.simple_mode() and not getattr(self,'simple_settings_override',False):return self.simple_settings()
        b=self.body_settings; self.clear(b); self.heading(b,'Settings','Control tracking, local data and optional AI services.')
        available=desktop.capture_available()
        if available: self.row(b,'Automatic tracking is ready','The desktop capture adapter is connected. App names are recorded; window titles are optional.')
        elif desktop.supported_desktop(): self.row(b,'Finish automatic tracking setup','Check desktop dependencies and helper activation in docs/INSTALL.md. After installation, save your work and sign out and back in once.',[('Install / repair setup',lambda _:self.install_setup())])
        else: self.row(b,'Manual timesheet mode','Capture needs a supported desktop adapter and reliable idle and lock services. Check the installation guide; manual timers and reports remain available.')
        from .diagnostics import diagnose
        def show_diagnostics(_):
            details=diagnose()
            self.info('Setup details',json.dumps(details,indent=2)+'\n\nThis diagnostic does not include activity or window titles.')
        b.append(button('View setup details',show_diagnostics))
        b.append(button('Check for updates',lambda _:self.check_app_updates()))
        b.append(Gtk.LinkButton(uri='https://github.com/peternewing/timesheet-linux/blob/main/docs/INSTALL.md',label='Open installation and desktop setup guide'))
        tracking=Adw.PreferencesGroup(title='Tracking'); b.append(tracking)
        capture=Adw.SwitchRow(title='Track desktop usage automatically',subtitle='Record the foreground app, excluding idle and locked time'); capture.set_active(self.store.get('capture_enabled','0')=='1'); tracking.add(capture)
        notifications=Adw.SwitchRow(title='Notify me when tracking needs attention',subtitle='Alert me if the background tracker detects that active tracking has become unavailable'); notifications.set_active(self.store.get('tracking_notifications','0')=='1'); tracking.add(notifications)
        titles=Adw.SwitchRow(title='Include window titles',subtitle='Titles can include document names and other sensitive information'); titles.set_active(self.store.get('capture_titles','0')=='1'); tracking.add(titles)
        startup=None
        if not desktop.FLATPAK:
            startup=Adw.SwitchRow(title='Start when I sign in',subtitle='Keep recording when the main window closes'); startup.set_active(desktop.AUTOSTART.exists()); tracking.add(startup)
        else:
            b.append(label('Startup is managed by the host companion.','dim-label'))
        backups=Adw.SwitchRow(title='Automatic daily backups',subtitle='Keep seven daily copies on this computer'); backups.set_active(self.store.get('auto_backup','1')=='1'); tracking.add(backups)
        exclusions=field(b,'Excluded applications',self.store.get('excluded_apps',''),'Exact app names separated by commas')
        names={r['app'] for r in self.store.rows("SELECT DISTINCT app FROM activity WHERE app!='' AND state='active' ORDER BY app") if ',' not in r['app']}
        names.update(x.strip() for x in exclusions.get_text().split(',') if x.strip())
        if names:
            chooser=dropdown(b,'Recorded or excluded application',[(name,name) for name in sorted(names,key=str.casefold)])
            actions=action_bar(); b.append(actions)
            def set_excluded(add):
                name=selected(chooser); values=[x.strip() for x in exclusions.get_text().split(',') if x.strip()]
                values=[x for x in values if x.casefold()!=name.casefold()]
                if add: values.append(name)
                exclusions.set_text(', '.join(values))
            actions.append(button('Exclude selected app',lambda _:set_excluded(True)))
            actions.append(button('Remove selected exclusion',lambda _:set_excluded(False)))
            b.append(label('Changes take effect after Save preferences. Excluded apps do not retain their app name or title.','dim-label'))
        idle=field(b,'Idle threshold in minutes',str(int(self.store.get('idle_seconds','300'))//60))
        retention=field(b,'Retain detailed activity for this many days',self.store.get('retention_days','30'))
        b.append(label('Task entries, report snapshots and backups are kept until you remove them. Raw activity expires independently.','dim-label'))
        def save(_):
            def apply():
                try: minutes=int(idle.get_text()); days=int(retention.get_text())
                except ValueError: raise ValueError('Idle threshold and retention must be whole numbers.')
                if not 1<=minutes<=240 or not 1<=days<=3650: raise ValueError('Idle: 1–240 minutes. Retention: 1–3650 days.')
                desktop.set_paused(self.store,not capture.get_active())
                for key,value in [('tracking_notifications',int(notifications.get_active())),('capture_titles',int(titles.get_active())),('excluded_apps',exclusions.get_text()),('idle_seconds',minutes*60),('retention_days',days),('auto_backup',int(backups.get_active()))]: self.store.set(key,value)
                if startup is not None: desktop.set_autostart(startup.get_active())
                desktop.start_collector()
            self.run_action(apply,lambda _:self.toast('Preferences saved'))
        b.append(button('Save preferences',save,True))
        self.append_ai_settings(b)
        self.heading(b,'Data and recovery')
        b.append(label('Data is stored at '+str(self.store.path),'dim-label'))
        try:
            copies=sorted((self.store.path.parent/'backups').glob('*.sqlite3'))
            backup_status=('Latest automatic backup: '+datetime.fromtimestamp(copies[-1].stat().st_mtime).strftime('%d %b %Y %H:%M')) if copies else 'No automatic backup found yet.'
        except OSError: backup_status='Automatic backup status is unavailable.'
        b.append(label(backup_status+' Backups on this computer do not protect against drive loss.','dim-label'))
        actions=Gtk.Box(spacing=8); b.append(actions)
        actions.append(button('Back up now',lambda _:self.save_file('Save backup','timesheet-backup.sqlite3',self.store.backup)))
        actions.append(button('Restore backup',lambda _:self.choose_backup()))
        actions.append(button('Open data folder',lambda _:Gio.AppInfo.launch_default_for_uri(DATA_DIR.as_uri(),None)))
        b.append(button('Delete activity for a period',lambda _:self.delete_period_dialog()))
        b.append(label('Deletion removes captured app details from this database. Task entries, reports and older backups remain. Database files are not encrypted. Copy a backup elsewhere for protection against drive loss.','dim-label'))
        if not desktop.FLATPAK: b.append(button('Stop background tracking',lambda _:self.confirm('Stop tracking?', 'Recording stops until you open the app or sign in again.',self.stop_collector)))
        else: b.append(label('The host companion manages automatic capture and startup. See the Flatpak installation guide.','dim-label'))
    def install_setup(self):
        self.run_action(lambda:desktop.install(),lambda result:self.info('Setup installed','Desktop capture dependencies are missing or this desktop is unsupported. See docs/INSTALL.md; manual timesheets remain available.' if result['manual_only'] else 'Sign out and back in once to activate your desktop helper; check tracking status afterwards.' if result['needs_sign_in'] else 'Automatic tracking is ready.'))
    def stop_collector(self): desktop.stop_collector()
    def delete_period_dialog(self):
        today=datetime.now().date()
        def build(b): return field(b,'From date',today.isoformat()),field(b,'Through date',today.isoformat())
        def save(f):
            try: a=datetime.strptime(f[0].get_text(),'%Y-%m-%d').date(); z=datetime.strptime(f[1].get_text(),'%Y-%m-%d').date()
            except ValueError: raise ValueError('Enter dates as YYYY-MM-DD.')
            if z<a: raise ValueError('End date must follow start date.')
            start,end=day_bounds(a)[0],day_bounds(z)[1]
            count=len(self.store.activity_for(start,end))
            self.confirm('Delete activity details?',f'{count} activity periods are affected. Timesheet entries and reports will remain. Older backups may contain deleted details.',lambda:self.delete_activity_period(start,end))
        self.dialog('Choose activity to delete',build,save)
    def delete_activity_period(self,start,end):
        desktop.stop_collector()
        try:
            with self.store.db:
                for row in self.store.rows('SELECT * FROM activity WHERE start<? AND end>?',(end,start)):
                    # Preserve portions outside the requested period without retaining the deleted detail.
                    self.store.db.execute('DELETE FROM activity WHERE id=?',(row['id'],))
                    for a,z in ((row['start'],min(start,row['end'])),(max(end,row['start']),row['end'])):
                        if z>a: self.store.db.execute('INSERT INTO activity(start,end,app,title,state,closed,session) VALUES(?,?,?,?,?,1,?)',(a,z,row['app'],row['title'],row['state'],row['session']))
                self.store.audit('activity period deleted',{'start':start,'end':end})
            self.automation_repo().prune()
            self.toast('Activity deleted')
        finally: desktop.start_collector()
    def choose_backup(self):
        chooser=Gtk.FileChooserNative(title='Choose a backup',transient_for=self.win,action=Gtk.FileChooserAction.OPEN,accept_label='Choose',cancel_label='Cancel')
        def response(c,r):
            path=c.get_file().get_path() if r==Gtk.ResponseType.ACCEPT and c.get_file() else None
            c.destroy()
            if path:
                self.confirm('Restore this backup?',f'{path}\n\nThe current data will be saved as a recovery copy and the collector will stop during restore.',lambda:self.restore_backup(path))
        chooser.connect('response',response); chooser.show()
    def restore_backup(self,path):
        # Validate and copy before stopping the collector or replacing the live database.
        candidate=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
        fd,tempname=tempfile.mkstemp(prefix='restore-',suffix='.sqlite3',dir=self.store.path.parent); os.close(fd)
        try:
            if candidate.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Backup integrity check failed.')
            names={r[0] for r in candidate.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'clients','projects','tasks','entries','activity','reports','runtime','settings'}.issubset(names): raise ValueError('This is not a compatible Time Sheet Linux backup.')
            target=sqlite3.connect(tempname)
            try: candidate.backup(target)
            finally: target.close()
            candidate.close()
            checked=Store(tempname)
            try: checked.validate()
            finally: checked.close()
            self.stop_collector()
            lock=open(DATA_DIR/'collector.lock','a+')
            try:
                deadline=time.monotonic()+5
                while True:
                    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); break
                    except BlockingIOError:
                        if time.monotonic()>deadline: raise ValueError('Collector did not stop; current data is unchanged.')
                        time.sleep(0.1)
                recovery=self.store.path.with_name('pre-restore-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3')
                self.store.backup(recovery)
                dbpath=self.store.path; self.store.close()
                try: os.replace(tempname,dbpath)
                finally: self.store=Store(dbpath)
                self.automation_repo().reset_after_restore()
                with self.store.db:
                    self.store.db.execute("UPDATE runtime SET task_id=NULL,started=NULL,checkpoint=NULL,state='stopped',collector_seen=NULL,capture_status='restored' WHERE id=1")
                    self.store.audit('backup restored',{'recovery_file':recovery.name})
            finally: lock.close()
            desktop.start_collector(); self.info('Backup restored',f'Previous data saved to {recovery}.')
        finally:
            candidate.close()
            if os.path.exists(tempname): os.unlink(tempname)

def main():
    parser=argparse.ArgumentParser(description='Private Linux desktop time tracking')
    from . import __version__
    parser.add_argument('--version',action='version',version=__version__)
    parser.add_argument('--diagnose',action='store_true',help='Print privacy-safe Linux compatibility diagnostics')
    parser.add_argument('--install',action='store_true',help='Install desktop launcher, GNOME helper and background startup')
    parser.add_argument('--uninstall',action='store_true',help='Remove desktop integration, keeping timesheet data')
    parser.add_argument('--collector-direct',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--automation-direct',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--automation-once',action='store_true',help='Process one permitted queued decision (requires saved consent)')
    parser.add_argument('--background',action='store_true',help='Start the background collector')
    parser.add_argument('--pause',action='store_true',help='Pause automatic tracking')
    parser.add_argument('--resume',action='store_true',help='Resume automatic tracking')
    parser.add_argument('--status',action='store_true',help='Print recording status')
    args=parser.parse_args()
    if args.diagnose:
        from .diagnostics import diagnose
        print(json.dumps(diagnose(),indent=2)); return 0
    if args.install:
        result=desktop.install(); print(json.dumps(result,indent=2)); return 0
    if args.uninstall: print(desktop.uninstall()); return 0
    if args.collector_direct:
        from .collector import run
        run(); return 0
    if args.automation_direct or args.automation_once:
        from .automation_worker import run
        return run(once=args.automation_once)
    if args.background: desktop.start_collector(); return 0
    if args.pause or args.resume or args.status:
        store=Store()
        try:
            if args.pause or args.resume: desktop.set_paused(store,args.pause); desktop.start_collector()
            if args.status: print(json.dumps(desktop.read_health(store),indent=2))
        finally: store.close()
        return 0
    app=TimeSheet(); return app.run([sys.argv[0]])

if __name__=='__main__': raise SystemExit(main())
