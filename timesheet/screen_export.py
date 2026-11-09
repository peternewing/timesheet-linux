"""Private local, non-financial screen-time summaries; never raw titles or intent guesses."""
import csv,io,unicodedata


def safe_cell(value):
    value=str(value)
    probe=value.lstrip()
    unsafe=probe.startswith(('=','+','-','@')) or bool(probe and unicodedata.category(probe[0]) in ('Cc','Cf'))
    return "'"+value if unsafe or value.startswith(('\t','\r','\n')) else value


def csv_bytes(week,space='all'):
    if space not in ('all','personal','work','unspecified') or any(day.get('space','all')!=space for day in week['days']):raise ValueError('Export the same space that was previewed.')
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(['Screen-time summary','Observed computer use only','Not a work/billing report'])
    writer.writerow(['Space',space]);writer.writerow(['Date','Observed screen seconds','Private screen seconds','Recorded evidence','Away/locked seconds','Capture-gap seconds','Schedule-labelled screen seconds'])
    for day in week['days']:writer.writerow([day['day'],day['screen_seconds'],day['private_seconds'],'yes' if day['has_observations'] else 'no',day['away_seconds'],day['gap_seconds'],day.get('scheduled_seconds',0)])
    writer.writerow([]);writer.writerow(['Application','Observed screen seconds'])
    for name,seconds in week['apps']:writer.writerow([safe_cell(name),seconds])
    return out.getvalue().encode('utf-8-sig')


def write_summary(path,content):
    # The existing durable replacement/portal implementation is format-neutral.
    from .pdf_export import write_pdf
    if not path:raise ValueError('Choose a local destination.')
    write_pdf(path,content)
