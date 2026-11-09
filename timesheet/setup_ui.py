"""Four-step click-only setup, separated from daily rendering and review."""
import threading
from . import desktop
from .simple_setup import BUCKETS,TOOLS,preset_ids,finish_setup,selected_tools


class SetupUI:
    def local_automation_choices(self,body,state,changed=None):
        from .app import Gtk,label
        from .automation_ui import wrapped_check
        expander=Gtk.Expander(label='Local automation (optional)');box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);expander.set_child(box);body.append(expander)
        control=wrapped_check('Use installed app categories locally');control.set_active(state['local_types'])
        def toggle(widget):
            state['local_types']=widget.get_active()
            if changed:changed(widget.get_active())
        control.connect('toggled',toggle);box.append(control)
        box.append(label('Clear installed app types can become reversible, non-billable category drafts without an AI request. Jev handles remaining apps when connected. App types do not establish purpose, productivity or client work. Nothing from desktop metadata is sent.','dim-label'))
        return expander

    def simple_setup_wizard(self):
        from .app import Gtk,GLib,button,label,margins
        from . import jev
        window,body,header=self.simple_window('Make your day automatic')
        current=self.automation_repo().config()
        chosen=set(BUCKETS);tool_choices=set(selected_tools(self.store))
        state=dict(step=0,titles=self.store.get('capture_titles','0')=='1',connected=False,remember=current['allow_examples'] if self.store.get('simple_setup_complete','0')=='1' else True,busy=False,closed=False,
            local_types=self.store.get('local_app_types','0' if self.store.get('simple_setup_complete','0')=='1' else '1')=='1')
        known=preset_ids(self.store)
        if current.get('category_tasks'):chosen={k for k,v in known.items() if v in current['category_tasks']} or set(BUCKETS)
        window.connect('close-request',lambda *_:state.update(closed=True))
        def clear():
            window.set_focus(None)
            child=body.get_first_child()
            while child:following=child.get_next_sibling();body.remove(child);child=following
        def schedule_render():
            GLib.idle_add(lambda:(render() if not state['closed'] else None,False)[1])
        def next_step():state['step']+=1;schedule_render()
        def connect_key(pasted=False):
            if state['busy']:return
            def run(text=None):
                state['busy']=True;connect_button.set_sensitive(False);paste_button.set_sensitive(False);skip_button.set_sensitive(False);status.set_text('Connecting…')
                def work():
                    error=None
                    try:
                        key=text.strip() if isinstance(text,str) else jev.get_key()
                        jev.check_connection(key)
                        if pasted:jev.save_key(key)
                    except Exception as exc:error=str(exc) if isinstance(exc,jev.JevError) else 'Could not connect. Unlock your keyring or use Paste key.'
                    finally:key=None
                    def done():
                        state['busy']=False
                        if state['closed']:return False
                        connect_button.set_sensitive(True);paste_button.set_sensitive(True);skip_button.set_sensitive(True)
                        if error:status.set_text(error)
                        else:state['connected']=True;next_step()
                        return False
                    GLib.idle_add(done)
                threading.Thread(target=work,daemon=True).start()
            if pasted:
                def clipboard_ready(clipboard,result):
                    try:text=clipboard.read_text_finish(result)
                    except Exception:text=None
                    if not state['closed']:run(text if isinstance(text,str) else '')
                window.get_display().get_clipboard().read_text_async(None,clipboard_ready)
            else:run()
        def render():
            nonlocal connect_button,paste_button,skip_button,status
            clear();step=state['step'];body.append(label(f'Step {step+1} of 4','dim-label'))
            progress=Gtk.ProgressBar(fraction=(step+1)/4);body.append(progress)
            if step:
                def back(_):
                    if not state['busy']:state['step']-=1;schedule_render()
                body.append(button('Back',back))
            if step==0:
                self.heading(body,'What fills your screen time?','Personal, work or both. Pick ready-made activity types.')
                for key,(name,_) in BUCKETS.items():
                    check=Gtk.CheckButton(label=name);check.set_active(key in chosen)
                    check.connect('toggled',lambda w,key=key:chosen.add(key) if w.get_active() else chosen.discard(key));body.append(check)
                status=label('','dim-label');body.append(status)
                def proceed(_):
                    if not chosen:status.set_text('Choose at least one category.');return
                    next_step()
                body.append(button('Next',proceed,True))
            elif step==1:
                self.heading(body,'Choose what gets recorded','Your activity stays on this computer. Jev receives only the allowed clues.')
                def choose(titles):state['titles']=titles;next_step()
                body.append(button('App names only',lambda _:choose(False),True))
                body.append(button('App names + local title clues',lambda _:choose(True)))
                self.simple_expand(body,'What is the difference?','App names only is the simplest choice. The other option also stores window titles locally and sends only category IDs and word-match counts to Jev. Raw titles, paths, document text and screenshots are not sent automatically.')
            elif step==2:
                self.heading(body,'Connect Jev','Use your own TypeSafe account. Your key stays in secure storage.')
                connect_button=button('Use my saved key',lambda _:connect_key(),True);body.append(connect_button)
                paste_button=button('Paste key and connect',lambda _:connect_key(True));body.append(paste_button)
                skip_button=button('Continue without AI',lambda _:(state.update(connected=False),next_step()));body.append(skip_button)
                status=label('','dim-label');body.append(status)
                self.simple_expand(body,'No saved key?','Copy your API key from your TypeSafe account, then click Paste key and connect. You do not need to type it here. Connecting checks the key; it does not send recorded activity or enable background requests.')
            else:
                self.heading(body,'You’re ready','Use your computer. Your screen time will appear here.')
                body.append(label('✓ Record screen time for personal and work use'))
                body.append(label('✓ Jev organises clear activity automatically' if state['connected'] else '✓ Keep a local activity record'))
                body.append(label('✓ Choose a category only when needed'))
                remember=Gtk.CheckButton(label='Remember my choices for similar activity');remember.set_active(state['remember']);remember.connect('toggled',lambda w:state.update(remember=w.get_active()));body.append(remember)
                if state['connected']:
                    body.append(label('Start allows Jev to process today’s completed activity using app names, these category names and remembered choices. Your TypeSafe account pays for requests.','dim-label'))
                self.simple_expand(body,'Data and limits',f"Jev receives app names, the selected generic category names/guidance, optional local title-match counts and remembered corrections. Real project names, raw titles, paths, screenshots, timestamps, rates and entry descriptions are not added. TypeSafe processes data in the US; standard retention has no fixed published duration. ZDR is by request. Your cap is {current['daily_requests']} background requests/day; sending pauses after {current['daily_tokens']:,} reported input tokens (it can cross by one request). Unknown usage pauses sending. Existing app exclusions stay in effect. AI categories are estimates, never proof of output or automatic billing approval. Pause or turn AI off in Settings.")
                health=desktop.read_health(self.store)
                status=label('','dim-label');body.append(status)
                if health['status'] in ('setup_required','stopped','error','degraded'):
                    status.set_text('Recording needs setup. Use Repair recording below; desktop sign-in may be needed.')
                    body.append(button('Repair recording',lambda _:self.simple_repair(status)))
                def finish(_):
                    try:
                        finish_setup(self.store,[k for k in BUCKETS if k in chosen],connected=state['connected'],titles=state['titles'],remember=state['remember'],backend='flatpak' if desktop.FLATPAK else 'native',tools=[k for k in TOOLS if k in tool_choices],local_types=state['local_types'])
                        # This explicit Start action resumes existing capture. No
                        # background policy is enabled merely by opening setup.
                        desktop.set_paused(self.store,False);desktop.start_collector()
                    except (ValueError,OSError) as exc:status.set_text(str(exc));return
                    window.close();self.show_page('Today');self.toast('Your day is ready')
                body.append(button('Start recording with Jev' if state['connected'] else 'Start local recording',finish,True))
                self.simple_tool_choices(body,tool_choices)
                self.local_automation_choices(body,state)
                if desktop.FLATPAK:body.append(label('Keep this Flatpak window open for continuous Jev processing until background permission is verified on your desktop.','dim-label'))
            # Each step starts at the top and places keyboard focus on its heading.
            body.get_parent().get_vadjustment().set_value(0)
        connect_button=paste_button=skip_button=status=None
        render();window.present();return window
