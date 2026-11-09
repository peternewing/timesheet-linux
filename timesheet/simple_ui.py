"""The everyday product: four setup steps, one day, one question at a time."""
from __future__ import annotations
import json
import threading
import time
from datetime import datetime,timedelta
from . import desktop
from .day_record import snapshot,bounds,duration

from .decision_policy import owner_token
from .simple_setup import BUCKETS,TOOLS,preset_ids,selected_tools,save_tools
from .setup_ui import SetupUI
from .screen_ui import ScreenTimeUI
from . import simple_store


def compact(seconds):
    seconds=max(0,int(seconds))
    return f'{seconds//3600:02d}:{seconds%3600//60:02d}:{seconds%60:02d}'


class SimpleUI(SetupUI,ScreenTimeUI):
    def simple_mode(self):return self.store.get('interface_mode','simple')!='advanced'

    def simple_choices(self):
        ids=preset_ids(self.store)
        allowed=self.automation_repo().config().get('category_tasks',[]) or list(ids.values())
        return [(tid,BUCKETS[key][0]) for key,tid in ids.items() if tid in allowed]

    def simple_window(self,title,width=640,height=650):
        from .app import Adw,Gtk,button,margins
        window=Adw.Window(title=title,transient_for=self.dialogs[-1] if self.dialogs else self.win,modal=True,default_width=width,default_height=height)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);window.set_content(outer)
        header=Adw.HeaderBar();outer.append(header);header.pack_end(button('Close',lambda control:control.get_root().close()))
        scroll=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER);outer.append(scroll)
        body=margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16),24);scroll.set_child(body)
        self.dialogs.append(window);self.dialog_count=len(self.dialogs);keys=self.automation_escape(window)
        def closed(widget):
            if keys.get_widget()==widget:widget.remove_controller(keys)
            widget.set_focus(None)
            # Dynamic controls can own Python callbacks which refer to their
            # window. Unparenting only the outer content leaves that native /
            # Python reference cycle alive after a fully rendered dialog closes.
            while body.get_first_child():body.remove(body.get_first_child())
            widget.set_content(None)
            return self.dialog_closed(widget)
        window.connect('close-request',closed)
        return window,body,header

    def simple_expand(self,box,title,text):
        from .app import Gtk,label
        expander=Gtk.Expander(label=title);expander.set_child(label(text,'dim-label'));box.append(expander);return expander

    def simple_review_meter(self,window,source='daily'):
        from .app import GLib
        from .review_metrics import Session
        meter=Session(self.store,source)
        def tick():
            if window not in self.dialogs:meter.finish();return False
            meter.observe(window.is_active());return True
        window.connect('close-request',lambda *_:meter.finish())
        GLib.timeout_add(500,tick);return meter

    def simple_tool_choices(self,body,chosen,changed=None):
        from .app import Gtk,button,label
        from .automation_ui import wrapped_check
        expander=Gtk.Expander(label='Choose useful tools (optional)')
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);expander.set_child(box);body.append(expander)
        for key,(name,target) in TOOLS.items():
            check=wrapped_check(name);check.set_active(key in chosen)
            def toggle(w,key=key):
                if w.get_active():chosen.add(key)
                else:chosen.discard(key)
                if changed:changed([k for k in TOOLS if k in chosen])
            check.connect('toggled',toggle);box.append(check)
            if changed:box.append(button('Open '+target.lower(),lambda _,target=target:self.show_page(target)))
        box.append(label('Selected tools appear in More actions on your day. Rules run locally; client reports use approved entries. Adding a shortcut does not change what Jev receives.','dim-label'))
        return expander

    def simple_repair(self,status=None):
        from .app import GLib
        if desktop.FLATPAK:
            text='Flatpak needs the host recording companion. Open Advanced tools → Recording settings for desktop setup.'
            if status:status.set_text(text)
            else:self.info('Recording setup',text)
            return
        if status:status.set_text('Checking recording…')
        def work():
            try:
                result=desktop.install();message='Sign out and back in once to finish recording setup.' if result['needs_sign_in'] else 'Recording is ready.' if not result['manual_only'] else 'This desktop needs a supported recording helper. Open Advanced recording settings.'
            except Exception:message='Could not repair recording. Open Advanced recording settings for diagnostics.'
            GLib.idle_add(lambda:(status.set_text(message) if status and status.get_root() else self.info('Recording setup',message),False)[1])
        threading.Thread(target=work,daemon=True).start()

    def simple_today(self):
        from .app import button,label,Gtk
        body=self.body_today;self.clear(body)
        self.today_metrics={};self.today_apps={};self.timer_label=None
        self.heading(body,'Today',datetime.now().strftime('%A, %d %B'))
        if self.store.get('simple_setup_complete','0')!='1':
            icon=Gtk.Image.new_from_icon_name('appointment-soon-symbolic');icon.set_pixel_size(64);body.append(icon)
            self.heading(body,'Your screen time, understood.','Set up once. Use your computer. See your personal and work day.')
            body.append(button('Set up in 4 steps',lambda _:self.simple_setup_wizard(),True))
            self.simple_expand(body,'Already using an older version?','Your existing time, projects and reports are still here. Set up the simple activity categories for this version, or find older tools in Settings → Advanced tools.')
            return
        self.simple_day_body(body,datetime.now().date())

    def simple_day_body(self,body,day):
        from .app import Gtk,button,label,Timeline,append_in_batches
        from .automation_status import worker_state
        record=snapshot(self.store,day,now=int(time.time()),include_running=True);config=self.automation_repo().config();health=desktop.read_health(self.store)
        is_today=day==datetime.now().date();items=simple_store.review_items(self.store,day);self.simple_view_day=day
        if is_today:
            reason=self.store.get('ai_pause_reason','')
            valid_owner=config['owner']==owner_token()
            if health['status']!='active':
                title='Recording is paused' if self.store.get('capture_enabled','0')!='1' else 'Recording needs attention'
                self.row(body,title,'Your saved day is safe.',[('Resume recording',self.toggle_capture)] if self.store.get('capture_enabled','0')!='1' else [('Repair recording',lambda _:self.simple_repair())])
            if config.get('category_tasks') and not set(config['category_tasks'])<=set(preset_ids(self.store).values()):
                self.row(body,'Your activity categories changed','Run setup to restore ready-made categories. Existing time stays saved.',[('Reset activity categories',lambda _:self.simple_setup_wizard())])
            elif config['mode']!='off' and not valid_owner:
                self.row(body,'Finish setup for this version','A few clicks reconnect Jev to this installation.',[('Continue setup',lambda _:self.simple_setup_wizard())])
            elif reason:
                self.row(body,'Jev needs attention','Recording continues. Your categories can wait.',[('Fix Jev',lambda _:self.simple_ai_status())])
            elif config['mode']=='off':
                self.row(body,'Recording locally','Local app types can organise clear activity. Connect Jev for remaining apps.',[('Connect Jev',lambda _:self.simple_setup_wizard())])
            elif worker_state(self.store)=='not running':
                self.row(body,'Jev is not running','Your local activity record is still available.',[('Restart Jev',lambda _:desktop.start_automation())])
            else:body.append(label('Jev organises in the background. Unclear activity waits for your choice.','dim-label'))
        metrics=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,min_children_per_line=1,max_children_per_line=3,column_spacing=10,row_spacing=10)
        self.simple_metrics={};self.simple_metric_buttons={}
        for key,title in [('active','Screen time'),('ai','Organised automatically'),('human','Chosen by you')]:
            card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);card.set_can_target(False)
            value=label(compact(record['screen_seconds'] if key=='active' else record[key]),'metric',selectable=False);card.append(value);card.append(label(title,'dim-label',selectable=False))
            control=Gtk.Button();control.set_child(card);control.add_css_class('card');control.add_css_class('metric-selector')
            control.update_property([Gtk.AccessibleProperty.LABEL],[title]);control.connect('clicked',lambda _,key=key:self.simple_select_metric(key));metrics.append(control)
            self.simple_metrics[key]=value;self.simple_metric_buttons[key]=control
        body.append(metrics)
        self.simple_details=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);body.append(self.simple_details)
        self.simple_details_signature=None;self.simple_render_details(record)
        actions=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,min_children_per_line=1,max_children_per_line=3,column_spacing=8,row_spacing=8);body.insert_child_after(actions,metrics.get_prev_sibling())
        actions.append(button('Organise my day',lambda _:self.simple_organise(day),True))
        if items:actions.append(button(f'Help Jev with {len(items)}'+('+' if len(items)==100 else '')+(' choice' if len(items)==1 else ' choices'),lambda _:self.simple_review(day)))
        elif record['unclassified']:body.append(label('Some activity is waiting for Jev or was left uncategorised.','dim-label'))
        else:body.append(label('No choices waiting.','dim-label'))
        actions.append(button('Save day record',lambda _:self.simple_export(day)))
        self.simple_unclassified=label('Uncategorised: '+compact(record['unclassified']),'dim-label');body.append(self.simple_unclassified)
        rt=self.store.runtime()
        if rt['state']=='running':self.row(body,'Your task timer is running','Stop it when this task is finished.',[('Stop timer',lambda _:self.run_action(self.store.stop_timer))])
        body.append(label('Your day at a glance','title-3'))
        start,end=bounds(day);timeline=Timeline(start,end,record['activity']);body.append(timeline);self.simple_timeline=timeline
        more=Gtk.Expander(label='More actions');more.set_expanded(getattr(self,'simple_more_open',False));more.connect('notify::expanded',lambda w,*_:setattr(self,'simple_more_open',w.get_expanded()));tools=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);more.set_child(tools);body.append(more)
        tools.append(button('Start task timer',lambda _:self.timer_dialog()))
        tools.append(button('Add missing time',lambda _:self.simple_add_time(day)))
        tools.append(button('Review activity & assign projects',lambda _:self.simple_detailed_day(day)))
        tools.append(button('Screen-time insights',lambda _:self.screen_insights(day)))
        tools.append(button('Personal / work spaces',lambda _:self.screen_space_dialog()))
        for key in selected_tools(self.store):
            name,target=TOOLS[key];tools.append(button(name,lambda _,target=target:self.show_page(target)))
        self.simple_expand(body,'Timeline colours','Blue: recorded app activity. Grey: away or locked. Red: missing capture. Personal and excluded activity stay separate. App activity is evidence of use, not proof that an output was completed.')
        from .day_record import digest_text
        self.simple_expand(body,'What this record means',digest_text(record)+' Manual time may extend beyond app activity. Export does not approve billing.')

    def simple_select_metric(self,key):
        if key not in ('active','ai','human'):return
        self.simple_metric_view=key
        day=getattr(self,'simple_view_day',datetime.now().date())
        self.simple_render_details(snapshot(self.store,day,now=int(time.time()),include_running=True),force=True)

    def simple_render_details(self,record,force=False):
        from .app import Gtk,label,button,append_in_batches,set_changed_text
        key=getattr(self,'simple_metric_view','active')
        for name,control in self.simple_metric_buttons.items():
            if name==key:control.add_css_class('selected')
            else:control.remove_css_class('selected')
        entries=[e for e in record['entries'] if (e['source'] in ('AI category','Rule category','App type category'))==(key=='ai')] if key!='active' else []
        signature=(key,(tuple(name for name,_ in record['top_apps']),tuple((r['start'],r['app'],r['state']) for r in record['activity'])) if key=='active' else tuple((e['id'],e['revision']) for e in entries),bool(record.get('running')))
        if not force and signature==self.simple_details_signature:
            if key=='active':
                for name,seconds in record['top_apps']:
                    value,bar=self.simple_top_rows[name];set_changed_text(value,compact(seconds));bar.set_fraction(seconds/max(1,record['active']))
                for r in record['activity']:
                    if r['state']=='active' and (r['start'],r['app']) in self.simple_period_rows:set_changed_text(self.simple_period_rows[(r['start'],r['app'])],datetime.fromtimestamp(r['start']).strftime('%H:%M:%S')+'–'+datetime.fromtimestamp(r['end']).strftime('%H:%M:%S')+' · '+r['app'])
            if getattr(self,'simple_running_value',None) and record.get('running'):set_changed_text(self.simple_running_value,compact(record['running']['seconds']))
            return
        self.simple_details_signature=signature;self.clear(self.simple_details);self.simple_top_rows={};self.simple_period_rows={};self.simple_running_value=None
        box=self.simple_details
        if key=='active':
            from . import screen_spaces
            quick=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,min_children_per_line=1,max_children_per_line=2,column_spacing=8,row_spacing=8);box.append(quick)
            quick.append(button('This week',lambda _:self.screen_insights(record['day'])))
            name=screen_spaces.SPACES[screen_spaces.effective_now(self.store)['space']]
            quick.append(button('Space now: '+name,lambda _:self.screen_space_dialog()))
            if record['private']:box.append(label('Private recorded use: '+compact(record['private'])+' · app names hidden','dim-label'))
            box.append(label('Top activities','title-3'))
            if not record['top_apps']:box.append(label('Recorded apps will appear here, longest first.','dim-label'))
            extra=None
            if len(record['top_apps'])>5:
                more=Gtk.Expander(label='More activities');extra=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);more.set_child(extra)
            for index,(name,seconds) in enumerate(record['top_apps']):
                target=box if index<5 else extra
                row=Gtk.Box(spacing=12);row.append(label(name));value=label(compact(seconds),'dim-label');value.set_hexpand(True);value.set_halign(Gtk.Align.END);row.append(value)
                assign=button('Assign',lambda _,name=name:self.simple_assign_activity(record['day'],name))
                assign.update_property([Gtk.AccessibleProperty.LABEL],['Assign '+name+' for this day']);row.append(assign);target.append(row)
                bar=Gtk.ProgressBar(fraction=seconds/max(1,record['active']));target.append(bar);self.simple_top_rows[name]=(value,bar)
            if extra is not None:box.append(more)
            periods=Gtk.Expander(label='Recorded activity periods');periods.set_expanded(getattr(self,'simple_periods_open',False));periods.connect('notify::expanded',lambda w,*_:setattr(self,'simple_periods_open',w.get_expanded()));rows=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);periods.set_child(rows);box.append(periods)
            def period_row(target,row):
                line=label(datetime.fromtimestamp(row['start']).strftime('%H:%M:%S')+'–'+datetime.fromtimestamp(row['end']).strftime('%H:%M:%S')+' · '+row['app'],'dim-label');target.append(line);self.simple_period_rows[(row['start'],row['app'])]=line
            append_in_batches(rows,[r for r in record['activity'] if r['state']=='active'],period_row,25)
        else:
            box.append(label('Organised automatically' if key=='ai' else 'Chosen by you','title-3'))
            if not entries and not (key=='human' and record.get('running')):box.append(label('No automatically organised periods yet.' if key=='ai' else 'No category choices or manual time saved yet.','dim-label'))
            def render(target,entry):
                clock=lambda ts:datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                card=self.row(target,entry['task'],f"{clock(entry['start'])}–{clock(entry['end'])} · {compact(entry['end']-entry['start'])} · {entry['source']}",[] if entry['status']=='billed' else [('Change category',lambda _:self.simple_change(entry))])
                if key=='ai':
                    from .automation_status import explain_entry
                    self.simple_expand(card,'Why this category?',explain_entry(self.store,entry['id']))
            append_in_batches(box,entries,render,25)
            if key=='human' and record.get('running'):
                box.append(label('Running timer · '+record['running']['task'],'heading'));self.simple_running_value=label(compact(record['running']['seconds']),'dim-label');box.append(self.simple_running_value)

    def simple_tick(self,rt,health,now=None):
        from .app import set_changed_text
        if getattr(self,'simple_activity_override',False):
            if not self.dialog_count and time.monotonic()-self.last_refresh>15:
                self.refresh_calendar_details();self.last_refresh=time.monotonic()
            return
        if self.page not in ('Today','Calendar') or self.store.get('simple_setup_complete','0')!='1':return
        now=int(time.time() if now is None else now)
        if now==getattr(self,'simple_last_tick',None):return
        self.simple_last_tick=now
        day=datetime.now().date() if self.page=='Today' else self.day
        ai=self.store.db.execute('SELECT MAX(updated) FROM ai_jobs').fetchone()[0]
        from .automation_status import worker_state
        from .screen_spaces import effective_now
        context=effective_now(self.store,now)
        signature=(day,ai,self.store.get('ai_pause_reason'),health['status'],worker_state(self.store,now),context['space'],context['source'])
        if not self.dialog_count and signature!=getattr(self,'simple_signature',None):
            self.simple_signature=signature
            if self.page=='Today':self.simple_today()
            else:self.simple_past_days()
            return
        # All counters and rankings use this one timestamp and one DB snapshot.
        record=snapshot(self.store,day,now=now,include_running=True)
        for key,value in getattr(self,'simple_metrics',{}).items():set_changed_text(value,compact(record['screen_seconds'] if key=='active' else record[key]))
        if getattr(self,'simple_unclassified',None):set_changed_text(self.simple_unclassified,'Uncategorised: '+compact(record['unclassified']))
        if not self.dialog_count:self.simple_render_details(record)
        if getattr(self,'simple_timeline',None):self.simple_timeline.records=record['activity'];self.simple_timeline.queue_draw()

    def simple_past_days(self):
        from .app import Gtk,GLib,button,label,action_bar
        body=self.body_calendar;self.clear(body);self.heading(body,'Past days')
        nav=action_bar();body.append(nav)
        def shift(delta):self.day+=timedelta(days=delta);self.simple_past_days()
        nav.append(button('Previous day',lambda _:shift(-1)));nav.append(label(self.day.strftime('%a, %d %b %Y')))
        next_button=button('Next day',lambda _:shift(1));next_button.set_sensitive(self.day<datetime.now().date());nav.append(next_button)
        picker=Gtk.Expander(label='Pick a date');calendar=Gtk.Calendar();calendar.select_day(GLib.DateTime.new_local(self.day.year,self.day.month,self.day.day,12,0,0));picker.set_child(calendar);body.append(picker)
        def changed(widget):
            date=widget.get_date();chosen=datetime(date.get_year(),date.get_month(),date.get_day_of_month()).date()
            if chosen>datetime.now().date():self.toast('Choose today or an earlier day');return
            self.day=chosen;self.simple_past_days()
        calendar.connect('day-selected',changed)
        self.simple_day_body(body,self.day)

    def simple_assign_activity(self,day,app):
        from datetime import date
        if isinstance(day,str):day=date.fromisoformat(day)
        item=simple_store.activity_item(self.store,day,app)
        if item:self.simple_review(day,items=[item])
        else:
            self.simple_select_metric('human')
            self.toast('No unassigned settled periods. Saved categories can be changed below; recent activity will settle shortly.')

    def simple_organise(self,day):
        from .app import GLib,button,label
        from . import day_organiser
        config=self.automation_repo().config()
        if config['mode']=='off' or config['owner']!=owner_token():self.simple_setup_wizard();return
        if self.store.get('ai_pause_reason',''):self.simple_ai_status();return
        try:batch=day_organiser.request(self.store,day)
        except ValueError as exc:self.toast(str(exc));return
        desktop.start_automation()
        window,body,_=self.simple_window('Organise my day',height=420)
        self.heading(body,'Jev is organising your day',day.strftime('%A, %d %B'))
        status=label('Finding recorded activities…');body.append(status)
        choices=button('Review uncertain activities',lambda _:(window.close(),self.simple_review(day)),True);choices.set_visible(False);body.append(choices)
        fix=button('Fix Jev',lambda _:(window.close(),self.simple_ai_status()));fix.set_visible(False);body.append(fix)
        body.append(button('Back to my day',lambda _:(window.close(),self.show_page(self.page))))
        self.simple_expand(body,'What Jev does','Jev compares your categories, app names and permitted clues. Clear matches become reversible, non-billable drafts. Equivalent activity reuses the decision. Only uncertain apps need your choice. Existing assignments, privacy choices and usage limits are preserved. Recent activity waits until it is settled. Nothing proves completed output from app time alone.')
        def poll():
            if window not in self.dialogs:return False
            progress=day_organiser.progress(self.store,batch);current=day_organiser.active(self.store)
            running=bool(current and current['id']==batch['id']);reason=self.store.get('ai_pause_reason','')
            status.set_text(('Jev needs attention. ' if reason else 'Organising… ' if running else 'Pass finished. ')+f"{progress['organised']} periods organised · {progress['waiting']} waiting")
            waiting=simple_store.review_items(self.store,day);choices.set_visible(bool(waiting) and not running);choices.set_label(f'Review {len(waiting)} uncertain '+('activity' if len(waiting)==1 else 'activities'))
            fix.set_visible(bool(reason))
            if not running and progress['waiting']:status.set_text('This pass stopped. Remaining activity will continue in the background within your settings.')
            if not running and not progress['waiting'] and not waiting:status.set_text('All eligible activity is organised. Recent, excluded or deliberately uncategorised activity stays separate.')
            return True
        poll();GLib.timeout_add_seconds(1,poll);window.present()

    def simple_add_time(self,day):
        if day==datetime.now().date():self.entry_dialog()
        else:self.entry_dialog(start=bounds(day)[0]+9*3600,end=bounds(day)[0]+9*3600+1800)

    def simple_detailed_day(self,day):
        self.day=day;self.simple_activity_override=True
        self.show_page('Calendar')

    def simple_review(self,day,items=None):
        from .app import Gtk,GLib,button,label
        window,body,header=self.simple_window('One quick choice')
        meter=self.simple_review_meter(window)
        items=simple_store.review_items(self.store,day) if items is None else items;queue=list(items);done=[0]
        def clear():
            window.set_focus(None)
            while body.get_first_child():body.remove(body.get_first_child())
        def render():
            clear()
            if not queue:
                self.heading(body,'You’re done','Your saved categories are ready.')
                body.append(button('Back to my day',lambda _:(window.close(),self.show_page(self.page)),True));return
            item=queue[0];self.heading(body,'Choose once for this activity today')
            body.append(label(item['app'],'title-3'));body.append(label(f"{len(item['blocks'])+len(item.get('auto_entries',[]))} recorded periods · {compact(item['seconds'])} · {day:%d %b}",'dim-label'))
            body.append(label('This choice covers this app for the selected day, including later recorded use.','dim-label'))
            self.simple_expand(body,'See included periods','\n'.join(datetime.fromtimestamp(p['start']).strftime('%H:%M:%S')+'–'+datetime.fromtimestamp(p['end']).strftime('%H:%M:%S') for p in sorted(item['blocks']+item.get('auto_entries',[]),key=lambda p:p['start'])))
            body.append(label(f'{done[0]} answered · {len(queue)} activity types left','dim-label'))
            status=label('','dim-label')
            def answer(task):
                try:
                    from .daily_choices import choose
                    choose(self.store,item,task,remember=self.store.get('simple_remember','0')=='1')
                    meter.answer('answered')
                    queue.pop(0)
                except ValueError:meter.answer('stale');status.set_text('This activity changed. Close and reopen your choices to see the latest record.');return
                done[0]+=1;GLib.idle_add(lambda:(render() if window in self.dialogs else None,False)[1])
            for tid,name in self.simple_choices():body.append(button(name,lambda _,tid=tid:answer(tid)))
            def skip(_):
                try:simple_store.skip_item(self.store,item)
                except ValueError:status.set_text('This activity changed. Reopen the daily choice.');return
                queue.pop(0);GLib.idle_add(lambda:(render() if window in self.dialogs else None,False)[1])
                meter.answer('skipped')
            body.append(button('Leave uncategorised',skip));body.append(status)
        render();window.present()

    def simple_change(self,entry):
        from .app import button,label
        window,body,header=self.simple_window('Change category',height=480)
        meter=self.simple_review_meter(window,'correction')
        self.heading(body,'Choose the right category',datetime.fromtimestamp(entry['start']).strftime('%H:%M')+'–'+datetime.fromtimestamp(entry['end']).strftime('%H:%M'))
        status=label('','dim-label')
        def choose(task):
            try:simple_store.change_category(self.store,entry['id'],task,entry['revision'],remember=self.store.get('simple_remember','0')=='1')
            except ValueError as exc:status.set_text(str(exc));return
            meter.answer('answered');window.close();self.show_page(self.page);self.toast('Category changed · Undo is in Settings')
        for tid,name in self.simple_choices():body.append(button(name,lambda _,tid=tid:choose(tid)))
        body.append(status);window.present()

    def simple_export(self,day):
        from .app import button,label,GLib
        from .day_record import pdf
        from .pdf_export import write_pdf
        record=snapshot(self.store,day);window,body,header=self.simple_window('Save day record',height=560)
        self.heading(body,'Your day record',day.strftime('%A, %d %B'))
        body.append(label('App activity: '+duration(record['active'])))
        body.append(label('Uncategorised: '+compact(record['unclassified'])))
        body.append(label('Away / locked: '+duration(record['away'])+' · Capture gaps: '+duration(record['gaps'])))
        body.append(label('Includes categories, exact periods and app activity. AI estimates and your choices are labelled separately. Private titles and financial details are omitted.','dim-label'))
        status=label('','dim-label');body.append(status)
        def save(_):
            save_button.set_sensitive(False);status.set_text('Preparing your PDF…')
            def work():
                try:content=pdf(record);error=None
                except Exception:content=None;error='Could not create the PDF. Check PDF dependencies in Advanced tools.'
                def ready():
                    if window not in self.dialogs:return False
                    save_button.set_sensitive(True)
                    if error:status.set_text(error)
                    else:
                        status.set_text('Choose where to save your day record.')
                        self.save_file('Save day record','day-record-'+day.isoformat()+'.pdf',lambda path:write_pdf(path,content))
                    return False
                GLib.idle_add(ready)
            threading.Thread(target=work,daemon=True).start()
        save_button=button('Save PDF',save,True);body.append(save_button);window.present()

    def simple_ai_status(self):
        from .app import button,label
        window,body,header=self.simple_window('Jev status',height=480);repo=self.automation_repo();used=repo.usage()
        self.heading(body,'Jev needs attention',self.store.get('ai_pause_reason','No error reported.'))
        body.append(label(f"Today: {used['requests']} background requests",'dim-label'))
        def resume():repo.resume();desktop.start_automation();window.close();self.show_page(self.page)
        if used['unknown']:
            body.append(label('An interrupted request may have been charged. Its usage is unknown.','dim-label'))
            body.append(button('Acknowledge and resume',lambda _:self.run_action(lambda:(repo.acknowledge_unknown_usage(),resume()))))
        else:body.append(button('Try again',lambda _:self.run_action(resume),True))
        body.append(button('Reconnect my key',lambda _:(window.close(),self.simple_setup_wizard())))
        body.append(button('Keep recording without AI',lambda _:self.run_action(lambda:(repo.configure({**repo.config(),'mode':'off'}),window.close()))));window.present()

    def simple_settings(self):
        from .app import Gtk,button,label,__version__
        body=self.body_settings;self.clear(body);self.heading(body,'Settings','Keep the everyday flow simple.')
        show=Gtk.CheckButton(label='Show advanced tools in sidebar');show.set_active(self.store.get('simple_show_advanced','0')=='1')
        show.connect('toggled',lambda w:self.simple_sidebar(w.get_active()));body.append(show)
        body.append(button('Change my setup',lambda _:self.simple_setup_wizard(),True))
        body.append(button('Undo last change',lambda _:self.simple_undo()))
        repo=self.automation_repo();config=repo.config()
        if config['mode']!='off':body.append(button('Turn Jev off',lambda _:self.run_action(lambda:repo.configure({**config,'mode':'off'}))))
        body.append(button('Check for updates',lambda _:self.check_app_updates()))
        from .automation_status import summary_text
        self.simple_expand(body,'Jev activity and limits',summary_text(self.store))
        from .review_metrics import text as review_text
        self.simple_expand(body,'Review effort',review_text(self.store))
        self.simple_expand(body,'Privacy and data','Your app activity is recorded locally. Optional Jev sends only the context chosen in setup using your personal TypeSafe key. Pause stops capture; Turn Jev off stops future background requests. Already-sent requests cannot be recalled. Away, locked, excluded and capture gaps stay separate. Use Advanced tools for exclusions, retention and backup/restore.')
        self.simple_expand(body,'What does Jev do?','Jev sorts recorded activity into your selected categories, reuses equivalent decisions and uses correction examples you allowed it to remember. Ambiguous apps need your choice. Organise my day prioritises this for the selected day. App names alone cannot identify a client or distinguish work from personal browsing. Use local rules for known repeated assignments and project tools for deliberate task tracking. Jev does not approve bills or prove completed work.')
        self.simple_tool_choices(body,set(selected_tools(self.store)),lambda keys:save_tools(self.store,keys))
        self.local_automation_choices(body,{'local_types':self.store.get('local_app_types','0')=='1'},lambda enabled:self.store.set('local_app_types','1' if enabled else '0'))
        advanced=Gtk.Expander(label='Advanced tools');tools=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);advanced.set_child(tools);body.append(advanced)
        for name,target in [('Projects and tasks','Projects'),('Assignment rules','Rules'),('Invoices and client reports','Reports'),('All time entries','History')]:tools.append(button(name,lambda _,target=target:self.show_page(target)))
        tools.append(label('Projects group client work. Rules assign matching activity locally. History edits and approves entries. Reports export approved work and protect billed records. These tools use the same saved records as your day summary.','dim-label'))
        tools.append(button('Recording, privacy and backups',lambda _:self.simple_advanced_settings()))
        tools.append(button('Detailed Jev controls',lambda _:self.automation_dialog()))
        body.append(label('Time Sheet Linux '+__version__,'dim-label'))

    def simple_undo(self):
        from .app import button,label
        try:preview=self.store.undo_preview()
        except ValueError as exc:self.toast(str(exc));return
        window,body,_=self.simple_window('Undo last change',height=380)
        self.heading(body,preview['action'],f"{preview['entries']} saved entries affected")
        body.append(label('This restores the previous draft entries. It does not forget correction examples. Billed or subsequently edited entries stay protected.','dim-label'))
        def apply(_):
            def done(action):window.close();self.show_page(self.page);self.toast(action+' undone')
            self.run_action(lambda:self.store.undo(expected_change=preview['id']),done)
        body.append(button('Undo this change',apply,True));window.present()

    def simple_sidebar(self,show):
        self.store.set('simple_show_advanced','1' if show else '0')
        for name,control in self.nav.items():control.set_visible(show or name in ('Today','Calendar','Settings'))

    def simple_advanced_settings(self):
        # Preserve the existing backup/capture controls behind one explicit door.
        self.simple_settings_override=True
        try:self.refresh_settings()
        finally:self.simple_settings_override=False
