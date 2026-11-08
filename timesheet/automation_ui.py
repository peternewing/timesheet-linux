"""Automation setup and exception review, separate from the tracking/billing UI."""
from __future__ import annotations
import json
import os
import time
from datetime import datetime,timedelta
from .automation_store import Repository
from .decision_context import canonical
from .decision_policy import POLICY_VERSION,owner_token


def wrapped_check(text):
    from .app import Gtk,Pango
    control=Gtk.CheckButton(label=text)
    def wrap_children(widget):
        child=widget.get_first_child()
        while child:
            if isinstance(child,Gtk.Label):child.set_wrap(True);child.set_wrap_mode(Pango.WrapMode.WORD_CHAR);child.set_max_width_chars(50)
            else:wrap_children(child)
            child=child.get_next_sibling()
    wrap_children(control)
    return control


class AutomationUI:
    def automation_repo(self):return Repository(self.store)

    def automation_escape(self,window):
        from .app import Gtk,Gdk
        keys=Gtk.EventControllerKey()
        def pressed(_,key,*args):
            if key==Gdk.KEY_Escape:window.close();return True
            return False
        keys.connect('key-pressed',pressed);window.add_controller(keys)

    def automation_summary(self,box):
        from .app import day_bounds
        repo=self.automation_repo();config=repo.config()
        if config['mode']!='off' and (config['backend']!=('flatpak' if os.environ.get('FLATPAK_ID') else 'native') or config['owner']!=owner_token()):
            self.row(box,'Jev is configured in another app installation','Only the native or Flatpak build that you authorised runs its background decisions. Set up this build explicitly to switch.',[('Set up Jev automation',lambda _:self.automation_dialog())]);return
        if config['mode']=='off':
            self.row(box,'Let Jev organise your day','Optional: prepare suggestions or automatically save supported work as drafts. Start with your own key and choose what may be sent.',
                     [('Set up Jev automation',lambda _:self.automation_dialog())]);return
        start,end=day_bounds(datetime.now().date())
        counts=self.store.db.execute("SELECT SUM(state='exception') decisions,SUM(state='failed') failed,SUM(state='pending' OR state='running') pending FROM ai_jobs WHERE start<? AND end>?",(end,start)).fetchone()
        assigned=self.store.db.execute("SELECT COALESCE(SUM(MIN(end,?)-MAX(start,?)),0) FROM entries WHERE deleted=0 AND origin='jev' AND start<? AND end>?",(end,start,end,start)).fetchone()[0]
        from .app import fmt_duration
        reason=self.store.get('ai_pause_reason','')
        mode='Automatic drafts' if config['mode']=='automatic' else 'Preparing suggestions'
        focus=repo.current_focus()
        focus_name=dict(self.task_choices()).get(focus['task_id']) if focus else None
        detail=f"{mode} · {fmt_duration(assigned)} automatically organised today · {counts['decisions'] or 0} decisions · {counts['pending'] or 0} queued"
        if focus_name:detail+='\nFocus: '+focus_name+' · until '+datetime.fromtimestamp(focus['end']).strftime('%H:%M')
        if reason:detail+='\nPaused: '+reason
        elif int(self.store.get('ai_worker_seen','0') or 0)<time.time()-30:detail+='\nBackground worker has not checked in recently. Open setup to resume it.'
        self.row(box,'Jev is organising your day',detail,[('Needs your decisions',lambda _:self.automation_inbox()),('Choose focus',lambda _:self.focus_dialog()),('Automation settings',lambda _:self.automation_dialog()),('Undo last edit',lambda _:self.run_action(self.store.undo,lambda action:self.toast(action+' undone')))])

    def show_ai_text(self,title,text):
        from .app import Adw,Gtk,margins,button
        window=Adw.Window(title=title,transient_for=self.dialogs[-1] if self.dialogs else self.win,modal=True,default_width=750,default_height=600)
        self.dialogs.append(window);self.dialog_count=len(self.dialogs)
        self.automation_escape(window)
        window.connect('close-request',lambda *_:self.dialog_closed(window))
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);window.set_content(outer)
        header=Adw.HeaderBar();header.pack_end(button('Close',lambda _:window.close()));outer.append(header)
        textview=Gtk.TextView(editable=False,cursor_visible=True,wrap_mode=Gtk.WrapMode.WORD_CHAR,monospace=True)
        textview.update_property([Gtk.AccessibleProperty.LABEL],[title]);textview.get_buffer().set_text(str(text))
        scroll=Gtk.ScrolledWindow(vexpand=True);scroll.set_child(margins(textview,16));outer.append(scroll);window.present()

    def focus_dialog(self,task_id=None):
        from .app import dropdown,selected,select_id,label,button,desktop
        choices=self.task_choices()
        if not choices:self.quick_setup(after=lambda:self.focus_dialog(task_id));return
        repo=self.automation_repo()
        def build(box):
            box.append(label('Tell Jev your intended task for the next period. This is context, not a timer: it creates no time by itself and does not prove all app use is work. Under an enabled automation policy, the selected task ID can be sent with later completed activity.'))
            task=dropdown(box,'My intended focus',[(None,'Choose a task…')]+choices);select_id(task,task_id)
            duration=dropdown(box,'Use this context for',[(15,'15 minutes'),(30,'30 minutes'),(60,'1 hour'),(120,'2 hours'),(240,'4 hours')]);select_id(duration,60)
            box.append(button('Clear current focus',lambda _:self.run_action(repo.clear_focus,lambda _:(self.dialogs[-1].close(),self.toast('Focus cleared for future activity')))))
            default=wrapped_check('Use this task as my draft default when Jev agrees; leave conflicting activity for review');box.append(default)
            box.append(label('This optional instruction applies only to recorded active use during the chosen period. It never fills gaps or approves time. Leave it off to provide context only.','dim-label'))
            return task,duration,default
        def save(fields):
            repo.set_focus(selected(fields[0]),selected(fields[1]),draft_default=fields[2].get_active());desktop.start_automation();self.toast('Focus context saved; recording and gaps remain unchanged')
        self.dialog('Choose Jev focus',build,save)

    def task_guidance_dialog(self,task_id=None):
        from .app import dropdown,field,label,selected,select_id
        choices=self.task_choices()
        if not choices:self.quick_setup(after=lambda:self.task_guidance_dialog(task_id));return
        repo=self.automation_repo()
        def build(box):
            box.append(label('Describe what belongs to this task and how it differs from other tasks. Keep it brief and exclude credentials, private document text and sensitive details. Guidance is local until you allow it in outgoing requests.'))
            task=dropdown(box,'Task',choices);select_id(task,task_id)
            guidance=field(box,'What belongs here? (up to 250 characters)','','e.g. Acme Falcon implementation and testing; excludes marketing work')
            def load(*_):
                row=self.store.db.execute('SELECT guidance FROM ai_task_profiles WHERE task_id=?',(selected(task),)).fetchone()
                guidance.set_text(row['guidance'] if row else '')
            warning=label('','dim-label');box.append(warning)
            def hints(*_):warning.set_text('\n'.join(repo.profile_warnings(selected(task),guidance.get_text())))
            guidance.connect('changed',hints)
            task.connect('notify::selected',load);load();hints()
            return task,guidance
        self.dialog('Describe work for Jev',build,lambda fields:repo.save_profile(selected(fields[0]),fields[1].get_text()))

    def automation_dialog(self):
        from .app import Gtk,button,label,field,dropdown,selected,select_id,action_bar,day_bounds,desktop
        from . import jev
        repo=self.automation_repo();config=repo.config();now=int(time.time())
        def build(box):
            box.append(label('Jev can organise completed work while you use other apps. Recording stays local and continues if Jev is unavailable. Automatic decisions create reversible drafts only.'))
            if desktop.FLATPAK:box.append(label('Flatpak automation runs in this app’s sandbox. Some desktops restrict apps after their windows close; keep the app open for continuous Jev processing until background permission is verified on your desktop. Host recording is independent.','dim-label'))
            box.append(label('After setup, choose a focus on Today. You can explicitly make it a draft default when Jev agrees, or provide context only. Without distinguishing context, Jev leaves a decision for you.','dim-label'))
            box.append(button('Describe my tasks',lambda _:self.task_guidance_dialog()))
            tools=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
            tools.append(button('Review decisions',lambda _:self.automation_inbox()))
            tools.append(button('Forget remembered corrections',lambda _:self.confirm('Forget correction examples?','Existing time entries remain unchanged. Future decisions will stop using remembered correction examples.',repo.forget_examples)))
            tools.append(button('Use current Jev model',lambda _:self.confirm('Reset the pinned model?', 'Cached responses will be cleared and automation switches to suggestion-only mode. Check results before enabling automatic drafts again.',repo.reset_model)))
            key=field(box,'TypeSafe key (leave blank to keep your saved key)');key.set_visibility(False);key.set_input_purpose(Gtk.InputPurpose.PASSWORD)
            mode=dropdown(box,'How should Jev help?',[('off','Off — keep manual review'),('suggest','Prepare suggestions in the background'),('automatic','Organise automatically as drafts (experimental)')]);select_id(mode,config['mode'])
            today=day_bounds(datetime.now().date())[0]
            values=[(today,'Today and future completed activity'),(None,'Only activity recorded after I save this setup'),(today-6*86400,'Past seven days and future completed activity')]
            if config['since'] and config['since'] not in [v for v,_ in values]:values.append((config['since'],'Keep existing processing start'))
            since=dropdown(box,'What period may be processed?',values);select_id(since,config['since'] or today)
            guidance=wrapped_check('Include my task guidance with task names');guidance.set_active(config['allow_guidance']);box.append(guidance)
            examples=wrapped_check('Include relevant corrections I explicitly remembered');examples.set_active(config['allow_examples']);box.append(examples)
            clues=wrapped_check('Match project words locally in recorded titles; send task IDs and match counts only')
            clues.set_sensitive(self.store.get('capture_titles','0')=='1');clues.set_active(config['allow_project_clues'] and clues.get_sensitive());box.append(clues)
            box.append(label('Background automation does not add raw titles, paths, timestamps, rates or entry descriptions. Guidance includes text you deliberately enter, so review it for sensitive details. Local title matching needs title collection enabled. A focus task provides intent without collecting titles.','dim-label'))
            requests=dropdown(box,'Daily maximum background requests',[(n,str(n)) for n in sorted({10,50,200,config['daily_requests']})]);select_id(requests,config['daily_requests'])
            tokens=dropdown(box,'Pause background requests after reported daily input tokens',[(n,f'{n:,}') for n in sorted({50000,250000,1000000,config['daily_tokens']})]);select_id(tokens,config['daily_tokens'])
            box.append(label('The request cap is strict. Reported token usage can cross its limit by one request. Unknown usage pauses sending until you acknowledge it. Your own TypeSafe account is charged. These draft thresholds are conservative heuristics, not measured accuracy.','dim-label'))
            excluded=field(box,'Never send these apps (comma-separated exact names)',', '.join(config['exclude_apps']))
            consent=wrapped_check('Allow background requests under this data and usage policy')
            consent.set_active(config['mode']!='off');box.append(consent)
            box.append(label('Requests go to api.typesafe.ai and include app names, active client/project/task names, and your explicitly chosen focus task, and only the extra context selected above. Standard provider retention has no fixed published duration; processing is in the US. ZDR is available by request from TypeSafe. Saving a key alone does not enable automation.','dim-label'))
            consent.set_tooltip_text('Turning this off and saving pauses new background requests. An in-flight request may already have been sent.')
            def preview(_):
                rows=self.store.rows("SELECT * FROM activity WHERE state='active' AND closed=1 AND start>=? ORDER BY end DESC LIMIT 1",(selected(since) if selected(since) is not None else int(time.time()),))
                if not rows:self.info('No completed activity yet','Record some application usage, then return to preview the next decision.');return
                candidate={**config,'allow_guidance':guidance.get_active(),'allow_examples':examples.get_active(),'allow_project_clues':clues.get_active(),'exclude_apps':[s.strip() for s in excluded.get_text().split(',') if s.strip()]}
                context,reason=repo.context(rows[0],candidate)
                if not context:self.info('No permitted request',reason);return
                network=context['network']
                payload=jev.prepare_decision(network['applications'],network['tasks'],examples=network['examples'],clues=network['clues'],focus=network.get('focus'),focus_default=network.get('focus_default',False),model=self.store.get('ai_pinned_model','jev-latest'))
                self.show_ai_text('Exact next-request data preview',json.dumps(payload,ensure_ascii=False,indent=2))
            tools.append(button('Preview permitted data',preview))
            tools.append(Gtk.LinkButton(uri='https://help.typesafe.ai/articles/5974925716',label='TypeSafe data handling'))
            advanced=Gtk.Expander(label='Advanced: model, stored examples and data preview');advanced.set_child(tools);box.append(advanced)
            return key,mode,since,guidance,examples,clues,requests,tokens,excluded,consent
        def save(fields):
            key,mode,since,guidance,examples,clues,requests,tokens,excluded,consent=fields
            chosen=selected(mode)
            if chosen!='off' and not consent.get_active():raise ValueError('Accept the background data policy, or choose Off.')
            if key.get_text().strip():jev.save_key(key.get_text());key.set_text('')
            repo.configure(dict(mode=chosen,consent_version=POLICY_VERSION if consent.get_active() else 0,since=selected(since) if selected(since) is not None else int(time.time()),
                backend='flatpak' if desktop.FLATPAK else 'native',
                owner=owner_token(),
                allow_guidance=guidance.get_active(),allow_examples=examples.get_active(),allow_project_clues=clues.get_active(),allow_focus=True,
                daily_requests=selected(requests),daily_tokens=selected(tokens),exclude_apps=[s.strip() for s in excluded.get_text().split(',') if s.strip()]))
            if chosen!='off':desktop.start_automation()
            self.toast('Jev automation settings saved')
        self.dialog('Set up Jev automation',build,save)
        self.dialogs[-1].set_default_size(720,760)

    def automation_inbox(self):
        from .app import Adw,Gtk,button,label,margins,append_in_batches,fmt_duration,fmt_time,dropdown,selected,desktop
        repo=self.automation_repo()
        window=Adw.Window(title='Jev decisions',transient_for=self.dialogs[-1] if self.dialogs else self.win,modal=True,default_width=800,default_height=720)
        self.dialogs.append(window);self.dialog_count=len(self.dialogs);window.connect('close-request',lambda *_:self.dialog_closed(window))
        self.automation_escape(window)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);window.set_content(outer);header=Adw.HeaderBar();outer.append(header);header.pack_end(button('Close',lambda _:window.close()))
        scroll=Gtk.ScrolledWindow(vexpand=True);outer.append(scroll);body=margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12),20);scroll.set_child(body)
        self.heading(body,'Only the decisions that need you','Choose a task once. Clear cases can be organised automatically; nothing is approved or billed by Jev.')
        used=repo.usage();body.append(label(f"Today’s background usage: {used['requests']} requests · {used['tokens']:,} reported input tokens · {used['unknown']} unknown-usage requests",'dim-label'))
        reason=self.store.get('ai_pause_reason','')
        if reason:body.append(label('Paused: '+reason))
        def refresh():window.close();self.automation_inbox();self.refresh_after_action()
        def resume(_):
            repo.resume();desktop.start_automation();self.toast('Automation will check again');refresh()
        header.pack_start(button('Resume',resume))
        if used['unknown']:
            body.append(button('Review unknown usage',lambda _:self.confirm('Resume with unknown usage?',
                'Some requests may have reached TypeSafe. Their tokens are unknown and may have incurred charges. This keeps their history and request count, and allows future requests within your limits.',
                lambda:(repo.acknowledge_unknown_usage(),desktop.start_automation(),refresh()))))
        from .app import day_bounds
        start,end=day_bounds(datetime.now().date());progress=repo.progress(start,end)
        metrics=Gtk.Expander(label='How automation is helping today')
        metrics.set_child(label(f"{progress['automatic_entries']} current Jev entries · {fmt_duration(progress['automatic_seconds'])} automatically organised.\n{progress['reviewed_exceptions']} exceptions reviewed · {progress['suggestions_kept']} suggestions kept.\nThese are local workflow counts. Exception reviews are selective and do not establish automatic accuracy. Use a representative labelled evaluation before relying on new patterns.",'dim-label'));body.append(metrics)
        rows=repo.review_rows()
        if len(rows)==1000:body.append(label('Showing the newest 1,000 decisions. Older items appear as these are resolved. All original activity remains in Calendar.','dim-label'))
        active=dict(self.task_choices())
        if not rows:body.append(label('No decisions waiting. Your day may be organised, still recording, or queued for processing.','dim-label'))
        def render(target,job):
            network=json.loads(job['network']);result=json.loads(job['decision']);app=network['applications'][0]
            card=self.row(target,f"{app} · {fmt_time(job['start'])} · {fmt_duration(job['end']-job['start'])}",job['reason'])
            card.append(button('Why this decision?',lambda _:self.show_ai_text('Decision evidence and policy',json.dumps(dict(permitted_context=network,decision=result,reason=job['reason'],model=result.get('model'),policy_version=1),ensure_ascii=False,indent=2))))
            if job['state']=='failed':
                def retry(_):
                    if repo.usage()['unknown']:self.info('Review usage first','Acknowledge unknown usage before retrying a request.');return
                    if not repo.fresh(job):self.info('Activity changed','This request is stale. Background discovery will reconsider permitted unassigned activity.');return
                    with self.store.db:self.store.db.execute("UPDATE ai_jobs SET state='pending',due=0,attempts=0 WHERE id=?",(job['id'],))
                    self.store.set('ai_pause_reason','');desktop.start_automation();refresh()
                card.append(button('Retry this request',retry));return
            def choose(task):
                peers=repo.matching_scope(job)
                def build(box):
                    choice=dropdown(box,'Put this work on',[(None,'Choose a task…')]+list(active.items()))
                    if task is not None:
                        from .app import select_id
                        select_id(choice,task)
                    remember=wrapped_check('Remember my choice as a local correction example');box.append(remember)
                    similar=wrapped_check(f"Apply to these {len(peers)} matching periods ({fmt_duration(sum(r['end']-r['start'] for r in peers))})")
                    similar.set_sensitive(len(peers)>1);box.append(similar)
                    if len(peers)>1:
                        box.append(label('These nearby periods have the same permitted context and task options. Check the exact scope below; other days and later arrivals are excluded.','dim-label'))
                        box.append(label('\n'.join(f"{fmt_time(p['start'])} – {datetime.fromtimestamp(p['end']):%H:%M} · {fmt_duration(p['end']-p['start'])}" for p in peers),'dim-label'))
                    return choice,remember,similar
                def save(fields):
                    choice,remember,similar=fields
                    repo.correct(job['id'],selected(choice),remember=remember.get_active(),job_ids=[p['id'] for p in peers] if similar.get_active() else None)
                    from .app import GLib
                    GLib.idle_add(lambda:(refresh(),False)[1])
                self.dialog('Resolve Jev decision',build,save)
            options=result.get('alternatives',[])
            for task,_ in options[:2]:
                if task in active:card.append(button(active[task],lambda _,task=task:choose(task)))
            card.append(button('Choose another task',lambda _:choose(None)))
            card.append(button('Leave for manual review',lambda _:self.run_action(lambda:repo.dismiss(job['id']),lambda _:refresh())))
        append_in_batches(body,rows,render,size=25)
        window.present()

    def check_app_updates(self):
        """Read-only public metadata check, off the GTK thread."""
        import threading
        from . import __version__,updates
        from .app import GLib
        self.toast('Checking public GitHub releases…')
        def work():
            try:
                result=updates.check(__version__)
                text=('A newer release is available: ' if result['newer'] else 'Latest complete release: ')+result['version']
                text+='\nInstalled: '+__version__+'\n\n'+result['url']
                text+='\n\n'+('A provenance bundle is listed; verify the downloaded binary with packaging/verify_release.py before installing.' if result['provenance'] else 'This release lists checksums but no provenance bundle. Check its release notes before installing.')
                text+='\n\nThis check downloaded no installer and sent no activity or credentials.'
            except ValueError as exc:text=str(exc)+'\nhttps://github.com/peternewing/timesheet-linux/releases'
            def done():
                if self.win is not None:self.show_ai_text('App update information',text)
                return False
            GLib.idle_add(done)
        threading.Thread(target=work,daemon=True).start()

    def entry_decision(self,entry_id):
        entry=self.store.db.execute('SELECT * FROM entries WHERE id=? AND deleted=0',(entry_id,)).fetchone()
        if entry:
            for job in self.store.rows('SELECT * FROM ai_jobs WHERE activity_id=? ORDER BY id DESC LIMIT 100',(entry['activity_id'],)):
                try:ids=json.loads(job['entry_ids'])
                except (ValueError,TypeError):continue
                if entry_id in ids:
                    self.show_ai_text('Why Jev chose this task',json.dumps(dict(reason=job['reason'],permitted_context=json.loads(job['network']),decision=json.loads(job['decision']),policy_version=1),ensure_ascii=False,indent=2));return
        self.info('Decision history','No detailed decision record is available. Source context may have been removed by retention or an earlier edit.')
