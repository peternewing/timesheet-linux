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
    if primary: w.add_css_class('suggested-action')
    return w

def label(text,css=None,*,selectable=True):
    if css in ('title-1','title-3','heading','metric','brand','field-label'): selectable=False
    w=Gtk.Label(label=str(text),xalign=0,wrap=True,selectable=selectable)
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


class TimeSheet(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.store=Store(); self.win=None; self.day=datetime.now().date(); self.page='Today'
        self.dialog_count=0; self.last_refresh=0; self.history_search=''; self.history_period='month'; self.history_status='all'
        self.dialogs=[]
        self.timer_label=None; self.timer_started=None
        self.live_signature=None; self.today_metrics={}; self.today_apps={}; self.calendar_live={}; self.history_live={}
        self.project_live={}; self.task_live={}; self.task_projects={}
        self.history_kind='tasks'
        self.history_from=datetime.now().date().replace(day=1); self.history_to=datetime.now().date(); self.history_billable='all'
        self.activity_filter='all'; self.selected_entries=set(); self.selected_blocks=[]; self.rendered_signature=None

    def do_activate(self):
        if self.win:
            self.win.present(); return
        self.win=Adw.ApplicationWindow(application=self,title='Time Sheet Linux',default_width=1120,default_height=800)
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
        self.start_timer_button=button('Start timer',lambda _:self.timer_dialog()); header.pack_start(self.start_timer_button)
        self.undo_button=button('Undo',lambda _:self.run_action(self.store.undo,lambda action:self.toast(action+' undone'))); header.pack_end(self.undo_button)
        header.pack_end(button('Refresh',lambda _:self.show_page(self.page)))
        header.pack_end(button('About',lambda _:self.info('About Time Sheet Linux', 'Version '+__version__+'\n\nYour data stays on this computer.')) )
        header.pack_end(button('Help',lambda _:self.info('From activity to a client report',
            '1. Projects: create a client, project and task. Set an hourly rate for billable work.\n\n'
            '2. Calendar: review captured activity and assign it to a task. Use Add time for work you recorded manually.\n\n'
            '3. History: check your entries and approve the drafts. Approval freezes the rate.\n\n'
            '4. Reports: create a report from approved work, export it, then mark it billed with your invoice reference.\n\n'
            'Draft = editable work. Approved = reviewed and ready to report. Billed = locked to protect your invoice history.\n\n'
            'Keyboard: Ctrl+1–7 opens pages, Ctrl+N creates a project, Ctrl+Z undoes an entry edit, Ctrl+R refreshes. Escape closes an edit form.')))
        split=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL); split.set_vexpand(True); layout.append(split)
        sidebar=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4); sidebar.add_css_class('sidebar'); margins(sidebar,12); sidebar.set_size_request(172,-1); split.append(sidebar)
        sidebar.append(margins(label('TIME SHEET','brand'),8)); self.nav={}
        for name,icon in zip(PAGES,PAGE_ICONS):
            b=Gtk.Button(); inner=Gtk.Box(spacing=10); inner.append(Gtk.Image.new_from_icon_name(icon)); inner.append(label(name,selectable=False)); b.set_child(inner)
            b.add_css_class('flat'); b.update_property([Gtk.AccessibleProperty.LABEL],[name]); b.set_tooltip_text(f'{name} (Ctrl+{len(self.nav)+1})'); b.connect('clicked',lambda _,n=name:self.show_page(n)); sidebar.append(b); self.nav[name]=b
        spacer=Gtk.Box(); spacer.set_vexpand(True); sidebar.append(spacer); sidebar.append(label('Private • on this computer','dim-label'))
        self.stack=Gtk.Stack(hexpand=True,vexpand=True); split.append(self.stack)
        for name in PAGES:
            scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            clamp=Adw.Clamp(maximum_size=1200,tightening_threshold=900)
            body=margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16),24)
            clamp.set_child(body); scroll.set_child(clamp); self.stack.add_named(scroll,name); setattr(self,'body_'+name.lower(),body)
        desktop.start_collector(); self.show_page('Today'); self.tick()
        self.tick_source=GLib.timeout_add(250,self.tick)
        self.timer_source=GLib.timeout_add(200,self.update_timer_display); self.win.present()
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
            health=desktop.read_health(self.store); status=health['status']; rt=self.store.runtime()
            self.timer_started=rt['started'] if rt['state']=='running' else None
            self.start_timer_button.set_visible(self.timer_started is None)
            self.update_timer_display()
            names={'active':'Tracking automatically','paused':'Tracking paused','setup_required':'Finish setup','stopped':'Tracking stopped','error':'Recording failed','degraded':'Tracking needs attention'}
            self.status.set_text(names.get(status,'Starting…'))
            self.capture_button.set_label('Resume' if self.store.get('capture_enabled','0')!='1' else 'Pause')
            if self.page=='Today':
                signature=(rt['state'],rt['capture_status'],rt['app'],datetime.now().date(),int(time.time())//15)
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
    def update_timer_display(self):
        if not self.win: return False
        self.timer_button.set_visible(self.timer_started is not None)
        if self.timer_started is not None:
            text=fmt_timer(time.time()-self.timer_started)
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
        self.timer_label=None
        b=self.body_today; self.clear(b); now=int(time.time()); start,end=day_bounds(datetime.now().date()); rt=self.store.runtime(); summary=self.store.day_summary(start,end,include_running=True,now=now)
        self.today_metrics={}; self.today_apps={}
        self.timer_started=rt['started'] if rt['state']=='running' else None; self.update_timer_display()
        self.heading(b,'Today',datetime.now().strftime('%A, %d %B')+' · Review your day and record your work')
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
        bar.append(button('Review today',lambda _:self.review_today(),True)); bar.append(button('Add time',lambda _:self.entry_dialog())); bar.append(button('New project',self.quick_setup))
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
        actions=[]
        if row['status']!='billed':
            actions=[('Edit',lambda _,i=eid:self.entry_dialog(i)),('Split',lambda _,r=row:self.split_dialog(r)),('Delete',lambda _,i=eid:self.confirm('Delete this time entry?','This can be undone until the entry changes again.',lambda:self.store.delete_entry(i)))]
            if row['status']=='draft': actions.insert(0,('Approve',lambda _,i=eid:self.run_action(lambda:self.store.approve(i),lambda _:self.toast('Time approved'))))
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
    def assign_dialog(self,blocks,app=None):
        if not blocks: self.toast('No completed, unassigned activity yet. Live usage becomes assignable when you switch apps.'); return
        if not self.task_choices(): self.quick_setup(after=lambda:self.assign_dialog(blocks,app)); return
        seconds=sum(b['end']-b['start'] for b in blocks)
        def build(b):
            b.append(label(f'{fmt_duration(seconds)} of activity. Time already assigned to a task will be skipped.'))
            task=dropdown(b,'Assign to',self.task_choices())
            if len(blocks)==1:
                suggestion=self.store.matching_task(blocks[0]['app'],blocks[0]['title'])
                if suggestion: select_id(task,suggestion)
            desc=field(b,'Client-facing description (optional)')
            remember=Gtk.CheckButton(label='Always assign this application to this task')
            same=len({r['app'] for r in blocks})==1 and all(r['state']=='active' for r in blocks)
            remember.set_sensitive(same); b.append(remember)
            b.append(label('Assigned time stays in draft until you review and approve it.','dim-label'))
            return task,desc,remember
        def save(f):
            task,desc,remember=f; count=self.store.assign_remaining(blocks,selected(task),desc.get_text(),remember.get_active())
            self.toast(f'{count} activity periods assigned')
        self.dialog('Assign activity',build,save)

    def refresh_calendar(self):
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
        for client in clients:
            title=client['name']+(' · Archived' if client['archived'] else '')
            rate='No default rate' if client['rate'] is None else client['currency']+' '+money(client['rate'])+'/hour'
            actions=[('Edit client',lambda _,r=client:self.client_dialog(r))]
            if not client['archived']: actions.append(('Add project',lambda _,i=client['id']:self.project_dialog(client_id=i)))
            self.row(b,title,rate,actions)
            for project in self.store.rows('SELECT * FROM projects WHERE client_id=? ORDER BY archived,name',(client['id'],)):
                seconds=self.store.db.execute('SELECT COALESCE(SUM(e.end-e.start),0) FROM entries e JOIN tasks t ON e.task_id=t.id WHERE e.deleted=0 AND t.project_id=?',(project['id'],)).fetchone()[0]
                detail=self.project_detail(seconds,project['budget'])
                card=self.row(b,project['name']+(' · Archived' if project['archived'] else ''),detail,[('Edit project',lambda _,r=project:self.project_dialog(r))])
                progress=None
                if project['budget']:
                    progress=Gtk.ProgressBar(fraction=min(1,seconds/project['budget'])); card.append(progress)
                self.project_live[project['id']]=(card.get_first_child().get_next_sibling(),project['budget'],progress)
                tasks=self.store.rows('SELECT t.*,COALESCE((SELECT SUM(e.end-e.start) FROM entries e WHERE e.deleted=0 AND e.task_id=t.id),0) spent FROM tasks t WHERE project_id=? ORDER BY archived,name',(project['id'],))
                for task in tasks:
                    detail=self.task_detail(task['spent'],task['budget'])
                    card=self.row(b,'  '+task['name']+(' · Archived' if task['archived'] else ''),detail,[('Edit task',lambda _,r=task:self.task_dialog(r))])
                    self.task_live[task['id']]=(card.get_first_child().get_next_sibling(),task['budget']); self.task_projects[task['id']]=project['id']
    def client_dialog(self,row=None):
        def build(b):
            n=field(b,'Client name',row['name'] if row else ''); c=field(b,'Currency code (GBP, EUR or USD)',row['currency'] if row else 'GBP'); rate=field(b,'Default hourly rate',f"{row['rate']/100:.2f}" if row and row['rate'] is not None else '', 'e.g. 60.00')
            a=Gtk.CheckButton(label='Archived'); a.set_active(bool(row['archived']) if row else False); b.append(a); return n,c,rate,a
        def save(f):
            n,c,r,a=f; rate=parse_money(r.get_text()); currency=c.get_text().strip().upper(); name=n.get_text().strip()
            if not name or currency not in ('GBP','EUR','USD'): raise ValueError('Enter a name and choose GBP, EUR or USD.')
            if not row: self.store.add_client(name,currency,rate…9179 tokens truncated…), started INTEGER, checkpoint INTEGER, state TEXT NOT NULL DEFAULT 'stopped', collector_seen INTEGER, capture_status TEXT NOT NULL DEFAULT 'not running');
INSERT OR IGNORE INTO runtime(id) VALUES(1);
'''

class Store:
    def _migrate(self):
        version=self.db.execute('PRAGMA user_version').fetchone()[0]
        if version>3:
            raise ValueError('This database was created by a newer version of Time Sheet Linux.')
        if version<3:
            # A consistent pre-migration copy is retained for existing user data.
            if self.db.execute('SELECT COUNT(*) FROM entries').fetchone()[0]:
                dest=self.path.with_name(self.path.stem+'-before-v3.sqlite3')
                if not dest.exists(): self.backup(dest)
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                additions={
                    'entries': [('deleted','INTEGER NOT NULL DEFAULT 0'),('origin',"TEXT NOT NULL DEFAULT 'manual'"),('activity_id','INTEGER')],
                    'activity': [('closed','INTEGER NOT NULL DEFAULT 1'),('auto_processed','INTEGER NOT NULL DEFAULT 0'),('session',"TEXT NOT NULL DEFAULT ''")],
                    'rules': [('created','INTEGER NOT NULL DEFAULT 0')],
                    'runtime': [('app',"TEXT NOT NULL DEFAULT ''"),('activity_state',"TEXT NOT NULL DEFAULT 'unknown'"),('last_error',"TEXT NOT NULL DEFAULT ''")],
                }
                for table,columns in additions.items():
                    present={r[1] for r in self.db.execute('PRAGMA table_info('+table+')')}
                    for name,typ in columns:
                        if name not in present: self.db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {typ}')
                self.db.execute('CREATE TABLE IF NOT EXISTS entry_changes(id INTEGER PRIMARY KEY,at INTEGER NOT NULL,action TEXT NOT NULL,before_state TEXT NOT NULL,after_state TEXT NOT NULL,undone INTEGER NOT NULL DEFAULT 0)')
                self.db.execute('CREATE TABLE IF NOT EXISTS notices(id INTEGER PRIMARY KEY,at INTEGER NOT NULL,message TEXT NOT NULL,read INTEGER NOT NULL DEFAULT 0)')
                self.db.execute("CREATE TABLE IF NOT EXISTS report_billing(report_id INTEGER PRIMARY KEY REFERENCES reports(id),invoice TEXT NOT NULL,at INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'billed',reason TEXT NOT NULL DEFAULT '')")
                self.db.execute('PRAGMA user_version=3')

    def notice(self,message):
        self.db.execute('INSERT INTO notices(at,message) VALUES(?,?)',(int(time.time()),message))

    def _record_change(self,action,before,after_ids):
        after=[dict(self.db.execute('SELECT * FROM entries WHERE id=?',(i,)).fetchone()) for i in after_ids]
        self.db.execute('INSERT INTO entry_changes(at,action,before_state,after_state) VALUES(?,?,?,?)',
                        (int(time.time()),action,json.dumps([dict(r) for r in before]),json.dumps(after)))

    def quick_project(self,client,project,task='General',rate=None,currency='GBP',budget=None):
        if not client.strip() or not project.strip() or not task.strip(): raise ValueError('Enter a client, project and task name.')
        if currency not in ('GBP','EUR','USD'): raise ValueError('Choose GBP, EUR or USD.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            c=self.db.execute('SELECT * FROM clients WHERE name=?',(client.strip(),)).fetchone()
            if c and c['archived']: raise ValueError('This client is archived. Unarchive it in Projects or choose another client name.')
            if c and (c['currency']!=currency or (rate is not None and c['rate']!=rate)):
                raise ValueError('This client already has different billing settings. Use Add project under that client in Projects, or choose a new client name.')
            cid=c[0] if c else self.db.execute('INSERT INTO clients(name,currency,rate) VALUES(?,?,?)',(client.strip(),currency,rate)).lastrowid
            p=self.db.execute('SELECT id FROM projects WHERE client_id=? AND name=?',(cid,project.strip())).fetchone()
            if p: raise ValueError('This project already exists for the client. Edit it or add a task in Projects.')
            pid=p[0] if p else self.db.execute('INSERT INTO projects(client_id,name,budget) VALUES(?,?,?)',(cid,project.strip(),budget)).lastrowid
            existing=self.db.execute('SELECT id FROM tasks WHERE project_id=? AND name=?',(pid,task.strip())).fetchone()
            tid=existing[0] if existing else self.db.execute('INSERT INTO tasks(project_id,name) VALUES(?,?)',(pid,task.strip())).lastrowid
            self.audit('project set up',{'task_id':tid})
            return tid

    def uncovered(self,start,end,now=None):
        """Unallocated subintervals; manual timers reserve their live interval."""
        intervals=[(r['start'],r['end']) for r in self.rows('SELECT start,end FROM entries WHERE deleted=0 AND start<? AND end>? ORDER BY start',(end,start))]
        rt=self.runtime()
        if rt['state']=='running' and rt['started'] is not None:
            intervals.append((rt['started'],int(time.time() if now is None else now)))
        cursor=int(start); result=[]
        for a,b in sorted(intervals):
            if b<=cursor: continue
            if a>=end: break
            if a>cursor: result.append((cursor,min(a,end)))
            cursor=max(cursor,b)
            if cursor>=end: break
        if cursor<end: result.append((cursor,int(end)))
        return [(a,b) for a,b in result if b>a]

    def activity_for(self,start,end,unassigned=False):
        result=[]
        for row in self.rows('SELECT * FROM activity WHERE start<? AND end>? ORDER BY start',(int(end),int(start))):
            record=dict(row); record['start']=max(row['start'],int(start)); record['end']=min(row['end'],int(end))
            if unassigned and row['state']=='active':
                for a,b in self.uncovered(record['start'],record['end']):
                    result.append(dict(record,start=a,end=b))
            elif not unassigned: result.append(record)
        return result

    def day_summary(self,start,end,include_running=False,now=None):
        entries=self.entries(start,end)
        assigned=sum(min(end,r['end'])-max(start,r['start']) for r in entries)
        if include_running:
            rt=self.runtime()
            if rt['state']=='running' and rt['started'] is not None:
                a=max(start,rt['started']); z=min(end,int(time.time() if now is None else now))
                if z>a:
                    # Future manual entries may overlap a still-running timer. Do
                    # not count that time twice; stop_timer will clip it too.
                    assigned+=z-a-sum(max(0,min(z,r['end'])-max(a,r['start'])) for r in entries)
        active=0; away=0; unassigned=0; apps={}
        for r in self.activity_for(start,end):
            seconds=r['end']-r['start']
            if r['state'] in ('active','personal'):
                active+=seconds; apps[r['app']]=apps.get(r['app'],0)+seconds
                if r['state']=='active': unassigned+=sum(b-a for a,b in self.uncovered(r['start'],r['end']))
            elif r['state'] in ('away','locked'): away+=seconds
        approved=sum(min(end,r['end'])-max(start,r['start']) for r in entries if r['status'] in ('approved','billed'))
        return dict(active=active,away=away,assigned=assigned,approved=approved,unassigned=unassigned,
                    drafts=sum(r['status']=='draft' for r in entries),apps=sorted(apps.items(),key=lambda pair:pair[1],reverse=True))

    def period_summary(self,start,end):
        """Summarise recorded entries and observed gaps, clipped to the period."""
        if end<=start: raise ValueError('End must be after start.')
        entries=self.entries(start,end)
        result=dict(recorded=0,approved=0,billable=0,drafts=0,gaps=0)
        for r in entries:
            seconds=min(end,r['end'])-max(start,r['start'])
            result['recorded']+=seconds
            if r['status'] in ('approved','billed'): result['approved']+=seconds
            if r['billable']: result['billable']+=seconds
            if r['status']=='draft': result['drafts']+=1
        result['gaps']=sum(r['end']-r['start'] for r in self.activity_for(start,end) if r['state']=='unknown')
        return result

    def set_personal(self,ids,personal=True):
        if not ids: raise ValueError('Select completed activity first.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for aid in set(ids):
                r=self.db.execute('SELECT * FROM activity WHERE id=?',(aid,)).fetchone()
                if not r or not r['closed'] or r['state'] not in ('active','personal'): raise ValueError('Choose completed application usage.')
                if personal and sum(b-a for a,b in self.uncovered(r['start'],r['end']))!=r['end']-r['start']: raise ValueError('Some of this activity is already assigned. Edit its task entry first.')
                self.db.execute('UPDATE activity SET state=?,auto_processed=1 WHERE id=?',('personal' if personal else 'active',aid))
            self.audit('activity marked personal' if personal else 'activity returned to review',{'count':len(set(ids))})

    def matching_rule(self,app,title,at=None):
        choices=[]
        for r in self.rows('''SELECT r.* FROM rules r JOIN tasks t ON r.task_id=t.id JOIN projects p ON t.project_id=p.id
              JOIN clients c ON p.client_id=c.id WHERE r.enabled=1 AND t.archived=0 AND p.archived=0 AND c.archived=0 ORDER BY r.priority DESC,r.id'''):
            if at is not None and r['created']>at: continue
            if r['app'].casefold()==app.casefold() and r['title'].casefold() in title.casefold(): choices.append(r)
        if not choices: return None
        best=[r for r in choices if r['priority']==choices[0]['priority']]
        targets={r['task_id'] for r in best}
        return best[0] if len(targets)==1 else None

    def matching_task(self,app,title):
        rule=self.matching_rule(app,title)
        return rule['task_id'] if rule else None

    def add_rule(self,app,title,task,priority=0):
        if not app.strip(): raise ValueError('Choose an application.')
        with self.db:
            rid=self.db.execute('INSERT INTO rules(app,title,task_id,priority,created) VALUES(?,?,?,?,?)',(app.strip(),title.strip(),task,int(priority),int(time.time()))).lastrowid
            self.audit('rule created',{'id':rid})
            return rid

    def update_rule(self,rule_id,app,title,task,priority=0):
        if not app.strip(): raise ValueError('Choose an application.')
        with self.db:
            cur=self.db.execute('UPDATE rules SET app=?,title=?,task_id=?,priority=?,created=? WHERE id=?',
                (app.strip(),title.strip(),task,int(priority),int(time.time()),rule_id))
            if not cur.rowcount: raise ValueError('Rule not found.')
            self.audit('rule edited',{'id':rule_id})

    def apply_rules(self,now=None,start=None,end=None):
        now=int(time.time() if now is None else now)
        cutoff=now-int(self.get('idle_seconds','300'))
        count=0
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if start is not None:
                self.db.execute("UPDATE activity SET auto_processed=0 WHERE state='active' AND closed=1 AND start>=? AND end<=?",(start,end or now))
            rows=self.rows("SELECT * FROM activity WHERE state='active' AND closed=1 AND auto_processed=0 AND end<=? ORDER BY start",(cutoff,))
            for r in rows:
                rule=self.matching_rule(r['app'],r['title'],None if start is not None else r['end'])
                if rule:
                    beginning=r['start'] if start is not None else max(r['start'],rule['created'])
                    for a,b in self.uncovered(beginning,r['end'],now):
                        self.db.execute("INSERT INTO entries(task_id,start,end,description,origin,activity_id) VALUES(?,?,?,'','automatic',?)",(rule['task_id'],a,b,r['id']))
                        count+=1
                self.db.execute('UPDATE activity SET auto_processed=1 WHERE id=?',(r['id'],))
            if count: self.audit('automatically assigned',{'entries':count})
        return count

    def assign_remaining(self,blocks,task,description='',remember=False):
        count=0
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            before=[]; ids=[]
            for block in blocks:
                original=self.db.execute('SELECT * FROM activity WHERE id=?',(block['id'],)).fetchone()
                if not original or original['state'] not in ('active','away'): raise ValueError('Activity is no longer available.')
                if not original['closed']: raise ValueError('This activity is still being recorded. Assign it once you switch apps or pause.')
                a=max(block['start'],original['start']); b=min(block['end'],original['end'])
                for x,y in self.uncovered(a,b):
                    cur=self.db.execute("INSERT INTO entries(task_id,start,end,description,origin,activity_id) VALUES(?,?,?,?,'assigned',?)",(task,x,y,description.strip(),original['id']))
                    ids.append(cur.lastrowid); count+=1
                if remember and original['state']=='active':
                    exists=self.db.execute("SELECT 1 FROM rules WHERE lower(app)=lower(?) AND title='' AND task_id=? AND enabled=1",(original['app'],task)).fetchone()
                    if not exists: self.db.execute('INSERT INTO rules(app,title,task_id,priority,created) VALUES(?,?,?,?,?)',(original['app'],'',task,0,int(time.time())))
            if not count: raise ValueError('This activity is already assigned to a task.')
            self._record_change('Assign activity',before,ids)
            self.audit('activity assigned',{'entries':count})
        return count

    def approve_many(self,ids):
        if not ids: raise ValueError('Select at least one draft entry.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for entry in dict.fromkeys(ids): self._approve_one(entry)

    def _approve_one(self,entry):
        row=self.db.execute('''SELECT e.*,COALESCE(t.rate,p.rate,c.rate) effective_rate,c.currency client_currency
                FROM entries e JOIN tasks t ON e.task_id=t.id JOIN projects p ON t.project_id=p.id
                JOIN clients c ON p.client_id=c.id WHERE e.deleted=0 AND e.id=?''',(entry,)).fetchone()
        if not row or row['status']!='draft': raise ValueError('Only draft entries can be approved.')
        if row['end']>time.time(): raise ValueError('Future time cannot be approved.')
        if row['origin'] in ('automatic','assigned'):
            activity=self.db.execute('SELECT * FROM activity WHERE id=?',(row['activity_id'],)).fetchone()
            if activity and (not activity['closed'] or activity['end']>time.time()-int(self.get('idle_seconds','300'))):
                raise ValueError('Recent activity is still settling. Review it after the idle threshold, or enter it explicitly as manual work.')
        if row['billable'] and row['effective_rate'] is None: raise ValueError('Set an hourly rate or mark this entry non-billable before approval.')
        self.db.execute("UPDATE entries SET status='approved',rate=?,currency=?,revision=revision+1 WHERE id=?",(row['effective_rate'],row['client_currency'],entry))
        self.audit('entry approved',{'id':entry})

    def merge_entries(self,ids):
        if len(set(ids))<2: raise ValueError('Select at least two adjacent entries.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            rows=[self.db.execute('SELECT * FROM entries WHERE deleted=0 AND id=?',(i,)).fetchone() for i in set(ids)]
            if any(r is None for r in rows): raise ValueError('An entry has changed. Refresh the list.')
            rows.sort(key=lambda r:r['start'])
            if any(r['status']=='billed' for r in rows): raise ValueError('Billed entries cannot be merged.')
            if len({(r['task_id'],r['billable']) for r in rows})!=1: raise ValueError('Choose entries for the same task and billable setting.')
            if any(a['end']!=b['start'] for a,b in zip(rows,rows[1:])): raise ValueError('Entries must be adjacent without a gap.')
            first=rows[0]
            description='; '.join(dict.fromkeys(r['description'] for r in rows if r['description']))
            self.db.execute("UPDATE entries SET end=?,description=?,origin='manual',activity_id=NULL,status='draft',rate=NULL,currency=NULL,revision=revision+1 WHERE id=?",(rows[-1]['end'],description,first['id']))
            for r in rows[1:]: self.db.execute('UPDATE entries SET deleted=1,revision=revision+1 WHERE id=?',(r['id'],))
            self._record_change('Merge entries',rows,[r['id'] for r in rows])
            self.audit('entries merged',{'id':first['id'],'count':len(rows)})

    def undo(self):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            change=self.db.execute('SELECT * FROM entry_changes WHERE undone=0 ORDER BY id DESC LIMIT 1').fetchone()
            if not change: raise ValueError('There is no change to undo.')
            before=json.loads(change['before_state']); after=json.loads(change['after_state'])
            revisions={}
            for expected in after:
                current=self.db.execute('SELECT * FROM entries WHERE id=?',(expected['id'],)).fetchone()
                same=current and {k:v for k,v in dict(current).items() if k!='revision'}=={k:v for k,v in expected.items() if k!='revision'}
                if not same or current['status']=='billed': raise ValueError('These entries changed after that action. Undo is unavailable.')
                revisions[current['id']]=current['revision']
            self.db.executemany('UPDATE entries SET deleted=1 WHERE id=?',[(r['id'],) for r in after])
            original_ids={r['id'] for r in before}
            for r in before:
                if not r['deleted']: self._assert_free(r['start'],r['end'])
                values={k:v for k,v in r.items() if k!='id'}
                values.update(status='draft',rate=None,currency=None,revision=revisions[r['id']]+1)
                self.db.execute('UPDATE entries SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),r['id']))
            for r in after:
                if r['id'] not in original_ids: self.db.execute('UPDATE entries SET revision=revision+1 WHERE id=?',(r['id'],))
            self.db.execute('UPDATE entry_changes SET undone=1 WHERE id=?',(change['id'],))
            self.audit('undone',{'action':change['action']})
            return change['action']
    def __init__(self, path=None):
        path = Path(path or DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not path.exists():
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
        os.chmod(path,0o600)
        self.path = path
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout=10000')
        self.db.executescript(SCHEMA)
        self.db.commit()
        self._migrate()

    def close(self): self.db.close()
    def rows(self, query, args=()): return self.db.execute(query, args).fetchall()
    def get(self, key, default=''): 
        row = self.db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row[0] if row else default
    def set(self, key, value):
        with self.db: self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,str(value)))
    def audit(self, action, details):
        self.db.execute('INSERT INTO audit(at,action,details) VALUES(?,?,?)',(int(time.time()),action,json.dumps(details)))
    def add_client(self,name,currency='GBP',rate=None):
        if not name.strip(): raise ValueError('Enter a client name.')
        if currency.strip().upper() not in ('GBP','EUR','USD'): raise ValueError('Choose GBP, EUR or USD; other currency precision is not yet supported.')
        with self.db:
            cur=self.db.execute('INSERT INTO clients(name,currency,rate) VALUES (?,?,?)',(name.strip(),currency.upper(),rate)); self.audit('client created',{'id':cur.lastrowid}); return cur.lastrowid
    def add_project(self,client,name,budget=None,rate=None):
        if not name.strip(): raise ValueError('Enter a project name.')
        with self.db:
            cur=self.db.execute('INSERT INTO projects(client_id,name,budget,rate) VALUES (?,?,?,?)',(client,name.strip(),budget,rate)); self.audit('project created',{'id':cur.lastrowid}); return cur.lastrowid
    def add_task(self,project,name,budget=None,rate=None):
        if not name.strip(): raise ValueError('Enter a task name.')
        with self.db:
            cur=self.db.execute('INSERT INTO tasks(project_id,name,budget,rate) VALUES (?,?,?,?)',(project,name.strip(),budget,rate)); self.audit('task created',{'id':cur.lastrowid}); return cur.lastrowid
    def tasks(self):
        return self.rows('''SELECT t.id, c.name AS client, p.name AS project, t.name AS task, t.budget,
            COALESCE((SELECT SUM(e.end-e.start) FROM entries e WHERE e.task_id=t.id AND e.deleted=0),0) AS spent,
            c.currency, COALESCE(t.rate,p.rate,c.rate) AS effective_rate FROM tasks t
            JOIN projects p ON p.id=t.project_id JOIN clients c ON c.id=p.client_id
            WHERE t.archived=0 AND p.archived=0 AND c.archived=0 ORDER BY c.name,p.name,t.name''')
    def _assert_free(self,start,end,exclude=None):
        if int(end) <= int(start): raise ValueError('End time must be after start time.')
        if self.db.execute('SELECT 1 FROM entries WHERE deleted=0 AND start < ? AND end > ? AND id != ? LIMIT 1',(end,start,exclude or -1)).fetchone():
            raise ValueError('This time overlaps an existing entry. Adjust or split it first.')
        rt=self.db.execute('SELECT * FROM runtime WHERE id=1').fetchone()
        if rt['state']=='running' and rt['started'] is not None and end > rt['started'] and start < max(int(time.time()),rt['started']+1):
            raise ValueError('This time overlaps the running timer. Stop it first.')
    def add_entry(self,task,start,end,description='',billable=True):
        start,end=int(start),int(end)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self._assert_free(start,end)
            cur=self.db.execute('INSERT INTO entries(task_id,start,end,description,billable) VALUES (?,?,?,?,?)',(task,start,end,description.strip(),int(billable)))
            self.audit('entry created',{'id':cur.lastrowid}); self._record_change('Add entry',[],[cur.lastrowid]); return cur.lastrowid
    def update_entry(self,entry,task,start,end,description,billable,expected_revision=None):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old=self.db.execute('SELECT * FROM entries WHERE deleted=0 AND id=?',(entry,)).fetchone()
            if not old: raise ValueError('Entry not found.')
            if expected_revision is not None and old['revision']!=expected_revision: raise ValueError('This entry changed while you were editing it. Reopen it to see the latest version.')
            if old['status']=='billed': raise ValueError('Billed entries are locked. Keep this entry and record a separate correction.')
            self._assert_free(int(start),int(end),entry)
            self.db.execute("UPDATE entries SET task_id=?,start=?,end=?,description=?,billable=?,origin='manual',activity_id=NULL,status='draft',rate=NULL,currency=NULL,revision=revision+1 WHERE id=?",(task,int(start),int(end),description.strip(),int(billable),entry))
            self.audit('entry edited',{'id':entry})
            self._record_change('Edit entry',[old],[entry])
    def delete_entry(self,entry):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old=self.db.execute('SELECT * FROM entries WHERE deleted=0 AND id=?',(entry,)).fetchone()
            if not old: raise ValueError('Entry not found.')
            if old['status']=='billed': raise ValueError('Billed entries are locked.')
            if self.db.execute('SELECT 1 FROM report_entries WHERE entry_id=?',(entry,)).fetchone(): raise ValueError('This entry belongs to a saved report and cannot be deleted. Edit it instead.')
            self.audit('entry deleted',{'id':entry})
            self.db.execute("UPDATE entries SET deleted=1,revision=revision+1 WHERE id=?",(entry,))
            self._record_change('Delete entry',[old],[entry])
    def split_entry(self,entry,point):
        point=int(point)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old=self.db.execute('SELECT * FROM entries WHERE deleted=0 AND id=?',(entry,)).fetchone()
            if not old: raise ValueError('Entry not found.')
            if old['status']=='billed': raise ValueError('Billed entries are locked.')
            if not old['start'] < point < old['end']: raise ValueError('Split time must be inside the entry.')
            self.db.execute("UPDATE entries SET end=?,status='draft',rate=NULL,currency=NULL,revision=revision+1 WHERE id=?",(point,entry))
            cur=self.db.execute('INSERT INTO entries(task_id,start,end,description,billable) VALUES(?,?,?,?,?)',
                (old['task_id'],point,old['end'],old['description'],old['billable']))
            self.audit('entry split',{'id':entry,'new_id':cur.lastrowid})
            self._record_change('Split entry',[old],[entry,cur.lastrowid])
            return cur.lastrowid
    def assign_activity_batch(self,ids,task,description=''):
        if not ids: raise ValueError('Select one or more activity blocks.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for activity_id in dict.fromkeys(ids):
                r=self.db.execute('SELECT * FROM activity WHERE id=?',(activity_id,)).fetchone()
                if not r or r['state']!='active': raise ValueError('Activity is no longer available for assignment.')
                self._assert_free(r['start'],r['end'])
                self.db.execute('INSERT INTO entries(task_id,start,end,description) VALUES(?,?,?,?)',(task,r['start'],r['end'],description.strip()))
            self.audit('activity assigned',{'count':len(set(ids)),'task_id':task})
    def entries(self,start,end,client=None,status=None,search=''):
        sql='''SELECT e.*, t.name AS task, p.name AS project, c.name AS client, c.id AS client_id,
                 COALESCE(t.rate,p.rate,c.rate) AS suggested_rate,c.currency AS client_currency
                 FROM entries e JOIN tasks t ON t.id=e.task_id JOIN projects p ON p.id=t.project_id
                 JOIN clients c ON c.id=p.client_id WHERE e.deleted=0 AND e.start < ? AND e.end > ?'''
        args=[int(end),int(start)]
        if client: sql+=' AND c.id=?'; args.append(client)
        if status: sql+=' AND e.status=?'; args.append(status)
        if search: sql+=' AND (e.description LIKE ? OR c.name LIKE ? OR p.name LIKE ? OR t.name LIKE ?)'; args += ['%'+search+'%']*4
        return self.rows(sql+' ORDER BY e.start DESC',args)
    def approve(self,entry):
        return self.approve_many([entry])
    def start_timer(self,task,now=None):
        now=int(time.time() if now is None else now)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            rt=self.db.execute('SELECT * FROM runtime WHERE id=1').fetchone()
            if rt['state']=='running': raise ValueError('Stop the running timer first.')
            if self.db.execute('SELECT 1 FROM entries WHERE deleted=0 AND start<=? AND end>?',(now,now)).fetchone(): raise ValueError('The current time is already assigned.')
            self.db.execute("UPDATE runtime SET task_id=?,started=?,checkpoint=?,state='running' WHERE id=1",(task,now,now)); self.audit('timer started',{'task_id':task})
    def stop_timer(self,now=None,reason='stopped'):
        now=int(time.time() if now is None else now)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            rt=self.db.execute('SELECT * FROM runtime WHERE id=1').fetchone()
            if rt['state']!='running': return None
            start=rt['started']; end=now
            conflict=self.db.execute('SELECT MIN(start) FROM entries WHERE deleted=0 AND start >= ? AND start < ?',(start,end)).fetchone()[0]
            if conflict is not None: end=conflict
            self.db.execute("UPDATE runtime SET task_id=NULL,started=NULL,checkpoint=NULL,state='stopped' WHERE id=1")
            eid=None
            if end>start:
                self._assert_free(start,end)
                eid=self.db.execute("INSERT INTO entries(task_id,start,end,description,origin) VALUES (?,?,?,?,'timer')",(rt['task_id'],start,end,'')).lastrowid
            self.audit('timer stopped',{'entry_id':eid,'reason':reason}); return eid
    def runtime(self): return self.db.execute('SELECT * FROM runtime WHERE id=1').fetchone()
    def backup(self,dest):
        if Path(dest).resolve()==self.path.resolve(): raise ValueError('Choose a backup path other than the active database.')
        target=sqlite3.connect(dest)
        try: self.db.backup(target); result=target.execute('PRAGMA integrity_check').fetchone()[0]
        finally: target.close()
        if result!='ok': raise ValueError('Backup did not pass the integrity check.')
        os.chmod(dest,0o600)
    def validate(self):
        if self.db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Database integrity check failed.')
        if self.rows('PRAGMA foreign_key_check'): raise ValueError('Database references are inconsistent.')
        # Exercise all required columns before a restored file can replace live data.
        for query in [
            'SELECT id,name,currency,rate,archived FROM clients LIMIT 0',
            'SELECT id,client_id,name,budget,rate,archived FROM projects LIMIT 0',
            'SELECT id,project_id,name,budget,rate,archived FROM tasks LIMIT 0',
            'SELECT id,task_id,start,end,description,billable,status,rate,currency,invoice,revision,origin,activity_id,deleted FROM entries LIMIT 0',
            'SELECT id,start,end,app,title,state,closed,session,auto_processed FROM activity LIMIT 0',
            'SELECT key,value FROM settings LIMIT 0',
            'SELECT id,created,client_id,start,end,snapshot FROM reports LIMIT 0']:
            self.db.execute(query)
        invalid=self.db.execute("SELECT 1 FROM entries WHERE end<=start OR status NOT IN ('draft','approved','billed') OR billable NOT IN (0,1) OR rate<0 OR (billable=1 AND status IN ('approved','billed') AND rate IS NULL) LIMIT 1").fetchone()
        overlap=self.db.execute('SELECT 1 FROM entries a JOIN entries b ON a.id<b.id AND a.start<b.end AND a.end>b.start WHERE a.deleted=0 AND b.deleted=0 LIMIT 1').fetchone()
        if invalid or overlap: raise ValueError('The backup contains invalid or overlapping timesheet entries.')
        for r in self.rows('SELECT id,snapshot FROM reports'):
            try:
                lines=json.loads(r['snapshot'])
                required={'id','start','end','rate','amount','currency','client','project','task','description'}
                if not isinstance(lines,list) or not lines: raise ValueError()
                for line in lines:
                    if not isinstance(line,dict) or not required.issubset(line): raise ValueError()
                    if any(type(line[key]) is not int for key in ('id','start','end','rate','amount')): raise ValueError()
                    if line['id']<=0 or line['end']<=line['start'] or line['rate']<0 or line['amount']<0: raise ValueError()
                    if line['currency'] not in ('GBP','EUR','USD'): raise ValueError()
                    if any(not isinstance(line[key],str) for key in ('client','project','task','description')): raise ValueError()
                    datetime.fromtimestamp(line['start']); datetime.fromtimestamp(line['end'])
                    if 'report_date' in line: datetime.strptime(line['report_date'],'%Y-%m-%d')
            except (ValueError,TypeError,OverflowError,OSError): raise ValueError('A saved report is malformed.')
        return True
    def create_report(self,client,start,end):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            rows=[dict(r) for r in self.entries(start,end,client,'approved') if r['billable']]
            if not rows: raise ValueError('No approved, unbilled work in this period.')
            if any(r['start'] < start or r['end'] > end for r in rows): raise ValueError('An entry crosses the report boundary. Split it first.')
            for row in rows:
                # Stored rate is minor currency units per hour; amounts round only once per line.
                row['amount'] = int((Decimal(row['end']-row['start'])*Decimal(row['rate'])/Decimal(3600)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
                row['report_date']=datetime.fromtimestamp(row['start']).strftime('%Y-%m-%d')
            cur=self.db.execute('INSERT INTO reports(created,client_id,start,end,snapshot) VALUES (?,?,?,?,?)',(int(time.time()),client,int(start),int(end),json.dumps(rows)))
            self.db.executemany('INSERT INTO report_entries VALUES (?,?,?)',[(cur.lastrowid,r['id'],r['revision']) for r in rows])
            self.audit('report created',{'id':cur.lastrowid}); return cur.lastrowid
    def report(self,rid):
        row=self.db.execute('SELECT * FROM reports WHERE id=?',(rid,)).fetchone()
        if not row: raise ValueError('Report not found.')
        return json.loads(row['snapshot'])
    def mark_billed(self,rid,invoice):
        if not invoice.strip(): raise ValueError('Enter an invoice reference.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            records=self.rows('''SELECT e.id,e.status,e.deleted,e.revision,r.revision snapshot_revision FROM report_entries r JOIN entries e ON e.id=r.entry_id WHERE r.report_id=?''',(rid,))
            if not records: raise ValueError('Report not found or empty.')
            if any(r['deleted'] or r['status']!='approved' or r['revision']!=r['snapshot_revision'] for r in records): raise ValueError('Report is stale or entries are already billed. Create a new report.')
            self.db.executemany("UPDATE entries SET status='billed',invoice=?,revision=revision+1 WHERE id=?",[(invoice.strip(),r['id']) for r in records])
            self.db.execute('INSERT INTO report_billing(report_id,invoice,at) VALUES(?,?,?)',(rid,invoice.strip(),int(time.time())))
            self.audit('marked billed',{'report_id':rid,'invoice':invoice.strip()})

    def reopen_report(self,rid,reason):
        if not reason.strip(): raise ValueError('Explain the invoice correction for your history.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            billing=self.db.execute('SELECT * FROM report_billing WHERE report_id=?',(rid,)).fetchone()
            if not billing or billing['state']!='billed': raise ValueError('This report is not currently marked billed.')
            rows=self.rows('SELECT e.*,r.revision saved FROM report_entries r JOIN entries e ON e.id=r.entry_id WHERE r.report_id=?',(rid,))
            if any(r['status']!='billed' or r['invoice']!=billing['invoice'] or r['revision']!=r['saved']+1 for r in rows): raise ValueError('These entries have changed. Review the billing history first.')
            self.db.executemany("UPDATE entries SET status='draft',invoice=NULL,rate=NULL,currency=NULL,revision=revision+1 WHERE id=?",[(r['id'],) for r in rows])
            self.db.execute("UPDATE report_billing SET state='corrected',reason=? WHERE report_id=?",(reason.strip(),rid))
            self.audit('billing corrected',{'report_id':rid,'invoice':billing['invoice'],'reason':reason.strip()})
    def internal_csv(self,start,end,client=None,group='entries'):
        """Export current task time, including non-billable work, without billing it."""
        if int(end)<=int(start): raise ValueError('End must be after start.')
        if group not in ('entries','client','project','task','week'): raise ValueError('Choose a valid grouping.')
        out=io.StringIO(newline=''); w=csv.writer(out)
        safe=lambda x: "'"+x if x.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else x
        rows=self.entries(start,end,client=client)
        if group=='entries':
            w.writerow(['Start','End','Client','Project','Task','Description','Hours in period','Billable','Status'])
            for r in rows:
                a=max(int(start),r['start']); z=min(int(end),r['end'])
                w.writerow([datetime.fromtimestamp(a).isoformat(sep=' '),datetime.fromtimestamp(z).isoformat(sep=' '),
                            *[safe(str(r[k])) for k in ('client','project','task','description')],
                            f"{Decimal(z-a)/Decimal(3600):.6f}",'Yes' if r['billable'] else 'No',r['status']])
        else:
            totals={}
            for r in rows:
                a=max(int(start),r['start']); z=min(int(end),r['end'])
                while a<z:
                    if group=='week':
                        day=datetime.fromtimestamp(a).date(); monday=day-timedelta(days=day.weekday())
                        key=monday.isoformat(); boundary=int(datetime.combine(monday+timedelta(days=7),datetime.min.time()).timestamp())
                        finish=min(z,boundary)
                    else:
                        key=' / '.join(str(r[k]) for k in ('client','project','task')[:{'client':1,'project':2,'task':3}[group]])
                        finish=z
                    values=totals.setdefault(key,[0,0]); values[0 if r['billable'] else 1]+=finish-a; a=finish
            w.writerow(['Week beginning' if group=='week' else group.capitalize(),'Billable hours','Non-billable hours','Total hours'])
            for key,(billable,nonbillable) in sorted(totals.items()):
                w.writerow([safe(key),*[f"{Decimal(seconds)/Decimal(3600):.6f}" for seconds in (billable,nonbillable,billable+nonbillable)]])
        return out.getvalue()

    def csv_report(self,rid):
        out=io.StringIO(newline=''); w=csv.writer(out)
        w.writerow(['Date','Client','Project','Task','Description','Actual hours','Billed hours','Hourly rate','Currency','Amount'])
        for r in self.report(rid):
            # Spreadsheet formula injection: prefix dangerous untrusted text.
            safe=lambda x: "'"+x if x.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else x
            hours=f"{Decimal(r['end']-r['start'])/Decimal(3600):.6f}"
            w.writerow([r.get('report_date',datetime.fromtimestamp(r['start']).strftime('%Y-%m-%d')),*[safe(str(r[k])) for k in ('client','project','task','description')],hours,hours,f"{Decimal(r['rate'])/100:.2f}",r['currency'],f"{Decimal(r['amount'])/100:.2f}"])
        return out.getvalue()
    def html_report(self,rid):
        rows=self.report(rid); e=html.escape
        def duration(seconds): return f'{seconds//3600}h {(seconds%3600)//60:02d}m {seconds%60:02d}s'
        items=''.join('<tr>'+''.join('<td>'+e(v)+'</td>' for v in [r.get('report_date',datetime.fromtimestamp(r['start']).strftime('%Y-%m-%d')),r['project'],r['task'],r['description'],duration(r['end']-r['start']),f"{Decimal(r['rate'])/100:.2f}",r['currency'],f"{Decimal(r['amount'])/100:.2f}"])+'</tr>' for r in rows)
        total=sum(r['amount'] for r in rows)
        return '<!doctype html><html><head><meta charset="utf-8"><title>Timesheet report</title><style>body{font:14px sans-serif;margin:2em;color:#222}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:8px;border-bottom:1px solid #ccc}thead{display:table-header-group}@media print{tr{break-inside:avoid}}</style></head><body><h1>Timesheet report</h1><p>Client: '+e(rows[0]['client'])+' · Report '+str(rid)+' · Dates use the local time zone at report creation.</p><p>Exact time; no duration rounding.</p><table><thead><tr><th>Date</th><th>Project</th><th>Task</th><th>Description</th><th>Duration</th><th>Rate</th><th>Currency</th><th>Amount</th></tr></thead><tbody>'+items+'</tbody></table><p><strong>Total: '+e(rows[0]['currency'])+' '+f'{Decimal(total)/100:.2f}'+'</strong></p></body></html>'

def parse_money(text):
    if not text.strip(): return None
    try:
        value=Decimal(text.strip())
        if not value.is_finite() or value<0 or value>Decimal('1000000000') or value.as_tuple().exponent < -2: raise ValueError()
        return int(value*100)
    except Exception: raise ValueError('Enter a rate between 0 and 1,000,000,000 with at most two decimal places.')

def parse_hours(text):
    if not text.strip(): return None
    try:
        value=Decimal(text.strip())
        if not value.is_finite() or value<0 or value>Decimal('1000000000'): raise ValueError()
        return int(value*3600)
    except Exception: raise ValueError('Enter hours between 0 and 1,000,000,000.')

def local_timestamp(text):
    """Parse unambiguous local wall time; reject DST gaps and repeated hours."""
    parsed=None
    for fmt in ('%Y-%m-%d %H:%M:%S','%Y-%m-%d %H:%M'):
        try:
            parsed=datetime.strptime(text.strip(),fmt); break
        except ValueError: pass
    if parsed is None: raise ValueError('Use date and time format YYYY-MM-DD HH:MM or YYYY-MM-DD HH:MM:SS.')
    expected=(parsed.year,parsed.month,parsed.day,parsed.hour,parsed.minute,parsed.second)
    candidates=set()
    for isdst in (0,1):
        try:
            ts=int(time.mktime((*expected,0,0,isdst)))
            if tuple(time.localtime(ts)[:6])==expected: candidates.add(ts)
        except (ValueError,OverflowError,OSError): pass
    if not candidates: raise ValueError('That local time does not exist because the clock changed. Choose another time.')
    if len(candidates)>1: raise ValueError('That local time occurs twice because the clock changed. Use a time outside the repeated hour.')
    return candidates.pop()
