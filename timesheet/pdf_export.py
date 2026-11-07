"""Offline PDF exports from frozen reports; exporting never changes billing state."""
from __future__ import annotations
import io
import inspect
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape


def report_pdf(rows, report_id, *, paper='A4', invoice=None):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, LETTER
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except ImportError as exc:
        raise ValueError('PDF export requires python3-reportlab. See the installation guide.') from exc
    if not rows: raise ValueError('Cannot export an empty report.')
    if paper not in ('A4','Letter'): raise ValueError('Choose A4 or Letter paper.')
    currency=rows[0]['currency']
    if any(row['currency']!=currency for row in rows): raise ValueError('A report must use one currency.')
    fonts=Path(__file__).resolve().parent.parent/'resources/fonts'
    font=fonts/'DejaVuSans.ttf'; bold=fonts/'DejaVuSans-Bold.ttf'
    if not font.exists():
        fonts=Path('/usr/share/fonts/truetype/dejavu');font=fonts/'DejaVuSans.ttf';bold=fonts/'DejaVuSans-Bold.ttf'
    if not font.exists() or not bold.exists(): raise ValueError('Install DejaVu Sans fonts to export Unicode PDFs.')
    if 'Timesheet' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('Timesheet',str(font)))
        pdfmetrics.registerFont(TTFont('TimesheetBold',str(bold)))
        pdfmetrics.registerFontFamily('Timesheet',normal='Timesheet',bold='TimesheetBold')
    styles={name:ParagraphStyle(name,fontName='TimesheetBold' if name in ('heading','label') else 'Timesheet',
        fontSize=size,leading=size*1.45,textColor=colors.HexColor('#172B3A'),spaceAfter=6)
        for name,size in [('heading',23),('body',9),('label',9),('small',8)]}
    def text(value,style='body'):
        # ReportLab supports markup: escape every piece of user-controlled text.
        return Paragraph(escape(str(value)).replace('\n','<br/>'),styles[style])
    data=io.BytesIO();size=A4 if paper=='A4' else LETTER
    document=SimpleDocTemplate(data,pagesize=size,rightMargin=36,leftMargin=36,topMargin=42,bottomMargin=46,
        title=('Invoice draft' if invoice else 'Timesheet report')+f' {report_id}',author='Time Sheet Linux')
    story=[text('Invoice draft' if invoice else 'Timesheet report','heading'),text(f'Report #{report_id} | {rows[0]["client"]}')]
    if invoice:
        required=('number','seller','customer','issued','due')
        if any(not str(invoice.get(key,'')).strip() for key in required): raise ValueError('Complete invoice reference, seller, customer and dates.')
        try:
            issued=datetime.strptime(invoice['issued'],'%Y-%m-%d').date()
            due=datetime.strptime(invoice['due'],'%Y-%m-%d').date()
        except ValueError as exc: raise ValueError('Invoice dates must use YYYY-MM-DD.') from exc
        if due<issued: raise ValueError('The due date cannot precede the issue date.')
        story += [text(f'Reference: {invoice["number"]} | Issued: {issued} | Due: {due}'),
            text('From','label'),text(invoice['seller']),text('Bill to','label'),text(invoice['customer']),
            text('Draft for review. No tax has been calculated. Export does not mark work billed.','small')]
    else:
        story.append(text('Saved report snapshot. Exact durations and approved rates; no duration rounding.','small'))
    story.append(Spacer(1,12))
    headings=['Date / work','Description','Duration','Rate / h','Amount']
    table_data=[[text(h,'label') for h in headings]]
    total=0;seconds=0
    for row in rows:
        duration=row['end']-row['start'];seconds+=duration;total+=row['amount']
        date=row.get('report_date') or datetime.fromtimestamp(row['start']).strftime('%Y-%m-%d')
        work=f'{date}\n{row["project"]}\n{row["task"]}'
        description=row['description']
        # Older ReportLab cannot split an oversized cell; bounded fragments also
        # make extreme user descriptions safe across page boundaries.
        parts=max(1,(max(len(work),len(description))+239)//240)
        for part in range(parts):
            start=part*240; end=start+240
            table_data.append([text(work[start:end]),text(description[start:end]),
                text(f'{duration//3600}:{duration%3600//60:02d}:{duration%60:02d}' if part==0 else ''),
                text(f'{Decimal(row["rate"])/100:.2f}' if part==0 else ''),
                text(f'{Decimal(row["amount"])/100:.2f}' if part==0 else '')])
    width=size[0]-72
    options={'colWidths':[width*.25,width*.35,width*.14,width*.12,width*.14], 'repeatRows':1, 'hAlign':'LEFT', 'splitByRow':1}
    if 'splitInRow' in inspect.signature(Table).parameters: options['splitInRow']=1
    table=Table(table_data,**options)
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E9F1F5')),
        ('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#8199AA')),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#D5DFE5')),
        ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story += [table,Spacer(1,15),text(f'Total: {currency} {Decimal(total)/100:.2f}','heading'),
        text(f'Recorded time: {seconds//3600}h {seconds%3600//60:02d}m {seconds%60:02d}s','small')]
    if invoice and invoice.get('payment'): story += [text('Payment details','label'),text(invoice['payment'])]
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('Timesheet',8);canvas.setFillColor(colors.HexColor('#607080'))
        canvas.drawString(36,24,f'Time Sheet Linux | Report #{report_id} | {currency}')
        canvas.drawRightString(size[0]-36,24,f'Page {doc.page}');canvas.restoreState()
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    return data.getvalue()


def write_pdf(path, content):
    """Replace a destination only after the complete PDF is ready."""
    import os,tempfile
    destination=Path(path)
    try:
        fd,temporary=tempfile.mkstemp(prefix='.timesheet-',suffix='.pdf',dir=destination.parent)
    except PermissionError:
        # The documents portal may grant access to the selected file only.
        # GIO handles replacement through that portal; use it only there.
        if '/doc/' not in str(destination) or not os.environ.get('FLATPAK_ID'): raise
        from gi.repository import Gio, GLib
        try:
            Gio.File.new_for_path(str(destination)).replace_contents(content,None,False,Gio.FileCreateFlags.REPLACE_DESTINATION,None)
        except GLib.Error as exc: raise OSError(str(exc)) from exc
        return
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,destination)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
