import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock
from timesheet.store import Store
from timesheet.automation_store import Repository
from timesheet.automation_worker import Engine,valid_result
from timesheet.decision_policy import settings,route,DEFAULTS,owner_token
from timesheet import jev


def decision(task_id,other=None,**changes):
    task=task_id
    alternatives=[(task,.99)]+([(other,.005)] if other else [])
    value=dict(task=task,probability=.99,none_probability=.005 if other else .01,alternatives=alternatives,
               personal=.01,enough_evidence=.99,work_kind='development',model='jev-test-1',
               usage=dict(input_tokens=200,output_tokens=20),confidence=.98)
    return {**value,**changes}


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite3')
        self.task=self.store.quick_project('Acme','Falcon','Development',6000)
        self.repo=Repository(self.store);self.now=int(datetime(2026,11,8,12).timestamp())
        self.store.set('capture_titles','1')
        self.policy={**DEFAULTS,'mode':'automatic','consent_version':1,'owner':owner_token(),'since':self.now-86400,'allow_project_clues':True}
        self.repo.save_profile(self.task,'Falcon implementation coding for Acme')
        with self.store.db:
            self.aid=self.store.db.execute("INSERT INTO activity(start,end,app,title,state,closed) VALUES(?,?,? ,?,'active',1)",
                (self.now-2000,self.now-1000,'Editor','Acme Falcon private file')).lastrowid
        self.request=Mock(return_value=decision(self.task));self.key=Mock(return_value='synthetic-key')
        self.engine=Engine(self.store,request=self.request,key=self.key)
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def enable(self,**kw):self.repo.configure({**self.policy,**kw})
    def jobs(self):return self.store.rows('SELECT * FROM ai_jobs ORDER BY id')
    def second_activity(self,**kw):
        fields=dict(start=self.now-900,end=self.now-600,app='Editor',title='Acme Falcon private file')|kw
        with self.store.db:return self.store.db.execute("INSERT INTO activity(start,end,app,title,state,closed) VALUES(?,?,?,?,'active',1)",tuple(fields[k] for k in ('start','end','app','title'))).lastrowid
    def test_default_and_invalid_policy_never_transmit(self):
        self.assertEqual(self.engine.step(self.now),'off');self.request.assert_not_called();self.key.assert_not_called()
        self.store.set('ai_policy',json.dumps({'mode':'automatic','consent_version':0}))
        self.assertEqual(self.engine.step(self.now),'off')
        self.assertEqual(settings('{bad')['mode'],'off')
        self.assertEqual(settings(json.dumps({**self.policy,'daily_requests':True}))['mode'],'off')
    def test_automatic_draft_audit_undo_and_no_duplicate(self):
        self.enable();self.assertEqual(self.engine.step(self.now),'applied')
        row=self.store.entries(0,self.now)[0]
        self.assertEqual((row['task_id'],row['status'],row['origin']),(self.task,'draft','jev'))
        self.assertEqual(self.jobs()[0]['state'],'applied');self.assertEqual(self.repo.usage(self.now)['tokens'],200)
        self.assertEqual(self.store.get('ai_pinned_model'),'jev-test-1')
        self.assertEqual(self.engine.step(self.now),'idle');self.assertEqual(self.request.call_count,1)
        self.store.undo();self.assertEqual(self.store.entries(0,self.now),[])
        self.engine.step(self.now);self.assertEqual(self.request.call_count,1)
    def test_only_permitted_derived_context_is_sent(self):
        self.enable();self.engine.step(self.now)
        args,kw=self.request.call_args
        outbound=json.dumps([args,kw]);self.assertNotIn('private file',outbound);self.assertNotIn(str(self.now),outbound)
        self.assertEqual(kw['clues'],[{'task':self.task,'matching_terms':2}])
        self.assertNotIn('synthetic-key',self.jobs()[0]['network']+self.jobs()[0]['decision'])
    def test_no_context_requires_exception_despite_high_probability(self):
        self.enable(allow_project_clues=False);self.assertEqual(self.engine.step(self.now),'exception')
        self.assertEqual(self.store.entries(0,self.now),[])
    def test_suggest_mode_never_writes_and_correction_is_atomic(self):
        self.enable(mode='suggest');self.assertEqual(self.engine.step(self.now),'exception')
        job=self.jobs()[0];self.assertEqual(self.repo.correct(job['id'],self.task,remember=True),1)
        self.assertEqual(len(self.store.rows('SELECT * FROM ai_examples')),1)
        self.assertEqual(len(self.store.rows('SELECT * FROM ai_reviews')),1)
        self.assertEqual(self.store.entries(0,self.now)[0]['status'],'draft')
    def test_equivalent_work_reuses_durable_cache_without_key_access(self):
        self.enable();self.engine.step(self.now);self.second_activity()
        self.key.reset_mock();self.assertEqual(self.engine.step(self.now),'applied')
        self.assertEqual(self.request.call_count,1);self.key.assert_not_called()
        self.assertEqual(len(self.store.entries(0,self.now)),2)
    def test_policy_revoke_during_request_prevents_application(self):
        self.enable()
        def revoke(*a,**kw):self.repo.configure({**self.policy,'mode':'off'});return decision(self.task)
        self.request.side_effect=revoke
        self.assertEqual(self.engine.step(self.now),'stale');self.assertEqual(self.store.entries(0,self.now),[])
    def test_changed_title_or_archived_task_during_request_is_stale(self):
        self.enable()
        def change(*a,**kw):
            with self.store.db:self.store.db.execute("UPDATE activity SET title='Other work' WHERE id=?",(self.aid,))
            return decision(self.task)
        self.request.side_effect=change
        self.assertEqual(self.engine.step(self.now),'stale');self.assertEqual(self.store.entries(0,self.now),[])
    def test_excluded_apps_do_not_create_requests(self):
        self.enable();self.store.set('excluded_apps','Editor, Browser')
        self.assertEqual(self.engine.step(self.now),'idle');self.request.assert_not_called()
    def test_key_error_pauses_without_usage_or_repeated_unlock(self):
        self.enable();self.key.side_effect=RuntimeError('sensitive low-level details')
        self.assertEqual(self.engine.step(self.now),'paused');self.assertEqual(self.repo.usage(self.now)['requests'],0)
        self.assertEqual(self.engine.step(self.now),'paused');self.assertEqual(self.key.call_count,1)
        self.assertNotIn('sensitive',self.store.get('ai_pause_reason'))
    def test_unknown_timeout_usage_requires_acknowledgement(self):
        self.enable();self.request.side_effect=jev.JevError('Network unavailable',retryable=True)
        self.assertEqual(self.engine.step(self.now),'paused');self.assertEqual(self.repo.usage(self.now)['unknown'],1)
        self.assertEqual(self.engine.step(self.now),'paused');self.assertEqual(self.request.call_count,1)
        self.repo.acknowledge_unknown_usage();self.assertEqual(self.repo.usage(self.now)['unknown'],0)
    def test_request_cap_stops_second_non_cached_request(self):
        self.enable(daily_requests=1);self.engine.step(self.now);self.second_activity(app='Browser',title='Acme Falcon')
        self.assertEqual(self.engine.step(self.now),'paused');self.assertEqual(self.request.call_count,1)
        self.assertIn('limit',self.store.get('ai_pause_reason'))
    def test_abandoned_lease_does_not_resend_unknown_request(self):
        self.enable();self.repo.discover(self.now);job=self.repo.claim(self.now)
        self.assertIsNotNone(job);self.assertIsNone(self.repo.claim(self.now+121))
        self.assertEqual(self.jobs()[0]['state'],'failed');self.request.assert_not_called()
    def test_stale_review_cannot_overlap_manual_time(self):
        self.enable(mode='suggest');self.engine.step(self.now);job=self.jobs()[0]
        self.store.add_entry(self.task,self.now-2000,self.now-1000,'Manual')
        with self.assertRaises(ValueError):self.repo.correct(job['id'],self.task)
        self.assertEqual(len(self.store.entries(0,self.now)),1)
    def test_pause_restore_and_older_database_compatibility(self):
        self.enable();self.repo.reset_after_restore();self.assertEqual(self.engine.step(self.now),'off')
        self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0],3)
        self.store.validate()
    def test_settings_update_does_not_commit_outer_transaction(self):
        try:
            with self.store.db:
                self.store.db.execute('BEGIN IMMEDIATE')
                self.store.set('atomic_test','new')
                raise ValueError('abort')
        except ValueError:pass
        self.assertEqual(self.store.get('atomic_test','missing'),'missing')
    def test_probability_and_context_policy_routes(self):
        cases=[dict(task=None,probability=.99),dict(personal=.7),dict(enough_evidence=.5),dict(probability=.8)]
        for update in cases:
            with self.subTest(update=update):self.assertEqual(route(decision(self.task,**update),'automatic',has_context=True)[0],'exception')
    def test_malformed_and_changed_model_results_are_rejected(self):
        tasks=[(self.task,'Task')]
        self.assertTrue(valid_result(decision(self.task),tasks,'jev-test-1'))
        for update in [dict(task=True),dict(probability=float('nan')),dict(model='other'),dict(usage={}),dict(none_probability=.9),dict(alternatives=[])]:
            with self.subTest(update=update):self.assertFalse(valid_result(decision(self.task,**update),tasks,'jev-test-1'))

    def test_focus_provides_explicit_context_without_window_titles(self):
        self.enable(allow_project_clues=False);self.store.set('capture_titles','0')
        self.repo.set_focus(self.task,60,now=self.now-2100)
        self.assertEqual(self.engine.step(self.now),'applied')
        self.assertEqual(self.request.call_args.kwargs['focus'],self.task)
        self.assertEqual(self.request.call_args.kwargs['clues'],[])
        self.assertNotIn('private file',json.dumps(self.request.call_args.kwargs))
    def test_focus_boundaries_split_actual_time_without_inventing_gaps(self):
        other=self.store.add_task(self.store.rows('SELECT id FROM projects')[0]['id'],'Research')
        self.enable(allow_project_clues=False)
        with self.store.db:self.store.db.execute('UPDATE activity SET start=?,end=? WHERE id=?',(self.now-5000,self.now-1000,self.aid))
        self.repo.set_focus(self.task,30,now=self.now-5000);self.repo.set_focus(other,30,now=self.now-3200)
        self.request.side_effect=lambda *a,**kw:decision(kw['focus'] or self.task,other if (kw['focus'] or self.task)==self.task else self.task)
        states=[self.engine.step(self.now) for _ in range(3)]
        self.assertEqual(states,['applied','applied','exception'])
        entries=self.store.entries(0,self.now)
        self.assertEqual(sum(r['end']-r['start'] for r in entries),3600)
        self.assertEqual(sorted(r['task_id'] for r in entries),sorted([self.task,other]))
        self.assertEqual(sum(j['end']-j['start'] for j in self.jobs()),4000)
    def test_mutating_one_default_does_not_affect_other_policies(self):
        first=settings('{}');first['exclude_apps'].append('Editor')
        self.assertEqual(settings('{}')['exclude_apps'],[])
        self.assertEqual(settings('['*2000)['mode'],'off')
    def test_tampered_queued_payload_is_never_sent(self):
        self.enable();self.repo.discover(self.now)
        with self.store.db:self.store.db.execute("UPDATE ai_jobs SET network=?",(json.dumps({'applications':['Private app'],'tasks':[[self.task,'Other']],'examples':[],'clues':[],'focus':None}),))
        self.assertEqual(self.engine.step(self.now),'stale');self.request.assert_not_called()
    def test_revoking_title_collection_invalidates_pending_context(self):
        self.enable();self.repo.discover(self.now);self.store.set('capture_titles','0')
        self.assertEqual(self.engine.step(self.now),'stale');self.request.assert_not_called()
    def test_corrections_are_scoped_and_many_are_saved_atomically(self):
        self.enable(mode='suggest',allow_examples=True);self.second_activity();self.engine.step(self.now);self.engine.step(self.now)
        jobs=self.jobs();count=self.repo.correct(jobs[0]['id'],self.task,remember=True,job_ids=[j['id'] for j in jobs])
        self.assertEqual(count,2);self.assertEqual(len(self.store.rows('SELECT * FROM ai_examples')),2)
        scopes=[json.loads(r['scope']) for r in self.store.rows('SELECT scope FROM ai_examples')]
        self.assertTrue(all(x['clues'] for x in scopes))
    def test_similar_scope_stops_at_privacy_barrier_and_other_dates(self):
        self.enable(mode='suggest');self.second_activity();self.engine.step(self.now);self.engine.step(self.now)
        jobs=self.jobs()
        with self.store.db:self.store.db.execute("INSERT INTO activity(start,end,app,state,closed) VALUES(?,?,'','locked',1)",(self.now-1000,self.now-900))
        self.assertEqual([r['id'] for r in self.repo.matching_scope(jobs[0])],[jobs[0]['id']])
    def test_retention_removes_copied_context_but_keeps_time_entries(self):
        self.enable();self.engine.step(self.now)
        with self.store.db:self.store.db.execute('DELETE FROM activity')
        self.repo.prune(self.now)
        self.assertEqual(self.jobs()[0]['network'],'{}');self.assertEqual(json.loads(self.jobs()[0]['decision'])['model'],'jev-test-1')
        self.assertEqual(len(self.store.entries(0,self.now)),1)
    def test_known_rate_limit_has_global_backoff(self):
        self.enable();self.request.side_effect=jev.JevError('Rate limit',retryable=True,status=429)
        self.assertEqual(self.engine.step(self.now),'retry');self.second_activity(app='Browser')
        self.assertEqual(self.engine.step(self.now+1),'backoff');self.assertEqual(self.request.call_count,1)
        self.assertEqual(self.repo.usage(self.now)['unknown'],0)
    def test_malformed_optional_review_context_is_quarantined(self):
        self.enable(mode='suggest');self.engine.step(self.now)
        with self.store.db:self.store.db.execute("UPDATE ai_jobs SET network='not json'")
        self.assertEqual(self.repo.review_rows(),[]);self.assertEqual(self.jobs()[0]['state'],'stale')
        self.store.validate()
    def test_reset_model_requires_suggestion_only_revalidation(self):
        self.enable();self.engine.step(self.now);self.repo.reset_model()
        self.assertEqual(self.repo.config()['mode'],'suggest');self.assertEqual(self.store.get('ai_pinned_model'),'jev-latest')
        self.assertEqual(self.store.rows('SELECT * FROM ai_cache'),[])

    def test_focus_default_is_explicit_and_cannot_override_disagreement(self):
        value=decision(self.task,probability=.85,none_probability=.15,alternatives=[(self.task,.85)],personal=.25,enough_evidence=.4)
        self.assertEqual(route(value,'automatic',has_context=True,focus_task=self.task,focus_default=False)[0],'exception')
        self.assertEqual(route(value,'automatic',has_context=True,focus_task=self.task,focus_default=True)[0],'apply')
        self.assertEqual(route(value,'suggest',has_context=True,focus_task=self.task,focus_default=True)[0],'exception')
        self.assertEqual(route(decision(self.task),'automatic',has_context=True,focus_task=self.task+1,focus_default=True)[0],'exception')
        for task,flag in [(True,True),(self.task,'yes')]:
            with self.assertRaises(ValueError):self.repo.set_focus(task,draft_default=flag)
    def test_unsent_context_changes_do_not_apply_after_key_unlock(self):
        self.enable()
        def revoke():self.repo.configure({**self.policy,'mode':'off'});return 'synthetic'
        self.key.side_effect=revoke
        self.assertEqual(self.engine.step(self.now),'paused');self.request.assert_not_called()
        self.assertEqual(self.repo.usage(self.now)['requests'],0)
    def test_missing_models_never_silently_use_latest_alias(self):
        self.assertFalse(valid_result(decision(self.task,model='jev-latest'),[(self.task,'Task')],'jev-latest'))
        self.assertFalse(valid_result(decision(self.task,usage={'input_tokens':2**63-1,'output_tokens':0}),[(self.task,'Task')],'jev-test-1'))


    def rule(self,task=None,created=None,priority=0):
        rid=self.store.add_rule('Editor','',task or self.task,priority)
        with self.store.db:self.store.db.execute('UPDATE rules SET created=? WHERE id=?',(self.now-3000 if created is None else created,rid))
        return rid
    def test_saved_rule_prevents_paid_inference(self):
        self.rule();self.enable()
        self.assertEqual(self.engine.step(self.now),'idle');self.request.assert_not_called()
    def test_new_rule_during_request_invalidates_response(self):
        self.enable()
        def added(*args,**kwargs):self.rule();return decision(self.task)
        self.request.side_effect=added
        self.assertEqual(self.engine.step(self.now),'stale');self.assertEqual(self.store.entries(0,self.now),[])
    def test_conflicting_rules_never_allow_automatic_focus_default(self):
        other=self.store.add_task(self.store.rows('SELECT id FROM projects')[0]['id'],'Other')
        self.rule();self.rule(other)
        self.enable();self.repo.set_focus(self.task,60,now=self.now-2100,draft_default=True)
        self.request.return_value=decision(self.task,other)
        self.assertEqual(self.engine.step(self.now),'exception');self.assertEqual(self.store.entries(0,self.now),[])
    def test_rule_creation_boundary_keeps_prior_period_eligible(self):
        self.rule(created=self.now-1500);self.enable()
        self.repo.discover(self.now)
        self.assertEqual([(j['start'],j['end']) for j in self.jobs()],[(self.now-2000,self.now-1500)])
    def test_other_installation_and_missing_owner_never_unlock_or_send(self):
        self.enable(owner='f'*64)
        self.assertEqual(self.engine.step(self.now),'other installation');self.key.assert_not_called();self.request.assert_not_called()
        self.store.set('ai_policy',json.dumps({**self.policy,'owner':''}))
        self.assertEqual(self.engine.step(self.now),'off')
    def test_second_connection_cannot_claim_same_job_or_exceed_cap(self):
        self.enable(daily_requests=1);self.second_activity(app='Browser');self.repo.discover(self.now)
        first=self.repo.claim(self.now)
        second_store=Store(Path(self.tmp.name)/'db.sqlite3')
        try:
            other=Repository(second_store);second=other.claim(self.now)
            self.assertNotEqual(first['id'],second['id'])
            uid,_=self.repo.reserve_request(first,self.now);self.assertIsNotNone(uid)
            self.repo.account(uid,decision(self.task))
            uid,reason=other.reserve_request(second,self.now)
            self.assertIsNone(uid);self.assertIn('limit',reason)
        finally:second_store.close()
    def test_manual_assignment_during_network_call_is_preserved(self):
        self.enable()
        def manual(*args,**kwargs):
            self.store.add_entry(self.task,self.now-1800,self.now-1200,'Human edit')
            return decision(self.task)
        self.request.side_effect=manual
        self.assertEqual(self.engine.step(self.now),'stale')
        rows=self.store.entries(0,self.now);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['description'],'Human edit')
    def test_unknown_acknowledgement_preserves_request_count(self):
        self.enable(daily_requests=1);self.request.side_effect=jev.JevError('Timeout')
        self.engine.step(self.now);self.repo.acknowledge_unknown_usage()
        used=self.repo.usage(self.now)
        self.assertEqual((used['requests'],used['unknown']),(1,0))
    def test_budget_automatically_resets_on_next_local_day(self):
        self.enable(daily_requests=1);self.engine.step(self.now);self.second_activity(app='Browser')
        self.assertEqual(self.engine.step(self.now),'paused')
        self.assertEqual(self.engine.step(self.now+86400),'applied')
        self.assertEqual(self.repo.usage(self.now+86400)['requests'],1)
    def test_model_change_and_auth_rejection_pause_without_repeat(self):
        self.enable();self.request.side_effect=jev.JevError('Authentication rejected',status=401)
        self.assertEqual(self.engine.step(self.now),'paused');self.assertEqual(self.repo.usage(self.now)['unknown'],0)
        self.assertEqual(self.engine.step(self.now+10),'paused');self.assertEqual(self.request.call_count,1)

    def test_guidance_overlap_is_a_local_hint_not_a_block(self):
        other=self.store.add_task(self.store.rows('SELECT id FROM projects')[0]['id'],'Other')
        self.assertTrue(self.repo.profile_warnings(other,'Falcon implementation coding for Acme'))
        self.assertEqual(self.repo.profile_warnings(other,'Marketing newsletter publication'),[])
        self.repo.save_profile(other,'Falcon implementation coding for Acme')
        self.request.assert_not_called()
    def test_progress_does_not_count_deleted_automatic_entries(self):
        self.enable();self.engine.step(self.now)
        self.assertEqual(self.repo.progress(self.now-86400,self.now+86400)['automatic_seconds'],1000)
        self.store.undo()
        self.assertEqual(self.repo.progress(self.now-86400,self.now+86400)['automatic_seconds'],0)


if __name__=='__main__':unittest.main()
