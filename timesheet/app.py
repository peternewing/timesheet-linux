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
        health=desktop.read_health(self.store); state=health['status']
        if state=='setup_required':
            description='Desktop capture needs setup. Check docs/INSTALL.md for your desktop, install its dependencies and helper, then sign out and back in.' if desktop.supported_desktop() else 'Automatic capture is unavailable. Check desktop dependencies in docs/INSTALL.md. Manual timers and timesheets remain available.'
            self.row(b,'Finish automatic tracking setup',description,[('Check setup',lambda _:self.show_page('Settings'))])
        elif state=='paused':
            self.row(b,'Automatic tracking is paused','Resume when you are ready. Titles are stored only if you enable them in Settings.',[('Resume tracking',self.toggle_capture)])
        elif state in ('stopped','error','degraded'):
            self.row(b,'Tracking needs attention',health.get('error') or 'Restart the tracker or check setup.',[('Restart tracking',lambda _:self.run_action(lambda:desktop.start_collector(),lambda _:self.toast('Tracker started'))),('Settings',lambda _:self.show_page('Settings'))])
        else:
            self.row(b,'Now using '+(rt['app'] or 'your desktop'),'Away and locked time are kept separate from active work.', [('Pause 15 min',lambda _:self.pause_for(15))])
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
    def refresh_rules(self):
        b=self.body_rules; self.clear(b); self.heading(b,'Automatic assignment','Teach the app once. Matching usage becomes draft task time for you to review.')
        b.append(label('Higher priority wins. Conflicting rules at the same priority leave activity unassigned. Rules apply to new settled activity; you can apply them to a past day from Calendar.','dim-label'))
        b.append(button('New rule',lambda _:self.rule_dialog(),True))
        rules=self.store.rows('''SELECT r.*,t.name task,p.name project,c.name client FROM rules r JOIN tasks t ON t.id=r.task_id JOIN projects p ON p.id=t.project_id JOIN clients c ON c.id=p.client_id ORDER BY priority DESC,id''')
        if not rules: self.empty(b,'Less assigning, more doing','Add a rule for a work application, or choose “Always assign” when reviewing its usage. Rules never approve time for billing.'); return
        for r in rules:
            self.row(b,f"{r['app']} → {r['client']} / {r['project']} / {r['task']}",f"Title contains: {r['title'] or 'Any title'} · Priority {r['priority']} · "+('Enabled' if r['enabled'] else 'Disabled'),[
                ('Edit',lambda _,x=r:self.rule_dialog(x)),('Disable' if r['enabled'] else 'Enable',lambda _,x=r:self.run_action(lambda:self.toggle_rule(x))),('Delete',lambda _,i=r['id']:self.confirm('Delete this rule?','Existing time entries stay as they are.',lambda:self.delete_rule(i)))])
    def toggle_rule(self,row):
        with self.store.db: self.store.db.execute('UPDATE rules SET enabled=? WHERE id=?',(0 if row['enabled'] else 1,row['id']))
    def delete_rule(self,rid):
        with self.store.db: self.store.db.execute('DELETE FROM rules WHERE id=?',(rid,)); self.store.audit('rule deleted',{'id':rid})
    def rule_dialog(self,row=None):
        choices=self.task_choices()
        if row and not any(i==row['task_id'] for i,_ in choices):
            old=self.store.db.execute('SELECT c.name client,p.name project,t.name task FROM tasks t JOIN projects p ON p.id=t.project_id JOIN clients c ON c.id=p.client_id WHERE t.id=?',(row['task_id'],)).fetchone()
            if old: choices.append((row['task_id'],f"{old['client']} / {old['project']} / {old['task']} (archived)"))
        if not choices: self.quick_setup(); return
        apps=[r['app'] for r in self.store.rows("SELECT DISTINCT app FROM activity WHERE state='active' AND app!='' ORDER BY app")]
        def build(b):
            app=field(b,'Application name',row['app'] if row else '','Use the name shown under Apps today')
            if apps:
                known=dropdown(b,'Or choose a recorded app',[(a,a) for a in apps]); known.connect('notify::selected',lambda *_:app.set_text(selected(known) or '')); app.set_text(row['app'] if row else apps[0])
            title=field(b,'Only when the title contains (optional)',row['title'] if row else ''); task=dropdown(b,'Assign to task',choices); priority=field(b,'Priority',str(row['priority']) if row else '0')
            if row: select_id(task,row['task_id'])
            if self.store.get('capture_titles','0')!='1': b.append(label('Window title collection is off; title-specific rules cannot match new activity until it is enabled in Settings.','dim-label'))
            preview=label('Choose an application to preview its recent activity.','dim-label'); b.append(preview)
            def update(*_):
                seconds=self.store.db.execute("SELECT COALESCE(SUM(end-start),0) FROM activity WHERE state='active' AND lower(app)=lower(?) AND instr(lower(title),lower(?))>0",(app.get_text(),title.get_text())).fetchone()[0]
                preview.set_text(fmt_duration(seconds)+' of retained activity matches. New rules apply to future settled usage. Use the calendar to apply rules to a past day.')
            app.connect('changed',update); title.connect('changed',update); update()
            return app,title,task,priority
        def save(f):
            app,title,task,priority=f
            try: p=int(priority.get_text())
            except ValueError: raise ValueError('Priority must be an integer.')
            if row: self.store.update_rule(row['id'],app.get_text(),title.get_text(),selected(task),p)
            else: self.store.add_rule(app.get_text(),title.get_text(),selected(task),p)
            self.toast('Automatic assignment rule saved')
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
        def internal(_):
            try:
                a=datetime.strptime(start.get_text().strip(),'%Y-%m-%d').date(); z=datetime.strptime(end.get_text().strip(),'%Y-%m-%d').date()
                if z<a: raise ValueError('End date must follow the start date.')
                content=self.store.internal_csv(day_bounds(a)[0],day_bounds(z)[1],selected(client))
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
    def review_drafts(self):
        self.history_kind='tasks'; self.history_status='draft'; self.history_period='all'; self.history_billable='all'; self.history_search=''; self.show_page('History')
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
            return [field(b,title,value) for title,value in [
                ('Invoice reference',''),('Seller name and address',''),
                ('Customer name and address',self.store.report(rid)[0]['client']),
                ('Issue date (YYYY-MM-DD)',datetime.now().strftime('%Y-%m-%d')),
                ('Due date (YYYY-MM-DD)',datetime.now().strftime('%Y-%m-%d')),('Payment details','')]]
        def save(fields):
            from .pdf_export import report_pdf,write_pdf
            invoice=dict(zip(('number','seller','customer','issued','due','payment'),[w.get_text() for w in fields]))
            content=report_pdf(self.store.report(rid),rid,invoice=invoice)
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
    def refresh_settings(self):
        b=self.body_settings; self.clear(b); self.heading(b,'Settings','Control what is recorded and keep your data on this computer.')
        available=desktop.capture_available()
        if available: self.row(b,'Automatic tracking is ready','The desktop capture adapter is connected. App names are recorded; window titles are optional.')
        elif desktop.supported_desktop(): self.row(b,'Finish automatic tracking setup','Check desktop dependencies and helper activation in docs/INSTALL.md. After installation, save your work and sign out and back in once.',[('Install / repair setup',lambda _:self.install_setup())])
        else: self.row(b,'Manual timesheet mode','Capture needs a supported desktop adapter and reliable idle and lock services. Check the installation guide; manual timers and reports remain available.')
        from .diagnostics import diagnose
        def show_diagnostics(_):
            details=diagnose()
            self.info('Setup details',json.dumps(details,indent=2)+'\n\nThis diagnostic does not include activity or window titles.')
        b.append(button('View setup details',show_diagnostics))
        b.append(Gtk.LinkButton(uri='https://github.com/peternewing/timesheet-linux/blob/linux-compatibility-0.3/docs/INSTALL.md',label='Open installation and desktop setup guide'))
        tracking=Adw.PreferencesGroup(title='Tracking'); b.append(tracking)
        capture=Adw.SwitchRow(title='Track desktop usage automatically',subtitle='Record the foreground app, excluding idle and locked time'); capture.set_active(self.store.get('capture_enabled','0')=='1'); tracking.add(capture)
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
                for key,value in [('capture_titles',int(titles.get_active())),('excluded_apps',exclusions.get_text()),('idle_seconds',minutes*60),('retention_days',days),('auto_backup',int(backups.get_active()))]: self.store.set(key,value)
                if startup is not None: desktop.set_autostart(startup.get_active())
                desktop.start_collector()
            self.run_action(apply,lambda _:self.toast('Preferences saved'))
        b.append(button('Save preferences',save,True))
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
