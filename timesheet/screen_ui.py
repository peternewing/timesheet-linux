"""Phone-style local insights and explicit personal/work context; no AI calls."""
from datetime import datetime,date
import threading
from . import screen_spaces


class ScreenTimeUI:
    def screen_space_dialog(self):
        from .app import Gtk,button,label
        window,body,_=self.simple_window('Personal and work spaces',height=430)
        current=screen_spaces.effective_now(self.store)
        self.heading(body,'Your space now',screen_spaces.SPACES[current['space']]+(' · scheduled' if current['source']=='schedule' else ''))
        def choose(space):
            def done(_):window.close();self.show_page(self.page);self.toast('Space: '+screen_spaces.SPACES[space])
            self.run_action(lambda:screen_spaces.switch(self.store,space),done)
        for key,name in screen_spaces.SPACES.items():body.append(button('Use '+name+' space',lambda _,key=key:choose(key),key==current['space']))
        change=self.store.db.execute('SELECT id FROM screen_space_changes WHERE undone=0 ORDER BY id DESC LIMIT 1').fetchone()
        if change:
            body.append(button('Undo last space change',lambda _:self.run_action(lambda:screen_spaces.undo_switch(self.store,change['id']),lambda _:(window.close(),self.show_page(self.page)))))
        automatic=Gtk.Expander(label='Automatic personal/work labels (optional)')
        options=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);automatic.set_child(options);body.append(automatic)
        def scheduled(key):
            self.run_action(lambda:screen_spaces.use_schedule(self.store,key),lambda _:(window.close(),self.show_page(self.page),self.toast('Local space schedule enabled')))
        for key,(name,_,_) in screen_spaces.SCHEDULES.items():options.append(button(name,lambda _,key=key:scheduled(key)))
        options.append(label('From now: weekdays in these hours are labelled Work; other recorded use is Personal. These are your schedule expectations, not inferred intent. A manual switch overrides the schedule until you choose a schedule again. Labels stay local and never approve time.','dim-label'))
        options.append(button('Clear local space labels',lambda _:self.confirm('Clear personal/work labels?','Captured activity and time entries stay saved. All local space labels, schedules and their undo history will be removed.',lambda:(screen_spaces.forget_labels(self.store),window.close(),self.show_page(self.page)))))
        self.simple_expand(body,'What does a space do?','A local label for recorded use from now on. It does not start a timer, hide personal activity, create work entries or approve billing. Space labels are not sent to Jev. Unsorted is fine; screen time still works.')
        window.present()

    def screen_label_period(self,start,end):
        from .app import button,label
        window,body,_=self.simple_window('Label recorded period',height=420)
        expected=screen_spaces.revision(self.store)
        self.heading(body,'Personal, work or unsorted?',datetime.fromtimestamp(start).astimezone().strftime('%d %b %H:%M %Z')+' – '+datetime.fromtimestamp(end).astimezone().strftime('%H:%M %Z'))
        body.append(label('Changes only local space labels for this period. Capture, activity categories, current space and billing remain separate.','dim-label'))
        def choose(space):
            self.run_action(lambda:screen_spaces.label_period(self.store,start,end,space,expected_revision=expected),lambda _:(window.close(),self.toast('Recorded period labelled · Undo in Personal / work spaces')))
        for key,name in screen_spaces.SPACES.items():body.append(button(name,lambda _,key=key:choose(key)))
        window.present()

    def screen_insights(self,day=None,space='all'):
        from .app import Gtk,GLib,button,label
        from .simple_ui import compact
        day=day or datetime.now().date()
        if isinstance(day,str):day=date.fromisoformat(day)
        window,body,header=self.simple_window('Screen-time insights',width=680,height=720)
        state={'space':space,'hourly':False,'details':False,'meaning':False,'version':None,'loading':False,'refresh_id':None}
        cancel=threading.Event()
        def closed(*_):
            cancel.set()
            if state['refresh_id'] is not None:GLib.source_remove(state['refresh_id']);state['refresh_id']=None
        window.connect('close-request',closed)
        spinner=Gtk.Spinner(tooltip_text='Updating local screen time',visible=False);spinner.update_property([Gtk.AccessibleProperty.LABEL],['Updating screen time']);header.pack_start(spinner)
        self.heading(body,'Your last seven days');body.append(label('Loading local screen time…','dim-label'))
        def render(week,now,selected_space):
            if window not in self.dialogs:return
            focus=window.get_focus();focus_label=focus.get_label() if isinstance(focus,Gtk.Button) else None
            adjustment=body.get_parent().get_vadjustment();scroll_value=adjustment.get_value()
            window.set_focus(None)
            while body.get_first_child():body.remove(body.get_first_child())
            today=week['days'][-1]
            self.heading(body,'Your last seven days',f"{week['days'][0]['day']} – {day.isoformat()}")
            filters=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,min_children_per_line=2,max_children_per_line=4,column_spacing=8,row_spacing=8);body.append(filters)
            group=None
            for key,name in [('all','Everything'),*screen_spaces.SPACES.items()]:
                control=Gtk.ToggleButton(label=name)
                if group is not None:control.set_group(group)
                else:group=control
                control.set_active(key==selected_space)
                control.update_property([Gtk.AccessibleProperty.LABEL],['Show '+name+' screen time'])
                if control.get_active():control.add_css_class('suggested-action')
                def select(widget,key=key):
                    if widget.get_active():
                        widget.add_css_class('suggested-action');state['space']=key
                        if state.get('export') is not None:state['export'].set_sensitive(False)
                        GLib.idle_add(lambda:(request(),False)[1])
                    else:widget.remove_css_class('suggested-action')
                control.connect('toggled',select)
                filters.append(control)
            body.append(label(compact(week['total'])+' recorded screen time','title-1'))
            if any(d['legacy_exclusions'] for d in week['days']):body.append(label('Some older excluded observations may include idle or locked time. New capture separates them; original observations stay preserved.','dim-label'))
            body.append(label(f"{week['recorded_days']} recorded "+('day' if week['recorded_days']==1 else 'days')+' · '+(compact(week['average'])+' average per recorded day' if week['average'] is not None else 'No recording yet'),'dim-label'))
            if week['change_fraction'] is not None:
                change=week['change_fraction'];body.append(label(f"{abs(change)*100:.0f}% "+('more' if change>=0 else 'less')+' recorded use than the previous seven recorded days','dim-label'))
            body.append(label('Daily screen time','title-3'));maximum=max([d['screen_seconds'] for d in week['days']]+[1])
            for value in week['days']:
                target=date.fromisoformat(value['day'])
                def open_day(target=target):window.close();self.day=target;self.show_page('Today' if target==datetime.now().date() else 'Calendar')
                row=Gtk.Box(spacing=10);body.append(row);row.append(button(target.strftime('%a %d %b'),lambda _,target=target:open_day(target)))
                bar=Gtk.ProgressBar(fraction=value['screen_seconds']/maximum,hexpand=True,valign=Gtk.Align.CENTER)
                bar.update_property([Gtk.AccessibleProperty.LABEL],[target.isoformat()+' recorded screen time']);row.append(bar)
                row.append(label(compact(value['screen_seconds']) if value['has_observations'] else 'No recording','dim-label'))
            body.append(label('Top apps across these days','title-3'))
            if not week['apps']:body.append(label('App names appear when active use is recorded. Private app names stay hidden.','dim-label'))
            for name,seconds in week['apps'][:10]:
                row=Gtk.Box(spacing=12);app_name=label(name);app_name.set_hexpand(True)
                row.append(app_name);row.append(label(compact(seconds),'dim-label'));body.append(row)
            details=self.simple_expand(body,'Selected day details',f"{today['sessions']} recorded sessions · {today['switches']} app switches\nLongest continuous use: {compact(today['longest_session'])}\nPrivate recorded use: {compact(today['private_seconds'])}\nSchedule-labelled use: {compact(today['scheduled_seconds'])}\nAway / locked: {compact(today['away_seconds'])} · Capture gaps: {compact(today['gap_seconds'])}")
            details.set_expanded(state['details']);details.connect('notify::expanded',lambda w,*_:state.update(details=w.get_expanded()))
            hourly=Gtk.Expander(label='By hour for '+day.strftime('%d %b'));hourly.set_expanded(state['hourly']);hourly.connect('notify::expanded',lambda w,*_:state.update(hourly=w.get_expanded()));hours=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);hourly.set_child(hours);body.append(hourly)
            for hour in today['hourly']:
                row=Gtk.Box(spacing=10);label_hour=button(hour['label'],lambda _,hour=hour:self.screen_label_period(hour['start'],hour['end']));label_hour.update_property([Gtk.AccessibleProperty.LABEL],['Change personal/work label for '+hour['label']]);row.append(label_hour);bar=Gtk.ProgressBar(fraction=hour['seconds']/max(1,hour['end']-hour['start']),hexpand=True,valign=Gtk.Align.CENTER);bar.update_property([Gtk.AccessibleProperty.LABEL],[hour['label']+' screen time']);row.append(bar);row.append(label(compact(hour['seconds']),'dim-label'));hours.append(row)
            actions=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,min_children_per_line=1,max_children_per_line=2,column_spacing=8,row_spacing=8);body.append(actions)
            actions.append(button('Refresh insights',lambda _:GLib.idle_add(lambda:(request(),False)[1])));actions.append(button('Personal / work spaces',lambda _:self.screen_space_dialog()))
            export_control=button('Save screen-time summary',lambda _,space=selected_space:self.screen_export(week,space));state['export']=export_control;actions.append(export_control)
            meaning=self.simple_expand(body,'What these numbers mean','Only observed foreground use counts, including private use without its app name. Away, locked and missing capture are separate. No recorded day means no evidence, not zero computer use. Personal/Work labels come from your choices or local schedule expectations; categories and invoices do not decide your intent. These totals describe computer use, not productivity or completed output.')
            meaning.set_expanded(state['meaning']);meaning.connect('notify::expanded',lambda w,*_:state.update(meaning=w.get_expanded()))
            body.append(label('Updated '+datetime.fromtimestamp(now).strftime('%H:%M:%S'),'dim-label'))
            if focus_label:
                def restore(widget):
                    if isinstance(widget,Gtk.Button) and widget.get_label()==focus_label:widget.grab_focus();return True
                    child=widget.get_first_child()
                    while child:
                        if restore(child):return True
                        child=child.get_next_sibling()
                    return False
                restore(body)
            GLib.idle_add(lambda:(adjustment.set_value(scroll_value) if window in self.dialogs else None,False)[1])
        def request():
            if window not in self.dialogs or state['loading']:return
            state['loading']=True;spinner.set_visible(True);spinner.start()
            if state.get('export') is not None:state['export'].set_sensitive(False)
            now=int(datetime.now().timestamp());selected_space=state['space'];version=(screen_spaces.revision(self.store),now//30);path=self.store.path
            def finished(value,error):
                state['loading']=False
                if window not in self.dialogs:return False
                spinner.stop();spinner.set_visible(False)
                if error:
                    state['version']=version
                    if state.get('error') is None:
                        state['error']=label('Could not load the local summary. Close and reopen insights to retry.','dim-label');body.append(state['error'])
                    return False
                if selected_space!=state['space'] or version[0]!=screen_spaces.revision(self.store):request();return False
                if value is not None:
                    state['error']=None;render(value,now,selected_space);state['version']=version
                return False
            def load():
                from .screen_reader import load_week
                try:value=load_week(path,day,now,selected_space,cancel);error=False
                except Exception:value=None;error=True
                GLib.idle_add(finished,value,error)
            threading.Thread(target=load,daemon=True,name='screen-time-reader').start()
        def refresh():
            if window not in self.dialogs:return False
            if self.dialogs[-1]==window and state['version']!=(screen_spaces.revision(self.store),int(datetime.now().timestamp())//30):request()
            return True
        request();state['refresh_id']=GLib.timeout_add_seconds(1,refresh);window.present();return window

    def screen_export(self,week,space):
        from .app import Gtk,GLib
        from .screen_export import csv_bytes,write_summary
        chooser=Gtk.FileDialog(title='Save screen-time summary',initial_name=f"screen-time-{week['days'][-1]['day']}.csv")
        def saved(dialog,result):
            try:
                destination=dialog.save_finish(result)
                if destination:
                    write_summary(destination.get_path(),csv_bytes(week,space));self.toast('Screen-time summary saved')
            except GLib.Error:pass
            except (ValueError,OSError):self.info('Could not save summary','Choose a writable destination and try again.')
        chooser.save(self.dialogs[-1] if self.dialogs else self.win,None,saved)
