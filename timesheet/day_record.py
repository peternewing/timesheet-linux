"""Factual, local day records. App use is evidence, not proof of output."""
from __future__ import annotations
import io
from datetime import datetime,timedelta
from pathlib import Path
from xml.sax.saxutils import escape


def bounds(day):
    return int(datetime.combine(day,datetime.min.time()).timestamp()),int(datetime.combine(day+timedelta(days=1),datetime.min.time()).timestamp())


def snapshot(store,day,now=None,*,include_running=False):
    now=int(datetime.now().timestamp() if now is None else now);start,end=bounds(day)
    # Export a coherent SQLite snapshot while capture may continue independently.
    from contextlib import nullcontext
    joined=store.db.in_transaction
    with nullcontext() if joined else store.db:
        if not joined:store.db.execute('BEGIN')
        records=store.activity_for(start,min(end,now)) if now>start else []
        entries=store.entries(start,min(end,now)) if now>start else []
        rows=[];categories={};active=0;away=0;gaps=0;hidden=0
        for record in records:
            seconds=record['end']-record['start'];state=record['state']
            if state=='active':active+=seconds
            elif state in ('away','locked'):away+=seconds
            elif state=='unknown':gaps+=seconds
            elif state in ('personal','excluded'):hidden+=seconds
            # Never export titles, private excluded app names or inferred intervals.
            if rows and rows[-1]['end']==record['start'] and (rows[-1]['app'],rows[-1]['state'])==(record['app'] if state=='active' else '',state):rows[-1]['end']=record['end']
            else:rows.append(dict(start=record['start'],end=record['end'],app=record['app'] if state=='active' else '',state=state))
        allocations=[];ai=0;human=0
        for entry in sorted(entries,key=lambda r:(r['start'],r['id'])):
            a=max(start,entry['start']);z=min(end,now,entry['end'])
            if z<=a:continue
            seconds=z-a;automatic=entry['origin'] in ('jev','automatic')
            evidence=bool(entry['activity_id'] and store.db.execute('SELECT 1 FROM activity WHERE id=?',(entry['activity_id'],)).fetchone())
            source='AI category' if entry['origin']=='jev' else 'Rule category' if entry['origin']=='automatic' else 'Chosen by you' if evidence else 'Manual entry'
            allocations.append(dict(id=entry['id'],revision=entry['revision'],task_id=entry['task_id'],task=entry['task'],start=a,end=z,source=source,status=entry['status'],evidence=evidence))
            categories[entry['task']]=categories.get(entry['task'],0)+seconds
            if automatic:ai+=seconds
            else:human+=seconds
        running=None
        if include_running:
            rt=store.runtime()
            if rt['state']=='running' and rt['started'] is not None:
                a=max(start,rt['started']);z=min(end,now)
                if z>a:
                    seconds=z-a-sum(max(0,min(z,r['end'])-max(a,r['start'])) for r in entries)
                    task=store.db.execute('SELECT name FROM tasks WHERE id=?',(rt['task_id'],)).fetchone()
                    if task and seconds>0:
                        human+=seconds;categories[task['name']]=categories.get(task['name'],0)+seconds
                        running=dict(task=task['name'],seconds=seconds,start=a,end=z)
        apps={}
        for row in rows:
            if row['state']=='active':
                key=row['app'].casefold()
                name,seconds=apps.get(key,(row['app'],0));apps[key]=(name,seconds+row['end']-row['start'])
        top_apps=sorted(apps.values(),key=lambda x:(-x[1],x[0].casefold()))
        unclassified=sum(r['end']-r['start'] for r in store.activity_for(start,min(end,now),True,now=now) if r['state']=='active') if now>start else 0
        return dict(day=day.isoformat(),generated=now,active=active,away=away,gaps=gaps,private=hidden,ai=ai,human=human,
                    unclassified=unclassified,top_apps=top_apps,running=running,categories=sorted(categories.items(),key=lambda x:(-x[1],x[0])),activity=rows,entries=allocations)


def duration(seconds):
    seconds=int(seconds)
    return f'{seconds//3600}h {seconds%3600//60:02d}m {seconds%60:02d}s'


def pdf(record):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    except ImportError as exc:raise ValueError('Install the PDF export dependency to save a day record.') from exc
    fonts=Path(__file__).resolve().parent.parent/'resources/fonts'
    if not (fonts/'DejaVuSans.ttf').exists():fonts=Path('/usr/share/fonts/truetype/dejavu')
    if 'DayRecord' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('DayRecord',str(fonts/'DejaVuSans.ttf')))
        pdfmetrics.registerFont(TTFont('DayRecordBold',str(fonts/'DejaVuSans-Bold.ttf')))
    styles={k:ParagraphStyle(k,fontName='DayRecordBold' if k in ('title','heading') else 'DayRecord',fontSize=n,leading=n*1.45,spaceAfter=8,textColor=colors.HexColor('#213547')) for k,n in [('title',24),('heading',13),('body',9),('small',8)]}
    def text(value,style='body'):return Paragraph(escape(str(value)).replace('\n','<br/>'),styles[style])
    out=io.BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=36,leftMargin=36,topMargin=36,bottomMargin=40,title='Day record '+record['day'],author='Time Sheet Linux')
    story=[text('My day record','title'),text(record['day'],'heading'),text('Saved '+datetime.fromtimestamp(record['generated']).astimezone().strftime('%d %b %Y %H:%M %Z'),'small'),
           text('Recorded app activity: '+duration(record['active'])+' | Away / locked: '+duration(record['away'])+' | Capture gaps: '+duration(record['gaps'])),
           text('AI / rule categories: '+duration(record['ai'])+' | User choices / manual entries: '+duration(record['human'])+' | Unclassified activity: '+duration(record['unclassified'])),
           text('A local activity record, not independent verification of productivity or completed output. AI categories are estimates. Gaps are not counted as work. Manual entries can extend beyond captured app activity. No billing approval is implied.','small')]
    def table(head,rows,widths):
        data=[[text(v,'small') for v in head]]+[[text(str(v)[:500],'small') for v in row] for row in rows]
        t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E8F0F5')),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#CBD8E0')),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));return t
    story+=[Spacer(1,12),text('How the day was categorised','heading')]
    story.append(table(['Category','Time'],[(name,duration(seconds)) for name,seconds in record['categories']] or [('Nothing categorised yet','—')],[380,143]))
    story+=[Spacer(1,16),text('Category timeline','heading')]
    clock=lambda t:datetime.fromtimestamp(t).astimezone().strftime('%H:%M:%S %Z')
    story.append(table(['Recorded period','Category','Source'],[(clock(r['start'])+' – '+clock(r['end']),r['task'],r['source']) for r in record['entries']] or [('—','No saved category entries','—')],[175,208,140]))
    story+=[Spacer(1,16),text('Captured app activity','heading')]
    states={'away':'Away','locked':'Locked','unknown':'Capture gap','personal':'Marked personal','excluded':'Excluded','paused':'Paused'}
    story.append(table(['Recorded period','Application / state','Time'],[(clock(r['start'])+' – '+clock(r['end']),r['app'] if r['state']=='active' else states.get(r['state'],'Not active'),duration(r['end']-r['start'])) for r in record['activity']] or [('—','No captured observations','—')],[175,208,140]))
    story.append(Spacer(1,12));story.append(text('Private titles, financial rates and entry descriptions are omitted. Exported from local records; this file is not a tamper-proof certificate.','small'))
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('DayRecord',8);canvas.drawString(36,20,'Time Sheet Linux · '+record['day']);canvas.drawRightString(A4[0]-36,20,'Page '+str(doc.page));canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer);return out.getvalue()
